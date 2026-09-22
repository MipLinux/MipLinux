"""命令行入口：把四个阶段串起来，并让「失败」有个统一的收尾。

M1 没有界面（界面是 M2），所以这个 CLI 就是 core 的第一个调用者 ——
它只做三件事：解析参数、按顺序调阶段、把失败翻译成退出码。
**逻辑一行都不许写在这里**，否则 M2 的 Qt 前端就得抄一遍。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from dataclasses import dataclass, field

from . import boot, configure, disk, packages, util, __version__
from .configure import TargetConfig
from .events import Event, TextReporter
from .util import (
    EXIT_GUARD,
    EXIT_USAGE,
    InstallerError,
    Runner,
)

#: 执行顺序即依赖顺序：分区 → 装包 → 配置 → 引导
STEP_ORDER = ("disk", "packages", "configure", "boot")

#: dry-run 且目标不是块设备时，按这个大小算布局（只为把命令序列打印出来）
DRY_RUN_ASSUMED_SIZE = 40 * disk.GiB


@dataclass
class _State:
    """阶段之间递的东西。默认值是占位符，dry-run 下就停在这里。"""

    esp: str = util.DRY
    root: str = util.DRY
    root_uuid: str = util.DRY
    esp_uuid: str = util.DRY
    packages: list[str] = field(default_factory=list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mipl_installer",
        description="MipLinux 安装器核心（无界面）。整盘擦除 → GPT(ESP+root) → pacstrap → chroot 配置 → systemd-boot。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例：\n"
            "  python3 -m mipl_installer --disk /dev/vda --yes --password-stdin\n"
            "  python3 -m mipl_installer --disk /dev/vda --dry-run   # 只打印命令，不动盘\n"
        ),
    )
    parser.add_argument("--disk", required=True, help="目标盘（整块盘，例如 /dev/vda）")
    parser.add_argument("--target", default="/mnt", help="目标系统的挂载点（默认 /mnt）")
    parser.add_argument("--hostname", default="mipl", help="装后系统的主机名")
    parser.add_argument("--user", default="mipl", help="要创建的用户（wheel 组，能 sudo）")
    parser.add_argument("--password-stdin", action="store_true",
                        help="从标准输入读一行当密码（非交互环境必须用这个）")
    parser.add_argument("--root-password-stdin", action="store_true",
                        help="再读一行设 root 的密码；**不给就保持 root 锁定**（只能用 sudo 提权）")
    parser.add_argument("--locale", default="zh_CN.UTF-8", help="装后系统的 LANG")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="装后系统的时区")
    parser.add_argument("--packages-file", default=packages.default_packages_file(),
                        help="装后系统的包清单（默认 installer/target-packages.x86_64）")
    parser.add_argument("--pacman-conf", default="/etc/pacman.conf",
                        help="pacman 配置来源（默认运行系统的；Live 里就是出厂设置）")
    parser.add_argument("--mirrorlist", default="/etc/pacman.d/mirrorlist",
                        help="conf 里没有 Include 时，写进目标的 mirrorlist 来源")
    parser.add_argument("--steps", default=",".join(STEP_ORDER),
                        help=f"只跑其中几个阶段，逗号分隔（可选：{','.join(STEP_ORDER)}）")
    parser.add_argument("--yes", action="store_true", help="跳过整盘擦除的二次确认")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的命令，不做任何改动")
    parser.add_argument("--no-nvram", action="store_true",
                        help="不写固件引导项（只在非 Live 环境排练时用，避免动开发机的主板）")
    parser.add_argument("--keep-mounted", action="store_true", help="装完不卸载目标（调试用）")
    parser.add_argument("--log", default=None, help="把过程写一份日志到文件")
    parser.add_argument("--version", action="version", version=f"mipl_installer {__version__}")
    return parser


def parse_steps(raw: str) -> tuple[str, ...]:
    requested = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in requested if s not in STEP_ORDER]
    if unknown:
        raise InstallerError(
            f"不认识的阶段：{'、'.join(unknown)}",
            EXIT_USAGE,
            hint=f"可选：{'、'.join(STEP_ORDER)}",
        )
    if not requested:
        raise InstallerError("一个阶段都没选", EXIT_USAGE, hint=f"例如 --steps {','.join(STEP_ORDER)}")
    # 按依赖顺序跑，不按人敲的顺序 —— "boot,disk" 不是一种意图
    return tuple(s for s in STEP_ORDER if s in requested)


def read_passwords(args: argparse.Namespace) -> tuple[str, str | None]:
    """读用户密码，以及（可选）root 密码。两行都从 stdin 读，**顺序固定**：用户在前。

    密码只走 stdin，绝不进 argv —— argv 会留在进程列表与日志里。
    """
    password = read_password(args)
    if not args.root_password_stdin:
        return password, None
    if args.dry_run:
        return password, util.DRY
    if not args.password_stdin:
        raise InstallerError(
            "--root-password-stdin 要和 --password-stdin 一起用",
            EXIT_USAGE,
            hint="两行密码按「用户在前、root 在后」的顺序从 stdin 读",
        )
    line = sys.stdin.readline().rstrip("\n")
    if not line:
        raise InstallerError("从标准输入读到的 root 密码是空的", EXIT_USAGE,
                            hint="不想设 root 密码就别带 --root-password-stdin")
    return password, line


def read_password(args: argparse.Namespace) -> str:
    if args.dry_run:
        # dry-run 不动盘、也不建用户，没必要先让人输密码
        return util.DRY
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise InstallerError("从标准输入读到空密码", EXIT_USAGE, hint="管子里必须有一行内容")
        return password
    if not sys.stdin.isatty():
        raise InstallerError(
            "非交互环境必须用 --password-stdin",
            EXIT_USAGE,
            hint="read -rsp '密码：' PW && printf '%s\\n' \"$PW\" | python3 -m mipl_installer ... --password-stdin",
        )
    first = getpass.getpass(f"给用户 {args.user} 设密码：")
    if first != getpass.getpass("再输一遍："):
        raise InstallerError("两次输入的密码不一致", EXIT_USAGE)
    if not first:
        raise InstallerError("密码不能是空的", EXIT_USAGE)
    return first


def describe(args: argparse.Namespace, layout: disk.Layout) -> str:
    lines = [
        f"目标盘：  {args.disk}（{util.human_size(layout.total)}）",
        f"布局：    1 MiB 对齐 → ESP {util.human_size(layout.esp_size)} (vfat) + "
        f"root {util.human_size(layout.root_size)} (ext4)",
        f"挂载点：  {args.target}（root）+ {args.target}/boot（ESP）",
        f"包清单：  {args.packages_file}",
        f"装后系统：主机名 {args.hostname}、用户 {args.user}、LANG {args.locale}、时区 {args.timezone}",
    ]
    return "\n".join(lines)


def confirm(args: argparse.Namespace, reporter: TextReporter, layout: disk.Layout) -> None:
    reporter.note(describe(args, layout))
    if args.yes:
        reporter.note("--yes：跳过二次确认")
        return
    if not sys.stdin.isatty():
        raise InstallerError(
            "非交互环境要显式 --yes",
            EXIT_USAGE,
            hint="先不加 --yes 跑一次看计划，确认无误再带上它",
        )
    print(f"\n这会**整盘擦除** {args.disk}，盘上现有数据全部丢弃。")
    typed = input(f"确认请原样输入设备路径（{args.disk}）：").strip()
    if typed != args.disk:
        raise InstallerError("确认不匹配，已放弃", EXIT_GUARD, hint="盘一个字节都没动")


# ── 阶段 ──────────────────────────────────────────────────────────────
def _step_disk(runner: Runner, args: argparse.Namespace, cfg: TargetConfig, layout: disk.Layout,
               state: _State) -> None:
    state.esp, state.root = disk.wipe_and_partition(runner, args.disk, layout)
    disk.make_filesystems(runner, state.esp, state.root)
    disk.mount_target(runner, state.root, state.esp, cfg.target)
    state.root_uuid = disk.uuid_of(runner, state.root)
    state.esp_uuid = disk.uuid_of(runner, state.esp)


def _step_packages(runner: Runner, args: argparse.Namespace, cfg: TargetConfig, state: _State) -> None:
    state.packages = packages.install(runner, cfg.target, args.packages_file, cfg.pacman_conf)


def _step_configure(runner: Runner, args: argparse.Namespace, cfg: TargetConfig, state: _State,
                    password: str, root_password: str | None) -> None:
    configure.configure_system(
        runner, cfg,
        root_uuid=state.root_uuid,
        esp_uuid=state.esp_uuid,
        password=password,
        root_password=root_password,
    )


def _step_boot(runner: Runner, args: argparse.Namespace, cfg: TargetConfig, state: _State) -> None:
    boot.install_bootloader(runner, cfg, state.root_uuid, no_nvram=args.no_nvram)
    boot.verify(runner, cfg, state.root_uuid)


def run(args: argparse.Namespace, reporter: TextReporter, password: str,
        root_password: str | None = None) -> None:
    runner = Runner(reporter, dry_run=args.dry_run)
    cfg = TargetConfig(
        target=args.target,
        hostname=args.hostname,
        user=args.user,
        locale=args.locale,
        timezone=args.timezone,
        pacman_conf=args.pacman_conf,
        mirrorlist=args.mirrorlist,
    )
    steps = parse_steps(args.steps)

    if not args.dry_run:
        util.require_root()
        for step in steps:
            runner.require(util.STEP_TOOLS[step])

    layout = _layout(args, runner, reporter)
    confirm(args, reporter, layout)

    state = _State()
    mounted = False
    try:
        for step in steps:
            reporter.emit(Event(step, f"阶段：{step}", percent=None))
            if step == "disk":
                _step_disk(runner, args, cfg, layout, state)
                mounted = not args.dry_run
            elif step == "packages":
                _step_packages(runner, args, cfg, state)
            elif step == "configure":
                _step_configure(runner, args, cfg, state, password, root_password)
            elif step == "boot":
                _step_boot(runner, args, cfg, state)
    except BaseException:
        # 失败就卸干净：留一堆挂载只会让下一次尝试更难查（也不许在残骸上继续）
        if mounted:
            reporter.note("失败收尾：卸载目标")
            disk.unmount_target(runner, cfg.target)
        raise
    else:
        if mounted and not args.keep_mounted:
            reporter.note("卸载目标")
            disk.unmount_target(runner, cfg.target)

    accounts = f"账号：{args.user}（密码已设，wheel 组，可 sudo）"
    accounts += "、root（已设密码）" if root_password is not None else "、root（未设密码，保持锁定）"
    reporter.emit(Event("done", "装完了 —— 现在可以重启（Live 里 `poweroff`）", percent=100,
                        detail=accounts))


def _layout(args: argparse.Namespace, runner: Runner, reporter: TextReporter) -> disk.Layout:
    if runner.dry_run and not util.is_block_device(args.disk):
        reporter.note(f"dry-run：{args.disk} 不是块设备，按 {util.human_size(DRY_RUN_ASSUMED_SIZE)} 计算布局")
        return disk.plan_layout(DRY_RUN_ASSUMED_SIZE)
    return disk.assert_usable(
        args.disk,
        size_bytes=util.size_of_device(args.disk),
        sources=disk.mount_sources(util.read_text("/proc/self/mountinfo")),
        target_mountpoint=args.target,
        target_is_mountpoint=disk.is_mountpoint(args.target),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    reporter = TextReporter(log_path=args.log)
    try:
        password, root_password = read_passwords(args)
    except InstallerError as exc:
        print(f"[失败] {exc.render()}", file=sys.stderr)
        reporter.close()
        return exc.exit_code
    try:
        run(args, reporter, password, root_password)
    except InstallerError as exc:
        print(f"[失败] {exc.render()}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\n[中断] 用户取消", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - 兜底也要给退出码，别让 traceback 当成成功
        print(f"[失败] 未预期的异常：{exc!r}", file=sys.stderr)
        return util.EXIT_UNEXPECTED
    finally:
        reporter.close()
    return util.EXIT_OK
