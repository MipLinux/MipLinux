"""擦盘 → GPT → ESP + root。

这是整条链里**唯一会摧毁数据**的一段，所以它被拆成两半：

* 纯函数（`plan_layout`、`partition_paths`、`mount_sources`、`assert_usable`）
  负责「算布局」和「该不该动手」，单测全覆盖，不用 root、不碰盘；
* 副作用（`wipe_and_partition`、`make_filesystems`、`mount_target`）只做
  「把算好的东西落到盘上」，命令一条条经 `Runner`。

安全红线（根 AGENTS.md）：分区逻辑**只在 `out/target.qcow2` 上跑**（真机用独立盘），
不做无损 resize。v0.1 是整盘擦除 —— 动别人的分区表才是真会丢数据的操作。

布局（roadmap §M1）：

    | 1 MiB | ESP 512 MiB (vfat, esp 标志) | root 剩余 (ext4) |

**ESP 挂 `/boot`**，不是 `/efi`：systemd-boot 只读 FAT，内核与 initramfs 必须
落在 ESP 上，否则重启时它找不到 `/vmlinuz-linux`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import util
from .util import (
    EXIT_GUARD,
    EXIT_USAGE,
    InstallerError,
    Runner,
    ensure_dir,
)

MiB = 1024 ** 2
GiB = 1024 ** 3

#: 1 MiB 对齐。512 字节扇区的盘上是 2048 扇区，4K 盘上是 256 —— 都是整数，
#: 顺带把 4Kn 盘的对齐要求一起满足了。
ALIGN = 1 * MiB
ESP_SIZE = 512 * MiB
#: root 的下限。留 5 GiB 是因为 base + linux + linux-firmware 装完约 1.5 GiB，
#: 再算上 pacman 缓存与将来的桌面环境。
MIN_ROOT_SIZE = 5 * GiB

FAT_LABEL = "MIPLINUX"
EXT4_LABEL = "MIPLINUX"


@dataclass(frozen=True)
class Layout:
    """以**字节**表示的分区布局（转扇区是 pyparted 那一层的事）。"""

    esp_start: int
    esp_size: int
    root_start: int
    root_size: int

    @property
    def total(self) -> int:
        return self.root_start + self.root_size


def plan_layout(total_bytes: int) -> Layout:
    """按盘的大小算布局。太小就拒绝 —— 装到一半才失败比一开始就拒绝贵得多。"""
    esp_start = ALIGN
    esp_size = ESP_SIZE
    root_start = _align_up(esp_start + esp_size, ALIGN)
    root_size = _align_down(total_bytes - root_start, ALIGN)

    if root_size < MIN_ROOT_SIZE:
        raise InstallerError(
            f"盘太小：{util.human_size(total_bytes)}，扣掉 ESP {util.human_size(ESP_SIZE)} 与对齐后"
            f" root 只剩 {util.human_size(max(root_size, 0))}，底限是 {util.human_size(MIN_ROOT_SIZE)}",
            EXIT_GUARD,
            hint="换一块大一点的盘（QEMU 里默认 40G）；这块盘一个字节都没动",
        )
    return Layout(esp_start=esp_start, esp_size=esp_size, root_start=root_start, root_size=root_size)


def _align_up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def _align_down(value: int, align: int) -> int:
    return value // align * align


# ── 该不该动手 ────────────────────────────────────────────────────────
def mount_sources(mountinfo_text: str) -> set[str]:
    """从 `/proc/self/mountinfo` 里取出「设备源」那一列。

    mountinfo 的字段（空格分隔）：`id parent major:minor root mountpoint
    options [optional...] - fstype source superopts`。`source` 在 `-` 之后，
    所以不能取第 1 列也不能取第 3 列。
    """
    sources: set[str] = set()
    for line in mountinfo_text.splitlines():
        fields = line.split()
        if "-" not in fields:
            continue
        sep = fields.index("-")
        if len(fields) >= sep + 3:
            sources.add(fields[sep + 2])
    return sources


def same_device(source: str, device: str) -> bool:
    """`/dev/vda1` 属于 `/dev/vda`；`/dev/vda` 不等于 `/dev/vdb`。"""
    if source == device:
        return True
    if not source.startswith(device):
        return False
    # 尾巴只能是分区号：1 / p1 / 12
    tail = source[len(device):]
    return tail.lstrip("0123456789p") == "" and tail != ""


def assert_usable(
    device: str,
    *,
    size_bytes: int,
    sources: set[str],
    target_mountpoint: str,
    target_is_mountpoint: bool,
) -> Layout:
    """动手前的全部守卫。**任一条不过就不动手**，不「先做着看看」。"""
    if not util.is_block_device(device):
        raise InstallerError(
            f"不是块设备：{device}",
            EXIT_GUARD,
            hint="给整块盘的路径，例如 Live 里挂上来的 /dev/vda（先 lsblk 确认）",
        )
    if util.is_partition(device):
        raise InstallerError(
            f"这是一个分区，不是整块盘：{device}",
            EXIT_GUARD,
            hint="去掉分区号，给整盘路径（/dev/vda1 → /dev/vda）",
        )
    if target_is_mountpoint:
        raise InstallerError(
            f"{target_mountpoint} 已经是个挂载点，拒绝把系统装上去",
            EXIT_GUARD,
            hint="手动卸载后再跑；安装器不替谁卸载机器上已有的挂载",
        )

    in_use = sorted(s for s in sources if same_device(s, device))
    if in_use:
        raise InstallerError(
            f"这块盘正在被使用：{device}（挂载来源：{'、'.join(in_use)}）",
            EXIT_GUARD,
            hint="它是运行环境自己的盘 —— 换一块盘，别动这一块",
        )
    return plan_layout(size_bytes)


def is_mountpoint(path: str) -> bool:
    """是不是挂载点。用 `os.path.ismount` 而不是读 /proc —— 后者在有 bind
    mount 时会给出反直觉的答案。"""
    return os.path.ismount(path)


# ── 落到盘上 ──────────────────────────────────────────────────────────
def partition_paths(lsblk_tree: str) -> tuple[str, str]:
    """从 `lsblk -p -n -o NAME,TYPE` 的输出里取出两个分区。

    不拼字符串（`/dev/vda` + `1`）：virtio 是 `vda1`、nvme 是 `nvme0n1p1`、
    loop 是 `loop0p1`，拼法有三套，让内核告诉我们更省事。
    """
    parts = []
    for line in lsblk_tree.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "part":
            parts.append(fields[0])
    if len(parts) < 2:
        raise InstallerError(
            f"分区建完之后只看到 {len(parts)} 个分区，预期 2 个",
            EXIT_GUARD,
            hint="看 `lsblk -p` 的实际输出；内核没重读分区表时 `partprobe <盘>` 一下",
        )
    # lsblk 按设备号排序，p1 在前
    return parts[0], parts[1]


def _read_partitions(runner: Runner, device: str) -> list[str]:
    tree = runner.run(["lsblk", "-p", "-n", "-o", "NAME,TYPE", device], capture=True, exit_code=EXIT_GUARD)
    if tree is util.DRY:
        return []
    return [line.split()[0] for line in tree.splitlines() if len(line.split()) >= 2 and line.split()[1] == "part"]


def wipe_and_partition(runner: Runner, device: str, layout: Layout) -> tuple[str, str]:
    """擦盘、建 GPT、建两个分区，返回 (ESP, root) 的设备路径。

    幂等：先擦掉盘上原有的分区表与残留文件系统，再重建 —— 同一块盘重复跑，
    结果一致（ROADMAP 的 S1 就是要验这一条）。
    """
    # 盘上原有的分区先各自 wipefs（有些布局里签名留在分区上，只擦盘头擦不掉）
    for old in _read_partitions(runner, device):
        runner.run(["wipefs", "-a", old], exit_code=EXIT_GUARD)
    runner.run(["wipefs", "-a", device], exit_code=EXIT_GUARD)

    if runner.dry_run:
        # dry-run 不碰盘，也就没必要真的去建分区表（顺带让没装 pyparted 的机器
        # 也能跑 dry-run —— 那正是「先看命令再动手」的用途）
        runner.reporter.note("dry-run：跳过 pyparted 建分区表与重读分区")
    else:
        _parted_create(device, layout)

    # 让内核与新分区互相看见：udev 事件落定 + 显式重读分区表（后者在 QEMU 里
    # 有时比 udev 更可靠）
    runner.run(["udevadm", "settle"], check=False)
    runner.run(["partprobe", device], check=False)

    if runner.dry_run:
        esp, root = f"{device}1", f"{device}2"
    else:
        esp, root = partition_paths(
            runner.run(["lsblk", "-p", "-n", "-o", "NAME,TYPE", device], capture=True, exit_code=EXIT_GUARD)
        )
    return esp, root


def _esp_flag(parted):
    """ESP 的标志常量。

    pyparted 是按 libparted 的能力**条件导入**它的（`if hasattr(_ped, "PARTITION_ESP")`），
    所以不能假定它一定在。缺了它分区就没有 ESP 类型 GUID，`bootctl install`
    后面会以「找不到 ESP」的口气报错 —— 在这里先说清楚，代价低得多。
    """
    flag = getattr(parted, "PARTITION_ESP", None)
    if flag is None:
        raise InstallerError(
            "这个 pyparted/libparted 没有 PARTITION_ESP（ESP 标志）",
            EXIT_USAGE,
            hint="parted ≥ 3.2 才有；先看 `pacman -Q parted python-pyparted`",
        )
    return flag


def _parted_create(device: str, layout: Layout) -> None:
    """pyparted：clobber → 新 GPT → ESP + root。

    API 名字照 pyparted 的**当前**写法（与 archinstall 的用法一致）：
    建新表是模块级 `freshDisk(dev, "gpt")`（不是 `Device.disk_new_fresh`），
    落盘是 `Disk.commit()`（不是 `commitToOS()`），`Constraint` 只认关键字参数。
    这几处都验证过源码，别按记忆改回去。

    **这一段只能在装了 pyparted 的环境里验**（Live 里 `python-pyparted`）。
    导入放在函数里，是为了让本模块在没装 pyparted 的机器上也能被导入和单测。
    """
    try:
        import parted
    except ImportError as exc:  # pragma: no cover - 只在缺依赖时走到
        raise InstallerError(
            "缺 python-pyparted（D14 定的分区库）",
            EXIT_USAGE,
            hint="Live 里： pacman -S python-pyparted",
        ) from exc

    try:
        dev = parted.getDevice(device)                    # 注意是 camelCase：getDevice
        dev.clobber()                                     # 抹掉旧分区表与签名
        disk = parted.freshDisk(dev, "gpt")               # 新 GPT
        sector = dev.sectorSize
        constraint = dev.optimalAlignedConstraint         # 按设备的最优对齐（通常 1 MiB）

        for start, size, fstype in (
            (layout.esp_start, layout.esp_size, "fat32"),
            (layout.root_start, layout.root_size, "ext4"),
        ):
            geometry = parted.Geometry(device=dev, start=start // sector, length=size // sector)
            filesystem = parted.FileSystem(type=fstype, geometry=geometry)
            partition = parted.Partition(
                disk=disk,
                type=parted.PARTITION_NORMAL,
                fs=filesystem,
                geometry=geometry,
            )
            disk.addPartition(partition=partition, constraint=constraint)
            if fstype == "fat32":
                # ESP 类型 GUID。**不**顺手加 boot 标志：那是 GPT 里的
                # legacy-BIOS-可引导属性，与 UEFI 无关，加了只会让分区表更难看懂。
                partition.setFlag(_esp_flag(parted))

        disk.commit()                                     # 写盘 + 通知内核重读
    except InstallerError:
        raise
    except Exception as exc:  # parted 的异常层级随版本变，统一收口成一句话
        raise InstallerError(
            f"分区失败：{device}（{exc}）",
            EXIT_GUARD,
            hint="盘上没有任何东西需要抢救 —— 重跑一次；仍失败就把这段输出贴进 tech/04",
        ) from exc


def make_filesystems(runner: Runner, esp: str, root: str) -> None:
    runner.run(["mkfs.vfat", "-F", "32", "-n", FAT_LABEL, esp], exit_code=EXIT_GUARD)
    runner.run(["mkfs.ext4", "-F", "-L", EXT4_LABEL, root], exit_code=EXIT_GUARD)


def mount_target(runner: Runner, root: str, esp: str, target: str = "/mnt") -> None:
    """root 挂到 target，ESP 挂到 target/boot（理由见模块开头）。"""
    ensure_dir(runner, target)
    runner.run(["mount", root, target], exit_code=EXIT_GUARD)
    ensure_dir(runner, f"{target}/boot")
    runner.run(["mount", esp, f"{target}/boot"], exit_code=EXIT_GUARD)


def unmount_target(runner: Runner, target: str = "/mnt") -> None:
    """卸载。**失败不抛** —— 收尾阶段再抛一个异常，只会盖掉真正的失败原因。"""
    if runner.dry_run:
        return
    for argv in (["umount", "-R", target], ["umount", "-R", f"{target}/boot"], ["umount", target]):
        runner.run(argv, check=False)


def uuid_of(runner: Runner, device: str) -> str:
    return runner.run(["blkid", "-s", "UUID", "-o", "value", device], capture=True, exit_code=EXIT_GUARD) or util.DRY
