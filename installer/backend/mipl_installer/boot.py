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

import os
import re
import struct
from pathlib import Path

from . import disk, util
from .configure import TargetConfig
from .events import step_event
from .util import (
    EXIT_BOOT,
    InstallerError,
    Runner,
    chroot_argv,
    ensure_dir,
    write_text,
)

#: 引导项标题。用发行版完整引导名，不用 "Linux Boot Manager"（那是 bootctl 的默认值）。
TITLE = "MipLinux Boot Manager"
ENTRY_NAME = "miplinux.conf"
FALLBACK_ENTRY_NAME = "miplinux-fallback.conf"
FALLBACK_TITLE = "MipLinux Boot Manager (fallback initramfs)"
LOADER_TIMEOUT = 3

#: 碰固件 NVRAM 的命令的超时（秒）。健康机器上这几条都是秒级；固件变量存储
#: 满 / 碎的时候 SetVariable / GetNextVariableName 能沉默地挂几十分钟（实机教训：
#: 引导阶段挂 40 分钟、只能强杀）。超时不是失败 —— 是「NVRAM 这条路不可信」，
#: 走可移除介质路径照样装得完、起得来。
BOOTCTL_TIMEOUT = 120
EFIBOOTMGR_TIMEOUT = 60

ESP_SYSTEMD_BOOT = "EFI/systemd/systemd-bootx64.efi"
ESP_REMOVABLE_PATH = "EFI/BOOT/BOOTX64.EFI"


def loader_entry(
    root_uuid: str,
    title: str = TITLE,
    *,
    sort_key: str = "miplinux",
    initrd: str = "/initramfs-linux.img",
    ucodes: tuple[str, ...] = (),
) -> str:
    lines = [
        f"title   {title}",
        f"sort-key {sort_key}",
        "linux   /vmlinuz-linux",
    ]
    for ucode in ucodes:
        lines.append(f"initrd  {ucode}")
    lines.append(f"initrd  {initrd}")
    lines.append(f"options root=UUID={root_uuid} rw nvidia_drm.modeset=1")
    return "\n".join(lines) + "\n"


def loader_conf(default: str = ENTRY_NAME, timeout: int = LOADER_TIMEOUT) -> str:
    return f"default {default}\ntimeout {timeout}\n"


def entry_path(cfg: TargetConfig) -> str:
    """entry 要落在 ESP 上：ESP 挂在 `<target>/boot`，所以这就是 ESP 里的 /loader/entries/。"""
    return f"{cfg.target}/boot/loader/entries/{ENTRY_NAME}"


def fallback_entry_path(cfg: TargetConfig) -> str:
    """fallback entry 同样落在 ESP 上。"""
    return f"{cfg.target}/boot/loader/entries/{FALLBACK_ENTRY_NAME}"


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def write_entries(runner: Runner, cfg: TargetConfig, root_uuid: str) -> None:
    runner.reporter.emit(step_event("boot", "entry", "写引导项"))
    esp_dir = Path(f"{cfg.target}/boot")
    ucodes = tuple(f"/{name}" for name in ("amd-ucode.img", "intel-ucode.img") if (esp_dir / name).is_file())
    write_text(runner, entry_path(cfg), loader_entry(root_uuid, TITLE, sort_key="miplinux", initrd="/initramfs-linux.img", ucodes=ucodes))
    if _nonempty_file(esp_dir / "initramfs-linux-fallback.img"):
        write_text(
            runner,
            fallback_entry_path(cfg),
            loader_entry(root_uuid, FALLBACK_TITLE, sort_key="miplinux-fallback", initrd="/initramfs-linux-fallback.img", ucodes=ucodes),
        )
    elif not runner.dry_run:
        # 重试时 preset 可能已关闭 fallback，不能留下指向旧镜像的菜单项。
        Path(fallback_entry_path(cfg)).unlink(missing_ok=True)
    write_text(runner, f"{cfg.target}/boot/loader/loader.conf", loader_conf())


def install_bootloader(runner: Runner, cfg: TargetConfig, root_uuid: str, *, no_nvram: bool = False) -> None:
    """装 systemd-boot 到 ESP（顺带写 NVRAM，除非 no_nvram）。"""
    if not runner.dry_run:
        _esp_identity(runner, cfg)
    runner.reporter.emit(step_event("boot", "bootctl", "安装 systemd-boot 到 ESP"))
    argv = ["bootctl", "--esp-path=/boot"]
    if no_nvram:
        argv.append("--no-variables")
        runner.reporter.note("--no-nvram：只装文件，不碰固件引导项")
    argv.append("install")
    nvram_sick = False
    try:
        runner.run(chroot_argv(cfg.target, argv), exit_code=EXIT_BOOT, timeout=BOOTCTL_TIMEOUT)
    except InstallerError as exc:
        if no_nvram:
            raise
        # 普通失败和超时都不能定位故障阶段；禁用变量写入重试，
        # 若文件安装本身有问题，第二次失败仍会中断安装。
        nvram_sick = True
        runner.reporter.note(
            f"bootctl {'超时' if exc.reason == 'timeout' else '失败'}：原因尚未确定。"
            "禁用 NVRAM 写入重试文件安装，"
            "成功后使用可移除介质路径"
        )
        # 重新完成文件安装，失败就保留 EXIT_BOOT。
        runner.run(
            chroot_argv(cfg.target, ["bootctl", "--esp-path=/boot", "--no-variables", "install"]),
            exit_code=EXIT_BOOT, timeout=BOOTCTL_TIMEOUT,
        )
    write_entries(runner, cfg, root_uuid)
    if nvram_sick:
        fallback_removable(runner, cfg)
        return
    ensure_efi_entry(runner, cfg, no_nvram=no_nvram)


def ensure_efi_entry(runner: Runner, cfg: TargetConfig, *, no_nvram: bool = False) -> None:
    """确认固件引导项在；不在就补，补不上就退到可移除介质路径。

    `bootctl install` 自己会写 NVRAM，所以这里**只做校验与兜底** ——
    这一步失败意味着「盘上的系统是好的，但固件不知道去哪找它」，
    正好是失败模式清单里那条。
    """
    runner.reporter.emit(step_event("boot", "nvram", "写固件引导项"))
    if no_nvram:
        # 不动固件，那就必须留一条「不靠 NVRAM」的路，否则这块盘在真机上起不来
        runner.reporter.note("--no-nvram：不写固件引导项，改留可移除介质路径")
        fallback_removable(runner, cfg)
        return

    if runner.dry_run:
        # 保留原有命令预览；Runner 在 dry-run 下不会执行它。
        runner.run(chroot_argv(cfg.target, ["efibootmgr"]), capture=True, check=False,
                   timeout=EFIBOOTMGR_TIMEOUT)
        runner.reporter.note("dry-run：读不到固件引导项，跳过校验")
        return
    device, parent, number, partuuid = _esp_identity(runner, cfg)
    try:
        listing = runner.run(chroot_argv(cfg.target, ["efibootmgr", "-v"]),
                             capture=True, exit_code=EXIT_BOOT, timeout=EFIBOOTMGR_TIMEOUT)
    except InstallerError:
        runner.reporter.note("无法读取固件引导项，改留可移除介质路径")
        fallback_removable(runner, cfg)
        return
    if _matches_esp(listing or "", partuuid, number):
        return

    runner.reporter.note(f"固件里没有指向 {device} 的有效引导项，补一条")
    if not runner.attempt(
        chroot_argv(cfg.target, ["efibootmgr", "--create", "--disk", parent,
                                "--part", str(number), "--label", TITLE, "--loader",
                                r"\EFI\systemd\systemd-bootx64.efi"]),
        timeout=EFIBOOTMGR_TIMEOUT,
    ):
        fallback_removable(runner, cfg)
        return
    try:
        listing = runner.run(chroot_argv(cfg.target, ["efibootmgr", "-v"]),
                             capture=True, exit_code=EXIT_BOOT, timeout=EFIBOOTMGR_TIMEOUT)
    except InstallerError:
        listing = ""
    if not _matches_esp(listing or "", partuuid, number):
        runner.reporter.note("补建后仍未确认目标 ESP 的有效引导项，改留可移除介质路径")
        fallback_removable(runner, cfg)


def _mounted_device(target: str, fs_type: str) -> str:
    entries = disk.mount_entries(util.read_text("/proc/self/mountinfo"))
    matches = [e for e in entries if re.sub(r"\\([0-7]{3})",
               lambda m: chr(int(m[1], 8)), e.mountpoint) == str(Path(target).resolve())]
    if len(matches) != 1 or matches[0].fstype != fs_type:
        raise InstallerError(f"目标挂载点不是预期的 {fs_type} 文件系统：{target}", EXIT_BOOT)
    return matches[0].source


def _partition_disk(device: str) -> tuple[str, int]:
    node = Path("/sys/class/block") / Path(device).resolve().name
    try:
        number = int((node / "partition").read_text().strip())
        parent = node.resolve(strict=True).parent.name
        if number < 1:
            raise ValueError("invalid partition")
    except (OSError, ValueError) as exc:
        raise InstallerError(f"无法识别 ESP 所属磁盘：{device}", EXIT_BOOT) from exc
    return f"/dev/{parent}", number


def _esp_identity(runner: Runner, cfg: TargetConfig) -> tuple[str, str, int, str]:
    device = _mounted_device(f"{cfg.target}/boot", "vfat")
    facts_text = runner.run(["blkid", "-p", "-o", "export", device],
                            capture=True, exit_code=EXIT_BOOT) or ""
    facts = dict(line.split("=", 1) for line in facts_text.splitlines() if "=" in line)
    guid = facts.get("PART_ENTRY_UUID", "")
    if (facts.get("PART_ENTRY_TYPE", "").lower() != disk.ESP_TYPE_GUID
            or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", guid)):
        raise InstallerError(f"挂载的分区不是有效 GPT ESP：{device}", EXIT_BOOT)
    parent, number = _partition_disk(device)
    return device, parent, number, guid


def _matches_esp(listing: str, partuuid: str, number: int) -> bool:
    order_match = re.search(r"^BootOrder:\s*([0-9a-fA-F,]+)\s*$", listing, re.MULTILINE)
    order = {n.upper() for n in order_match[1].split(",")} if order_match else set()
    for line in listing.splitlines():
        entry = re.match(r"^Boot([0-9a-fA-F]{4})\*\s+", line)
        if not entry or entry[1].upper() not in order:
            continue
        hd = re.search(r"HD\((\d+),GPT,([^,]+),[^)]*\)", line, re.IGNORECASE)
        # efivar 的格式化版本不同：路径可能有 File() 包装，也可能直接显示。
        tail = line[hd.end():] if hd else ""
        file = re.match(r"/File\(([^)]+)\)", tail, re.IGNORECASE)
        if file is None:
            file = re.match(r"/(\\[^\s()]+)", tail)
        if (hd and file and int(hd[1]) == number and hd[2].lower() == partuuid.lower()
                and file[1].replace("/", "\\").lower() == r"\efi\systemd\systemd-bootx64.efi"):
            return True
    return False


def fallback_removable(runner: Runner, cfg: TargetConfig) -> None:
    """NVRAM 写不进时的退路：把 systemd-boot 放到可移除介质路径。

    固件不可读、补建失败或校验不通过时，都保留这条不依赖 NVRAM 的路径。
    """
    source = f"{cfg.target}/boot/{ESP_SYSTEMD_BOOT}"
    destination = f"{cfg.target}/boot/{ESP_REMOVABLE_PATH}"
    ensure_dir(runner, f"{cfg.target}/boot/EFI/BOOT")
    if not runner.dry_run and not os.path.exists(source):
        system_boot_efi = f"{cfg.target}/usr/lib/systemd/boot/efi/systemd-bootx64.efi"
        if os.path.exists(system_boot_efi):
            runner.reporter.note(f"ESP 上未找到 {ESP_SYSTEMD_BOOT}，从目标系统原始路径回退：{system_boot_efi}")
            _verify_efi(Path(system_boot_efi))
            ensure_dir(runner, str(Path(source).parent))
            runner.run(["cp", system_boot_efi, source], exit_code=EXIT_BOOT)
    runner.reporter.note(f"退到可移除介质路径：/{ESP_REMOVABLE_PATH}")
    runner.run(["cp", source, destination], exit_code=EXIT_BOOT)


def verify(runner: Runner, cfg: TargetConfig, root_uuid: str) -> None:
    """收尾断言：**装完了但起不来**全靠这几条挡在重启之前。

    只检查「文件在不在」当然不够，但对 ESP 来说它是必要的第一道：
    systemd-boot 读不到这两个文件，`--boot c` 只会给你 `no bootable device`，
    现场极难定位。第二道是 entry 里的 UUID 与实际 root 分区的 UUID 一致 ——
    UUID 写错的话，内核起得来、找不到根，掉进 emergency shell。
    """
    runner.reporter.emit(step_event("boot", "verify", "校验引导"))
    if runner.dry_run:
        return
    _esp_identity(runner, cfg)
    root = _mounted_device(cfg.target, "ext4")
    actual_uuid = runner.run(["blkid", "-s", "UUID", "-o", "value", root],
                             capture=True, exit_code=EXIT_BOOT)
    if actual_uuid != root_uuid:
        raise InstallerError("实际根文件系统 UUID 与安装记录不一致", EXIT_BOOT)
    missing = [name for name in ("vmlinuz-linux", "initramfs-linux.img", ESP_SYSTEMD_BOOT, ESP_REMOVABLE_PATH)
               if not (Path(f"{cfg.target}/boot") / name).is_file()
               or (Path(f"{cfg.target}/boot") / name).stat().st_size == 0]
    if missing:
        raise InstallerError(
            "ESP 上缺少引导文件或文件为空：" + "、".join(missing),
            EXIT_BOOT,
            hint="多半是 mkinitcpio -P 没跑成（configure 阶段）或 ESP 没挂到 /boot",
        )

    for name in (ESP_SYSTEMD_BOOT, ESP_REMOVABLE_PATH):
        _verify_efi(Path(cfg.target) / "boot" / name)

    try:
        text = util.read_text(entry_path(cfg))
    except OSError as exc:
        raise InstallerError("无法读取 loader entry", EXIT_BOOT) from exc
    roots = [token for line in text.splitlines()
             if line.split() and line.split()[0] == "options"
             for token in line.split()[1:] if token.startswith("root=")]
    if roots != [f"root=UUID={root_uuid}"]:
        raise InstallerError(
            f"loader entry 里的 root UUID 与根分区不一致（{entry_path(cfg)}）",
            EXIT_BOOT,
            hint="entry 是我们自己写的，出现这种不一致说明中间有人改过盘或改过文件",
        )

    def values(contents: str, key: str) -> list[str]:
        return [parts[1].strip() for line in contents.splitlines()
                if (parts := line.split(None, 1)) and parts[0] == key and len(parts) == 2]

    initrds = values(text, "initrd")
    if (values(text, "linux") != ["/vmlinuz-linux"]
            or not initrds
            or initrds[-1] != "/initramfs-linux.img"
            or not all(item in ("/amd-ucode.img", "/intel-ucode.img") for item in initrds[:-1])):
        raise InstallerError("loader entry 的内核或 initrd 路径不符合安装布局", EXIT_BOOT)

    def require_initrds(paths: list[str]) -> None:
        missing = [name for name in paths
                   if not _nonempty_file(Path(cfg.target) / "boot" / name.lstrip("/"))]
        if missing:
            raise InstallerError("引导项引用的 initrd 缺失或为空：" + "、".join(missing), EXIT_BOOT)

    require_initrds(initrds)

    fb_path = fallback_entry_path(cfg)
    if Path(fb_path).is_file():
        try:
            fb_text = util.read_text(fb_path)
        except OSError as exc:
            raise InstallerError("无法读取 fallback loader entry", EXIT_BOOT) from exc
        fb_roots = [token for line in fb_text.splitlines()
                    if line.split() and line.split()[0] == "options"
                    for token in line.split()[1:] if token.startswith("root=")]
        if fb_roots != [f"root=UUID={root_uuid}"]:
            raise InstallerError(f"fallback entry 里的 root UUID 与根分区不一致（{fb_path}）", EXIT_BOOT)
        fb_initrds = values(fb_text, "initrd")
        if (values(fb_text, "linux") != ["/vmlinuz-linux"]
                or not fb_initrds
                or fb_initrds[-1] != "/initramfs-linux-fallback.img"
                or not all(item in ("/amd-ucode.img", "/intel-ucode.img") for item in fb_initrds[:-1])):
            raise InstallerError("fallback entry 的内核或 initrd 路径不符合安装布局", EXIT_BOOT)
        require_initrds(fb_initrds)

    try:
        loader = util.read_text(f"{cfg.target}/boot/loader/loader.conf")
    except OSError as exc:
        raise InstallerError("无法读取 loader.conf", EXIT_BOOT) from exc
    if values(loader, "default") != [ENTRY_NAME]:
        raise InstallerError("loader.conf 默认项不是安装器写入的引导项", EXIT_BOOT)


def _verify_efi(path: Path) -> None:
    """检查 x86_64 EFI 应用头；这不等于验证 Secure Boot 签名或实际可执行性。"""
    try:
        with path.open("rb") as stream:
            dos = stream.read(64)
            if len(dos) != 64 or dos[:2] != b"MZ":
                raise ValueError("missing DOS header")
            offset = struct.unpack_from("<I", dos, 60)[0]
            if offset < 64 or offset > path.stat().st_size - 94:
                raise ValueError("invalid PE offset")
            stream.seek(offset)
            header = stream.read(94)
            if (header[:4] != b"PE\0\0"
                    or struct.unpack_from("<H", header, 4)[0] != 0x8664
                    or struct.unpack_from("<H", header, 20)[0] < 70
                    or struct.unpack_from("<H", header, 24)[0] != 0x20b
                    or struct.unpack_from("<H", header, 92)[0] != 10):
                raise ValueError("not an x86_64 EFI application")
    except (OSError, ValueError, struct.error) as exc:
        raise InstallerError(f"EFI 文件不是有效的 x86_64 EFI 应用：{path}", EXIT_BOOT) from exc
