"""引导：`bootctl install` + loader entry + `efibootmgr` 校验与兜底。

装后系统用 **systemd-boot**（D14），理由是 ISO 自己就是 `uefi.systemd-boot`，
少维护一套。

四条与「重启之后才发现」有关的细节：

* **loader entry 里的路径相对 ESP 根**（`/vmlinuz-linux`），不是 `/boot/vmlinuz-linux`。
  别照抄 `profile/efiboot/*` 那几份 —— 它们是 archiso 的，路径里带 `/arch/`。
* **`options` 带 `nvidia_drm.modeset=1`**（D8 / 04-架构决策 §1.6）：这一条要在
  M1 就写对，否则 M3 装完驱动还得回头改引导项。没有 N 卡时它是个无副作用的参数。
* **`bootctl install` 会写 NVRAM**。QEMU 里写的是我们自己的 `target.vars.fd`，
  正合 `mipl qemu --disk --boot c` 的验法；但在**开发机**上排练会写进真主板 ——
  所以留了 `--no-variables`（`no_nvram=True`）。
* **NVRAM 写不进不算失败**（主板满 / 只读是常见情况）：退到可移除介质路径
  `\\EFI\\BOOT\\BOOTX64.EFI`，告警但不中断（roadmap §6 失败模式清单）。
"""

from __future__ import annotations

from pathlib import Path

from . import util
from .configure import TargetConfig
from .util import (
    EXIT_BOOT,
    InstallerError,
    Runner,
    chroot_argv,
    ensure_dir,
    write_text,
)

#: 引导项标题。用发行版名，不用 "Linux Boot Manager"（那是 bootctl 的默认值）。
TITLE = "MipLinux"
ENTRY_NAME = "miplinux.conf"
LOADER_TIMEOUT = 3

ESP_SYSTEMD_BOOT = "EFI/systemd/systemd-bootx64.efi"
ESP_REMOVABLE_PATH = "EFI/BOOT/BOOTX64.EFI"


def loader_entry(root_uuid: str, title: str = TITLE) -> str:
    return (
        f"title   {title}\n"
        f"sort-key miplinux\n"
        f"linux   /vmlinuz-linux\n"
        f"initrd  /initramfs-linux.img\n"
        f"options root=UUID={root_uuid} rw nvidia_drm.modeset=1\n"
    )


def loader_conf(default: str = ENTRY_NAME, timeout: int = LOADER_TIMEOUT) -> str:
    return f"default {default}\ntimeout {timeout}\n"


def entry_path(cfg: TargetConfig) -> str:
    """entry 要落在 ESP 上：ESP 挂在 `<target>/boot`，所以这就是 ESP 里的 /loader/entries/。"""
    return f"{cfg.target}/boot/loader/entries/{ENTRY_NAME}"


def write_entries(runner: Runner, cfg: TargetConfig, root_uuid: str) -> None:
    write_text(runner, entry_path(cfg), loader_entry(root_uuid))
    write_text(runner, f"{cfg.target}/boot/loader/loader.conf", loader_conf())


def install_bootloader(runner: Runner, cfg: TargetConfig, root_uuid: str, *, no_nvram: bool = False) -> None:
    """装 systemd-boot 到 ESP（顺带写 NVRAM，除非 no_nvram）。"""
    argv = ["bootctl", "--esp-path=/boot"]
    if no_nvram:
        argv.append("--no-variables")
        runner.reporter.note("--no-nvram：只装文件，不碰固件引导项")
    argv.append("install")
    runner.run(chroot_argv(cfg.target, argv), exit_code=EXIT_BOOT)
    write_entries(runner, cfg, root_uuid)
    ensure_efi_entry(runner, cfg, no_nvram=no_nvram)


def ensure_efi_entry(runner: Runner, cfg: TargetConfig, *, no_nvram: bool = False) -> None:
    """确认固件引导项在；不在就补，补不上就退到可移除介质路径。

    `bootctl install` 自己会写 NVRAM，所以这里**只做校验与兜底** ——
    这一步失败意味着「盘上的系统是好的，但固件不知道去哪找它」，
    正好是失败模式清单里那条。
    """
    if no_nvram:
        # 不动固件，那就必须留一条「不靠 NVRAM」的路，否则这块盘在真机上起不来
        runner.reporter.note("--no-nvram：不写固件引导项，改留可移除介质路径")
        fallback_removable(runner, cfg)
        return

    listing = runner.run(chroot_argv(cfg.target, ["efibootmgr"]), capture=True, check=False)
    if listing is None or listing == util.DRY:
        runner.reporter.note("dry-run：读不到固件引导项，跳过校验")
        return
    if _has_entry(listing):
        return

    runner.reporter.note("固件里没有 MipLinux 的引导项，补一条")
    if not runner.attempt(
        chroot_argv(
            cfg.target,
            ["efibootmgr", "--create", "--label", TITLE, "--loader", r"\EFI\systemd\systemd-bootx64.efi"],
        )
    ):
        fallback_removable(runner, cfg)


def _has_entry(efibootmgr_output: str) -> bool:
    """在 `efibootmgr` 的输出里找引导项。

    认两个东西：我们的标题，以及 systemd-boot 的默认落点 —— bootctl 有时会用
    "Linux Boot Manager" 这个名字建项，只认标题会误判成「没建上」。
    """
    lowered = efibootmgr_output.lower()
    return TITLE.lower() in lowered or "systemd-boot" in lowered or "linux boot manager" in lowered


def fallback_removable(runner: Runner, cfg: TargetConfig) -> None:
    """NVRAM 写不进时的退路：把 systemd-boot 放到可移除介质路径。

    注意 `ensure_efi_entry` 里 `efibootmgr --create` 用的是 `check=False`，
    返回 None 表示它失败了 —— 那种情况下这条路才是唯一的引导来源。
    """
    source = f"{cfg.target}/boot/{ESP_SYSTEMD_BOOT}"
    destination = f"{cfg.target}/boot/{ESP_REMOVABLE_PATH}"
    runner.reporter.note(f"退到可移除介质路径：/{ESP_REMOVABLE_PATH}")
    ensure_dir(runner, f"{cfg.target}/boot/EFI/BOOT")
    runner.run(["cp", source, destination], exit_code=EXIT_BOOT)


def verify(runner: Runner, cfg: TargetConfig, root_uuid: str) -> None:
    """收尾断言：**装完了但起不来**全靠这几条挡在重启之前。

    只检查「文件在不在」当然不够，但对 ESP 来说它是必要的第一道：
    systemd-boot 读不到这两个文件，`--boot c` 只会给你 `no bootable device`，
    现场极难定位。第二道是 entry 里的 UUID 与实际 root 分区的 UUID 一致 ——
    UUID 写错的话，内核起得来、找不到根，掉进 emergency shell。
    """
    if runner.dry_run:
        return
    missing = [name for name in ("vmlinuz-linux", "initramfs-linux.img")
               if not (Path(f"{cfg.target}/boot") / name).exists()]
    if missing:
        raise InstallerError(
            "ESP 上没有内核或 initramfs：" + "、".join(missing),
            EXIT_BOOT,
            hint="多半是 mkinitcpio -P 没跑成（configure 阶段）或 ESP 没挂到 /boot",
        )

    text = util.read_text(entry_path(cfg))
    if f"root=UUID={root_uuid}" not in text:
        raise InstallerError(
            f"loader entry 里的 root UUID 与根分区不一致（{entry_path(cfg)}）",
            EXIT_BOOT,
            hint="entry 是我们自己写的，出现这种不一致说明中间有人改过盘或改过文件",
        )
