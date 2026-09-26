"""外部命令与文件写入的唯一出口。

两件事在这里收口，都是为了可测与可复现：

1. **所有 `subprocess` 都走 `Runner`。** 单测注入记录型替身，就能断言
   「会跑哪些命令、顺序对不对」，不必真的动盘。
2. **`--dry-run` 只打印不执行。** 数据依赖的取值（UUID 之类）在 dry-run 下
   拿不到，返回占位符 `DRY`，由调用方原样写进要生成的内容里 —— 与其编一个假
   UUID，不如让占位符显眼地留在产物里。

退出码在这里统一定义：脚本与测试靠它区分失败阶段，不靠读中文报错。
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from .events import Reporter

# ── 退出码 ────────────────────────────────────────────────────────────
EXIT_OK = 0
# 1 留给 Python 自己的未捕获异常，不用
EXIT_USAGE = 2       # 参数/环境不对，没动手
EXIT_GUARD = 3       # 目标盘被守卫拒绝，一个字节都没写
EXIT_PACKAGES = 4    # pacstrap 阶段失败
EXIT_CONFIGURE = 5   # chroot 配置阶段失败
EXIT_BOOT = 6        # 引导阶段失败
EXIT_UNEXPECTED = 7  # 兜底

#: dry-run 下的取值占位符。**不要**把它当成合法 UUID 去用。
DRY = "<dry-run>"


class InstallerError(Exception):
    """带退出码的失败。消息面向用户，hint 是「接下来敲什么」。"""

    def __init__(self, message: str, exit_code: int = EXIT_UNEXPECTED, hint: str | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.hint = hint

    def render(self) -> str:
        text = str(self)
        return f"{text}\n  → {self.hint}" if self.hint else text


class Runner:
    """执行外部命令。dry-run 时只打印。

    命令一律用列表传参（不是 shell 字符串）：参数里出现空格、换行都不会被拆开，
    这正是 Issue #8（`-file=` 被换行拆开）那类事故的通用解。
    """

    def __init__(self, reporter: Reporter, dry_run: bool = False) -> None:
        self.reporter = reporter
        self.dry_run = dry_run
        #: 实际跑过的命令（测试与日志用）
        self.history: list[list[str]] = []

    # ── 执行 ──────────────────────────────────────────────────────────
    def run(
        self,
        argv: list[str],
        *,
        check: bool = True,
        capture: bool = False,
        exit_code: int = EXIT_UNEXPECTED,
        input: str | None = None,
        cwd: str | None = None,
    ) -> str | None:
        """跑一条命令。

        capture=True 时返回 stdout（去掉尾部换行）；dry-run 下返回 `DRY`。
        check=True 时非零退出码抛 `InstallerError`（带 exit_code）。
        """
        argv = [str(a) for a in argv]
        self.history.append(argv)
        self.reporter.command(argv)
        if self.dry_run:
            return DRY if capture else None

        try:
            proc = subprocess.run(
                argv,
                capture_output=capture,
                text=True,
                input=input,
                cwd=cwd,
                check=False,
            )
        except FileNotFoundError as exc:
            raise InstallerError(
                f"找不到命令：{argv[0]}",
                EXIT_USAGE,
                hint="这个命令属于哪个包见 cli.py 的 TOOL_PACKAGES —— 先装它，再重跑",
            ) from exc

        if check and proc.returncode != 0:
            detail = ""
            if capture and proc.stderr:
                detail = "：\n    " + proc.stderr.strip().replace("\n", "\n    ")
            raise InstallerError(f"命令失败（退出码 {proc.returncode}）：{' '.join(argv)}{detail}", exit_code)

        if capture:
            return (proc.stdout or "").rstrip("\n")
        return None

    def have(self, program: str) -> bool:
        from shutil import which

        return which(program) is not None

    def attempt(self, argv: list[str], *, input: str | None = None) -> bool:
        """跑一条命令，只回报成没成功。

        用于「失败有退路」的场合（NVRAM 写不进 → 退到可移除介质路径）。
        普通的失败路径别用它 —— 抛异常的 `run()` 才带得上退出码与提示。
        """
        argv = [str(a) for a in argv]
        self.history.append(argv)
        self.reporter.command(argv)
        if self.dry_run:
            return True
        try:
            proc = subprocess.run(argv, text=True, input=input, check=False)
        except FileNotFoundError:
            return False
        return proc.returncode == 0

    def require(self, programs: list[str], *, tools: dict[str, str] | None = None) -> None:
        """开跑前确认工具都在。缺一个就报「装哪个包」，别跑到一半才炸。"""
        missing = [p for p in programs if not self.have(p)]
        if not missing:
            return
        hints = []
        for name in missing:
            package = (tools or TOOL_PACKAGES).get(name)
            hints.append(f"{name}（包：{package}）" if package else name)
        raise InstallerError(
            "缺少工具：" + "、".join(hints),
            EXIT_USAGE,
            hint="这些是安装环境（Live）里该有的东西 —— 缺了说明环境不对，先补齐再重跑",
        )


#: 工具 → 提供它的包。报错时直接告诉人装什么。
TOOL_PACKAGES = {
    "parted": "parted",
    "partprobe": "parted",
    "wipefs": "util-linux",
    "mknod": "coreutils",
    "chown": "coreutils",
    "chmod": "coreutils",
    "blkid": "util-linux",
    "mount": "util-linux",
    "umount": "util-linux",
    "udevadm": "systemd",
    "arch-chroot": "arch-install-scripts",
    "pacstrap": "arch-install-scripts",
    "pacman-key": "archlinux-keyring",
    "mkfs.vfat": "dosfstools",
    "mkfs.ext4": "e2fsprogs",
    "bootctl": "systemd",
    "efibootmgr": "efibootmgr",
    "pacman": "pacman",
}

#: 每个阶段需要哪些工具（开跑前一次性检查，别跑到一半才炸）
STEP_TOOLS = {
    "disk": ["parted", "partprobe", "wipefs", "udevadm", "mkfs.vfat", "mkfs.ext4",
             "mount", "umount", "blkid", "mknod", "chown", "chmod"],
    "packages": ["pacstrap", "pacman-key", "pacman"],
    "configure": ["arch-chroot"],
    "boot": ["bootctl", "efibootmgr"],
}


def human_size(size: int) -> str:
    # TiB 在最前：2 TB 的盘按 GiB 报是「1863.0 GiB」，而人对自己的盘记得的是
    # 「2 T」—— 磁盘页要让人一眼认出哪块是自己的盘（见 frontend 的 DiskPage）。
    for unit, step in (("TiB", 1024 ** 4), ("GiB", 1024 ** 3), ("MiB", 1024 ** 2)):
        if size >= step:
            return f"{size / step:.1f} {unit}"
    return f"{size} B"


def chroot_argv(target: str, argv: list[str]) -> list[str]:
    """把一条命令放进目标系统里跑。

    用 `arch-chroot` 而不是裸 `chroot`：它顺手把 /proc /sys /dev（含 efivars）
    /run 挂好 —— `bootctl install` 要写 NVRAM，靠的正是 efivars 那一挂。
    """
    return ["arch-chroot", target, *argv]


# ── 文件 ──────────────────────────────────────────────────────────────
def write_text(runner: Runner, path: str, text: str, *, mode: int | None = None,
               secret: bool = False) -> None:
    """写一个文件（含父目录）。dry-run 下只打印内容，不落盘。

    dry-run 把内容也打出来，是因为「将要生成的 fstab / 引导项长什么样」正是
    最值得先看一眼的东西 —— 分区表只是手段，这两个文件才决定它能不能起来。

    `secret=True` 时**连预览都不打**：密码那类内容一旦进了日志，日志就会跟着进仓库、
    进 issue、进别人的终端。要写的路径照旧说出来，内容一个字都不落。
    """
    runner.reporter.note(f"写入 {path}" + (f"（mode {mode:04o}）" if mode is not None else "")
                         + ("（内容不打印）" if secret else ""))
    if runner.dry_run:
        if not secret:
            _preview(runner.reporter, text)
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(target, mode)


#: dry-run 里预览内容的最多行数。mirrorlist 那种几十行的文件不值得占满屏幕。
PREVIEW_LINES = 20


def _preview(reporter, text: str) -> None:
    lines = text.rstrip("\n").splitlines()
    for line in lines[:PREVIEW_LINES]:
        reporter.note(f"    │ {line}")
    if len(lines) > PREVIEW_LINES:
        reporter.note(f"    │ ……（还有 {len(lines) - PREVIEW_LINES} 行）")


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def ensure_dir(runner: Runner, path: str) -> None:
    """建目录（含父目录）。dry-run 下只打印。"""
    runner.reporter.note(f"建目录 {path}")
    if not runner.dry_run:
        Path(path).mkdir(parents=True, exist_ok=True)


def is_block_device(path: str) -> bool:
    """是不是块设备。**不猜**：`/dev/vda` 与 `/dev/vda1` 必须能分开。"""
    try:
        return stat.S_ISBLK(os.stat(path).st_mode)
    except OSError:
        return False


def is_partition(path: str) -> bool:
    """是不是「整盘」而不是它上面的某个分区。

    判据来自 sysfs（`/sys/class/block/<name>/partition` 只在分区上存在），
    不去数设备名的数字 —— `nvme0n1p1`、`loop0p1`、`vda1` 的命名规则不一样。
    """
    name = os.path.basename(os.path.realpath(path))
    return Path(f"/sys/class/block/{name}/partition").exists()


def require_root() -> None:
    if os.geteuid() != 0:
        raise InstallerError(
            "安装器必须 root 跑（它要分区、挂载、往目标系统里写文件）",
            EXIT_USAGE,
            hint="Live 环境里本来就是 root；在别的机器上排练请用 sudo",
        )


def size_of_device(path: str) -> int:
    """块设备的字节数（走 sysfs，不解析 `lsblk` 的文本）。"""
    name = os.path.basename(os.path.realpath(path))
    sectors = Path(f"/sys/class/block/{name}/size").read_text(encoding="utf-8").strip()
    return int(sectors) * 512
