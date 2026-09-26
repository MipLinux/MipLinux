"""擦盘 → GPT → ESP + root。

这是整条链里**唯一会摧毁数据**的一段，所以它被拆成两半：

* 纯函数（`plan_layout`、`kernel_partitions`、`mount_sources`、`assert_usable`、
  `detect_disks`、`list_candidates`）负责「算布局」「该不该动手」与「有哪些盘」，
  单测全覆盖，不用 root、不碰盘；
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
import re
from dataclasses import dataclass, replace
from pathlib import Path

from . import util
from .util import (
    EXIT_CONFIGURE,
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
#: **盘尾要留给 GPT 的备份表头**（最后 33 个扇区，按 1 MiB 对齐留）。
#: 不留会怎样：分区压上去之后，内核要么把它裁短、要么干脆不收下 ——
#: 表现为 `/proc/partitions` 里少一个分区、`/dev` 里没有节点，
#: 而 `lsblk` 照样把盘上的表列出来（它自己去读设备），于是报错完全指不到这里。
GPT_TAIL_RESERVE = 1 * MiB
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
    """按盘的大小算布局。太小就拒绝 —— 装到一半才失败比一开始就拒绝贵得多。

    root 不占到最后：**盘尾 1 MiB 留给 GPT 的备份表头**（见 `GPT_TAIL_RESERVE`）。
    """
    esp_start = ALIGN
    esp_size = ESP_SIZE
    root_start = _align_up(esp_start + esp_size, ALIGN)
    root_size = _align_down(total_bytes - root_start - GPT_TAIL_RESERVE, ALIGN)

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


def fits(size_bytes: int) -> bool:
    """这块盘装得下吗？判据与 `plan_layout` **共用一份**，不另立一套阈值 ——
    两套阈值意味着「列表里可选、装的时候被拒」这类自相矛盾。"""
    try:
        plan_layout(size_bytes)
    except InstallerError:
        return False
    return True


# ── 候选盘：给界面选盘用 ──────────────────────────────────────────────
#: 一定不是「可安装的整块盘」的设备名前缀：光驱 / 软驱 / 回环 / 内存盘 /
#: device-mapper / 软 RAID。**光靠前缀不够**，还有第二条判据（见 `detect_disks`）。
NOT_A_DISK_PREFIXES = ("sr", "fd", "loop", "ram", "zram", "dm-", "md")


@dataclass(frozen=True)
class Partition:
    """盘上的一个分区。起点与容量都是**字节**，来源是 sysfs。"""

    device: str
    number: int
    start: int
    size: int
    #: 文件系统类型与卷标，来自 `blkid` 读超级块（**不挂载**）。读不到就是 None。
    fs_type: str | None = None
    label: str | None = None
    #: 是不是 EFI 系统分区 —— 按 GPT 的类型 GUID 认，不是猜「第一个分区」。
    esp: bool = False


@dataclass(frozen=True)
class Candidate:
    """一块候选盘，以及**能确证的事实**。

    这里只放事实，不放结论：`fs_type="ntfs"` 就说 ntfs，**不说「那是 Windows」**；
    `table_type="dos"` 就说 dos，不说「像是启动盘」。界面上的每个字都必须能指出
    出处（见 frontend 的 `DiskPage.qml` 文件头）—— 推断出来的话由谁担保？
    """

    path: str
    model: str
    size: int
    removable: bool
    in_use: bool
    #: "gpt" / "dos" / None（读不到就老实说不知道）
    table_type: str | None = None
    partitions: tuple[Partition, ...] = ()

    @property
    def too_small(self) -> bool:
        return not fits(self.size)

    @property
    def usable(self) -> bool:
        """能不能当安装目标。

        **这不是动手时的守卫** —— 真正的守卫是 `assert_usable`（装的那一刻再查
        一遍，见 cli/pipeline）。这里只负责把盘分成「可选 / 不可选」两堆。
        """
        return not self.in_use and not self.too_small


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
def kernel_partitions(device: str, sysfs_root: str = "/sys") -> list[tuple[str, int, int]]:
    """**内核已经收下**的分区：[(设备路径, major, minor), ...]，按分区号排序。

    判据必须是 sysfs（`/sys/block/<盘>/<分区>/partition`），**不是 `lsblk` 的列表**。
    实测：`lsblk` 会把「盘上的分区表里写着、但内核没收下」的分区也列出来
    （它自己去读设备上的表），照着它去 mkfs 只会得到一句 ENOENT。

    sysfs_root 可注入，测试里拿假的目录就能验（不需要真盘）。
    """
    name = os.path.basename(os.path.realpath(device))
    base = Path(sysfs_root) / "block" / name
    try:
        children = sorted(base.iterdir())
    except OSError:
        return []

    found: list[tuple[str, int, int, int]] = []
    for child in children:
        if not (child / "partition").is_file():
            continue
        try:
            major, minor = (child / "dev").read_text(encoding="utf-8").strip().split(":")
            number = int((child / "partition").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        # 设备路径用 sysfs 的子目录名：udev 与内核用的就是同一个名字（vda1 / nvme0n1p1）
        found.append((f"/dev/{child.name}", int(major), int(minor), number))

    found.sort(key=lambda item: item[3])
    return [(path, major, minor) for path, major, minor, _ in found]


# ── 候选盘：从 sysfs 枚举（界面选盘页的数据源）──────────────────────────
def _sysfs_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def detect_disks(sysfs_root: str = "/sys", disk_root: str = "/dev") -> list[str]:
    """sysfs 里的整块盘路径，按名字排序。

    **不看 `lsblk` 的列表。** 理由与 `kernel_partitions` 同一条（它会把内核没收下
    的分区也列出来），而这里还有第二个理由：`lsblk` 默认把 `zram0`、`loop0`
    当盘列出来，照着它建候选表，用户会在安装器里看见一堆装不进去的「盘」。

    两条判据，缺一不可：
      1. `/sys/block/<name>/device` 存在 —— zram / loop / dm / md 没有它；
      2. 名字不以 `NOT_A_DISK_PREFIXES` 开头 —— 光驱（sr）与软驱**有** `device`，
         但装不进去，也不该出现在候选表里。

    `sysfs_root` 可注入：测试里搭一棵假目录就能验，不需要真盘、不需要 root。
    """
    base = Path(sysfs_root) / "block"
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []

    found: list[str] = []
    for entry in entries:
        name = entry.name
        if name.startswith(NOT_A_DISK_PREFIXES):
            continue
        if not (entry / "device").exists():
            continue
        size = _sysfs_read(entry / "size")
        if size is None or size == "0":
            continue
        found.append(f"{disk_root}/{name}")
    return found


def model_of(device: str, sysfs_root: str = "/sys") -> str:
    """盘的型号。读不到就返回空串 —— **不编一个**。

    virtio-blk（QEMU 的 `if=virtio` 就是它）在 sysfs 里没有 `model`，这是正常的；
    界面那边对空型号有降级显示。这里有啥说啥，别拿设备名冒充型号。

    **但 PCI 的 vendor id 不算型号。** virtio 盘的 `device/vendor` 是 `0x1af4`
    （红帽的 PCI 厂商号），实测它会一路显示到磁盘页的型号那一行 —— 用户看到
    「0x1af4」学不到任何东西，比空着更糟。那种十六进制形式直接当读不到。
    """
    base = Path(sysfs_root) / "block" / os.path.basename(os.path.realpath(device))
    for attr in ("model", "vendor"):
        value = _sysfs_read(base / "device" / attr)
        if not value:
            continue
        value = " ".join(value.split())
        if PCI_ID_RE.fullmatch(value):
            continue
        return value
    return ""


#: GPT 里「EFI 系统分区」的类型 GUID。`blkid` 原样小写给出。
ESP_TYPE_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"

#: PCI 厂商 / 设备号的写法（`0x1af4`）。virtio 盘的 `device/vendor` 就是这个，
#: 它不是型号 —— 详见 `model_of`。
PCI_ID_RE = re.compile(r"0x[0-9a-fA-F]+")


def parse_blkid_export(text: str) -> dict[str, str]:
    """`blkid -o export` 的输出 → 字典。认不出的行直接忽略，不猜。"""
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def probe(runner: Runner | None, device: str) -> dict[str, str]:
    """读一个块设备的超级块元数据（`blkid -p`：**不挂载、不写盘**）。

    读不到就返回空字典 —— 非 root（开发机上跑测试）与不认识的表都走到这里。
    这一层同样只给事实：`TYPE=ntfs` 就说 ntfs，不说它是谁的盘。
    """
    if runner is None or getattr(runner, "dry_run", False):
        return {}
    text = runner.run(["blkid", "-p", "-o", "export", device], capture=True, check=False)
    return parse_blkid_export(text or "")


def _blkid_facts(runner: Runner | None, device: str) -> tuple[str | None, str | None, bool]:
    """一个分区的（文件系统类型, 卷标, 是不是 ESP）。读不到就是 (None, None, False)。"""
    try:
        facts = probe(runner, device)
    except InstallerError:
        # blkid 不在 / 读不了设备：退化成「只知道容量」，不把整页拖崩
        return None, None, False
    esp = facts.get("PART_ENTRY_TYPE", "").lower() == ESP_TYPE_GUID
    return facts.get("TYPE") or None, facts.get("LABEL") or None, esp


def _table_type(runner: Runner | None, device: str) -> str | None:
    """分区表类型（gpt / dos）。读不到就说不知道，**不按盘大小猜**。"""
    try:
        return probe(runner, device).get("PTTYPE") or None
    except InstallerError:
        return None


def _read_partition(entry: Path, disk_root: str) -> Partition | None:
    """一个分区目录 → `Partition`。缺字段或不是数字就当没这个分区。"""
    number = _sysfs_read(entry / "partition")
    start = _sysfs_read(entry / "start")
    size = _sysfs_read(entry / "size")
    if number is None or start is None or size is None:
        return None
    try:
        return Partition(
            device=f"{disk_root}/{entry.name}",
            number=int(number),
            # sysfs 的 start / size 一律是 **512 字节扇区**（与逻辑块大小无关）
            start=int(start) * 512,
            size=int(size) * 512,
        )
    except ValueError:
        return None


def inspect(
    device: str,
    *,
    sysfs_root: str = "/sys",
    sources: set[str] | None = None,
    runner: Runner | None = None,
) -> Candidate:
    """把一块盘读成 `Candidate`：判据全在 sysfs，`blkid` 只补文件系统那两列。"""
    name = os.path.basename(os.path.realpath(device))
    base = Path(sysfs_root) / "block" / name
    if sources is None:
        sources = mount_sources(util.read_text("/proc/self/mountinfo"))

    disk_root = os.path.dirname(device.rstrip("/")) or "/dev"

    partitions: list[Partition] = []
    try:
        children = sorted(base.iterdir())
    except OSError:
        children = []
    for child in children:
        part = _read_partition(child, disk_root)
        if part is None:
            continue
        fs_type, label, esp = _blkid_facts(runner, part.device)
        partitions.append(replace(part, fs_type=fs_type, label=label, esp=esp))
    partitions.sort(key=lambda p: p.number)

    return Candidate(
        path=device,
        model=model_of(device, sysfs_root=sysfs_root),
        size=int(_sysfs_read(base / "size") or 0) * 512,
        removable=(_sysfs_read(base / "removable") or "0") == "1",
        in_use=any(same_device(s, device) for s in sources),
        table_type=_table_type(runner, device),
        partitions=tuple(partitions),
    )


def list_candidates(
    *,
    sysfs_root: str = "/sys",
    disk_root: str = "/dev",
    sources: set[str] | None = None,
    runner: Runner | None = None,
) -> list[Candidate]:
    """选盘页的数据源：枚举所有**整块盘**，每块附上能确证的事实。

    `runner` 给了就顺手用 `blkid` 补文件系统类型与卷标（Live 里是 root，读得到）；
    不给就只报 sysfs 那几列 —— 开发机上跑得动，不必是 root。
    """
    if sources is None:
        sources = mount_sources(util.read_text("/proc/self/mountinfo"))
    return [
        inspect(device, sysfs_root=sysfs_root, sources=sources, runner=runner)
        for device in detect_disks(sysfs_root=sysfs_root, disk_root=disk_root)
    ]


def _ensure_node(runner: Runner, path: str, major: int, minor: int) -> bool:
    """内核已经收下这个分区、`/dev` 里却没有节点时，自己补一个。

    `mknod` 正是 udev 会做的事（同名、同 major:minor，不会打架）。等下去是没有尽头的：
    实测里 5 秒、几十秒都不出现，而设备本身一直是可用的。
    """
    runner.run(["mknod", path, "b", str(major), str(minor)], check=False)
    runner.run(["chown", "root:disk", path], check=False)   # 与 udev 的默认一致：brw-rw----
    runner.run(["chmod", "660", path], check=False)
    return os.path.exists(path)


def settle_udev(runner: Runner) -> None:
    """把 udev 追平到「这些块设备已经处理过」的状态。

    **动任何设备节点之前都要先做这一下。** 实测：分区表在、`/dev/vda1` 在、
    `/proc/partitions` 也认，但 `wipefs -a /dev/vda1` 报
    `probing initialization failed: No such file or directory` —— 那是 libblkid 在
    udev 还没处理完这块设备时的表现（同一对 udevadm 命令之后，同样的 wipefs 立刻成功）。
    """
    runner.run(["udevadm", "trigger", "--subsystem-match=block"], check=False)
    runner.run(["udevadm", "settle"], check=False)


def wipe_and_partition(runner: Runner, device: str, layout: Layout) -> tuple[str, str]:
    """擦盘、建 GPT、建两个分区，返回 (ESP, root) 的设备路径。

    幂等：先擦掉盘上原有的分区表与残留文件系统，再重建 —— 同一块盘重复跑，
    结果一致（ROADMAP 的 S1 就是要验这一条）。
    """
    settle_udev(runner)

    # 盘上原有的分区先各自 wipefs（有些布局里签名留在分区上，只擦盘头擦不掉）。
    # 只擦**内核收下、节点也在**的那些：盘上的表里有名字不代表设备存在。
    for old, _, _ in kernel_partitions(device):
        if runner.dry_run or os.path.exists(old):
            runner.run(["wipefs", "-a", old], exit_code=EXIT_GUARD)
        else:
            runner.reporter.note(f"{old} 还没有设备节点，跳过预擦（整盘 wipefs 会清掉分区表）")
    runner.run(["wipefs", "-a", device], exit_code=EXIT_GUARD)

    if runner.dry_run:
        # dry-run 不碰盘，也就没必要真的去建分区表（顺带让没装 pyparted 的机器
        # 也能跑 dry-run —— 那正是「先看命令再动手」的用途）
        runner.reporter.note("dry-run：跳过 pyparted 建分区表与重读分区")
        return f"{device}1", f"{device}2"

    _parted_create(device, layout)

    # 分区表提交后让内核与 udev 跟上，再等节点出现（理由见 wait_for_partition_nodes）
    runner.run(["partprobe", device], check=False)
    settle_udev(runner)
    return wait_for_partition_nodes(runner, device)


#: 等设备节点：25 × 0.2s = 5 秒。慢磁盘上写分区表可能要一两秒才出节点。
WAIT_ATTEMPTS = 25
WAIT_INTERVAL = "0.2"


def wait_for_partition_nodes(runner: Runner, device: str) -> tuple[str, str]:
    """等两个分区**在内核里出现**，并且在 `/dev` 里有节点。

    两次实测的教训都在这里：
    * 判据是 sysfs 与 `os.path.exists`，**不是 `lsblk`** —— 它会把内核没收下的分区也列出来；
    * 内核收下了、`/dev` 里没有节点，就自己 `mknod` 补（等 udev 是等不到的）。
    """
    seen: list[str] = []
    for attempt in range(WAIT_ATTEMPTS):
        parts = kernel_partitions(device)
        seen = [path for path, _, _ in parts]

        if len(parts) >= 2:
            for path, major, minor in parts[:2]:
                if not os.path.exists(path):
                    _ensure_node(runner, path, major, minor)
            if all(os.path.exists(path) for path, _, _ in parts[:2]):
                return parts[0][0], parts[1][0]

        if attempt + 1 < WAIT_ATTEMPTS:
            runner.run(["sleep", WAIT_INTERVAL], check=False)

    raise InstallerError(
        f"内核只收下了 {len(seen)} 个分区（预期 2 个）：{'、'.join(seen) if seen else '一个都没有'}",
        EXIT_GUARD,
        hint=(
            "分区表没被内核接受。最常见的原因是分区压到了 GPT 备份表头（盘尾 33 个扇区），"
            "布局里已经留了 1 MiB；仍出现就看 `dmesg | tail` 里 GPT 那几行，"
            "并确认分区范围与 `lsblk` 报的不一样"
        ),
    )


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
    """读分区的 UUID。

    **读不到就报错，不返回空串。** 空串会被 fstab 与引导项写成 `UUID=`，
    而那种系统重启之后是起不来的 —— 与其让它悄悄装出一个不能启动的系统，
    不如在这里停下（这正是「安装器直到装出来的系统能启动才算被测过」的反面）。
    """
    value = runner.run(["blkid", "-s", "UUID", "-o", "value", device], capture=True, exit_code=EXIT_GUARD)
    if value is util.DRY:
        return util.DRY
    value = (value or "").strip()
    if not value:
        raise InstallerError(
            f"读不到 {device} 的 UUID（blkid 没有输出）",
            EXIT_CONFIGURE,
            hint=f"mkfs 之后立刻 blkid 偶尔要重试：手工跑 `blkid {device}` 看一眼",
        )
    return value
