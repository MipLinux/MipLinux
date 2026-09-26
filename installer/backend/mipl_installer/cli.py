"""命令行入口：把参数翻译成一份 `pipeline.Plan`，交给编排去跑。

M1 没有界面（界面是 M2），所以这个 CLI 就是 core 的第一个调用者 ——
它只做三件事：解析参数、翻译成 `Plan`、把失败翻译成退出码。
**逻辑一行都不许写在这里**（包括那段编排循环）：M2 的 Qt 前端要复用的正是它，
在这儿再写一份就等于有了两份会漂移的真相。编排在 `pipeline.py`。

密码只走 stdin，绝不进 argv —— argv 会留在进程列表与日志里。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from . import disk, packages, pipeline, util, __version__
from .events import TextReporter
from .pipeline import STEP_ORDER, Plan, parse_steps
from .util import EXIT_GUARD, EXIT_USAGE, InstallerError


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
    parser.add_argument("--locale", default="zh_CN.UTF-8",
                        help="装后系统的 LANG（候选来自运行系统的 /usr/share/i18n/SUPPORTED）")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="装后系统的时区（IANA 名）")
    parser.add_argument("--keymap", default="us",
                        help="装后系统的控制台键盘映射，写进 /etc/vconsole.conf（例如 us、be-latin1）")
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


def build_plan(args: argparse.Namespace) -> Plan:
    """命令行参数 → `Plan`。**唯一的翻译点**，前端走的是同一个 `Plan`。"""
    return Plan(
        disk=args.disk,
        target=args.target,
        hostname=args.hostname,
        user=args.user,
        locale=args.locale,
        timezone=args.timezone,
        keymap=args.keymap,
        packages_file=args.packages_file,
        pacman_conf=args.pacman_conf,
        mirrorlist=args.mirrorlist,
        steps=parse_steps(args.steps),
        no_nvram=args.no_nvram,
        keep_mounted=args.keep_mounted,
    )


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


def describe(plan: Plan, layout: disk.Layout) -> str:
    lines = [
        f"目标盘：  {plan.disk}（{util.human_size(layout.total)}）",
        f"布局：    1 MiB 对齐 → ESP {util.human_size(layout.esp_size)} (vfat) + "
        f"root {util.human_size(layout.root_size)} (ext4)",
        f"挂载点：  {plan.target}（root）+ {plan.target}/boot（ESP）",
        f"包清单：  {plan.packages_path()}",
        f"装后系统：主机名 {plan.hostname}、用户 {plan.user}、LANG {plan.locale}、"
        f"时区 {plan.timezone}、键盘 {plan.keymap}",
    ]
    return "\n".join(lines)


def confirm_hook(args: argparse.Namespace) -> pipeline.ConfirmHook:
    """把「`--yes` / 交互」翻译成一个 `pipeline.ConfirmHook`。

    **守卫一个都不减少**：不带 `--yes` 又没有 TTY 时硬失败（不会静默放行）；
    带 `--yes` 时照样先把计划打出来，只是不再等人敲设备路径。
    """

    def hook(plan: Plan, layout: disk.Layout, reporter: TextReporter) -> None:
        reporter.note(describe(plan, layout))
        if args.yes:
            reporter.note("--yes：跳过二次确认")
            return
        if not sys.stdin.isatty():
            raise InstallerError(
                "非交互环境要显式 --yes",
                EXIT_USAGE,
                hint="先不加 --yes 跑一次看计划，确认无误再带上它",
            )
        print(f"\n这会**整盘擦除** {plan.disk}，盘上现有数据全部丢弃。")
        typed = input(f"确认请原样输入设备路径（{plan.disk}）：").strip()
        if typed != plan.disk:
            raise InstallerError("确认不匹配，已放弃", EXIT_GUARD, hint="盘一个字节都没动")

    return hook


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
        pipeline.run(
            build_plan(args),
            reporter,
            password=password,
            root_password=root_password,
            confirm=confirm_hook(args),
            dry_run=args.dry_run,
        )
    except InstallerError as exc:
        print(f"[失败] {exc.render()}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\n[中断] 用户取消", file=sys.stderr)
        return pipeline.EXIT_CANCELLED
    except Exception as exc:  # noqa: BLE001 - 兜底也要给退出码，别让 traceback 当成成功
        print(f"[失败] 未预期的异常：{exc!r}", file=sys.stderr)
        return util.EXIT_UNEXPECTED
    finally:
        reporter.close()
    return util.EXIT_OK
