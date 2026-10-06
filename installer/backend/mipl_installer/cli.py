"""命令行入口：把参数翻译成一份 `pipeline.Plan`，交给编排去跑。

M1 没有界面（界面是 M2），所以这个 CLI 就是 core 的第一个调用者 ——
它只做三件事：解析参数、翻译成 `Plan`、把失败翻译成退出码。
**逻辑一行都不许写在这里**（包括那段编排循环）：安装器界面要复用的正是它，
在这儿再写一份就等于有了两份会漂移的真相。编排在 `pipeline.py`，
只读出口在 `queries.py`。

## 这个入口有两种用法

| 用法 | 例子 | stdout 上是什么 |
|---|---|---|
| **安装**（默认） | `--disk /dev/vda --yes --password-stdin` | 人读的过程（`TextReporter`）或 JSON 行（`--json-events`） |
| **只读出口** | `--print-disks` / `--print-keymap de` | **恰好一份 JSON 文档**，别的什么都没有 |

只读出口的那一支里，`Runner` 的旁白走 **stderr** —— 混进 stdout 会让
「读一份 JSON」变成「先剥掉几行人话」，那正是前端最不该做的事。

## 两个不进 argv 的东西

* **密码**只走 stdin（argv 会留在进程列表与日志里）。
* **取消**走 `SIGUSR1`，不是 `SIGINT`/`SIGTERM`：后两个是「立刻去死」的语义，
  而装盘装到一半被杀，留下的是一个谁都说不清的半成品。收到 `SIGUSR1` 只是
  **举手**，真正的取消发生在**阶段之间**（`pipeline.run(should_cancel=…)`），
  退出码 130、并按与失败相同的路径卸载目标。终端里按 Ctrl-C 的语义不变
  （`SIGINT` 仍然立刻中断），因为敲键盘的人看得见自己打断了什么。
"""

from __future__ import annotations

import argparse
import getpass
import json
import signal
import sys

from . import disk, packages, pipeline, queries, util, __version__
from .events import JsonReporter, TextReporter
from .pipeline import STEP_ORDER, Plan, parse_steps
from .util import EXIT_GUARD, EXIT_USAGE, InstallerError, Runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mipl_installer",
        description="MipLinux 安装器核心（无界面）。整盘擦除 → GPT(ESP+root) → pacstrap → chroot 配置 → systemd-boot。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例：\n"
            "  python3 -m mipl_installer --disk /dev/vda --yes --password-stdin\n"
            "  python3 -m mipl_installer --disk /dev/vda --dry-run   # 只打印命令，不动盘\n"
            "  python3 -m mipl_installer --print-disks               # 只读出口：候选人选一块盘\n"
            "  python3 -m mipl_installer --print-keymap de           # 只读出口：键位预览\n"
        ),
    )
    # `--disk` **不是** required：只读出口不该逼人先指一块盘。安装模式下缺了它
    # 由 `queries.require_disk_argv()` 报错，文案与原来的 argparse 提示一致。
    parser.add_argument("--disk", default=None, help="目标盘（整块盘，例如 /dev/vda）；安装模式下必填")
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
    parser.add_argument("--json-events", action="store_true",
                        help="进度走 JSON 行（安装器界面用的协议），而不是人读的文本")

    # ── 只读出口 ──────────────────────────────────────────────────────
    # 一次只跑一个：它们互为替代，同时给两个只会让人猜哪个生效。
    # 名字与 queries.EXITS / queries 里的函数一一对应。
    exits = parser.add_argument_group(
        "只读出口",
        "看一眼运行环境，不动盘、不需要 root（--connect-wifi 除外，它会真的联网）。"
        "输出恰好一份 JSON 文档。",
    )
    pick = exits.add_mutually_exclusive_group()
    pick.add_argument("--print-disks", action="store_true", help="候选盘（sysfs 枚举 + blkid）")
    pick.add_argument("--print-network", action="store_true", help="网络现状（有线 / 无线）")
    pick.add_argument("--print-wifi", action="store_true", help="周围的无线网络，按信号排序")
    pick.add_argument("--print-timezones", action="store_true", help="时区名单 + 当前偏移")
    pick.add_argument("--print-locales", action="store_true", help="语言名单（/usr/share/i18n/SUPPORTED）")
    pick.add_argument("--print-keymaps", action="store_true", help="键盘映射名单（localectl 的写法）")
    pick.add_argument("--print-keymap", metavar="名字", default=None,
                      help="一份键盘映射解析完的样子：主键区要的 keycode → 字符")
    pick.add_argument("--print-plan", action="store_true", help="摘要页要的「装成什么样」")
    pick.add_argument("--check-hostname", metavar="名字", default=None, help="主机名合不合规")
    pick.add_argument("--check-locale", metavar="名字", default=None, help="语言在不在名单里")
    pick.add_argument("--check-keymap", metavar="名字", default=None, help="键盘映射在不在名单里")
    pick.add_argument("--check-timezone", metavar="名字", default=None, help="时区存不存在")
    pick.add_argument("--connect-wifi", metavar="SSID", default=None,
                      help="连一个无线网络；密码从 stdin 读一行")
    exits.add_argument("--rescan", action="store_true",
                       help="配合 --print-wifi：让 NetworkManager 重新扫一遍（慢几秒）")

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


# ── 取消 ──────────────────────────────────────────────────────────────
class CancelFlag:
    """`SIGUSR1` 举手，阶段之间生效。

    内容极简，但 `__call__` 是刻意的：`pipeline.run(should_cancel=…)` 要的就是一个
    「问一下要不要停」的可调用对象，这个类本身就是那个对象，不用再包一层 lambda。
    """

    def __init__(self) -> None:
        self.requested = False

    def request(self, *_args: object) -> None:
        self.requested = True

    def __call__(self) -> bool:
        return self.requested


# ── 只读出口 ──────────────────────────────────────────────────────────
def query_requested(args: argparse.Namespace) -> bool:
    """这次调用是不是只读出口。**判断只写这一处** —— argparse 那边加一个开关、
    这里忘了加，症状是那个开关被当成安装模式、然后抱怨没给 `--disk`。"""
    return any(
        (
            args.print_disks,
            args.print_network,
            args.print_wifi,
            args.print_timezones,
            args.print_locales,
            args.print_keymaps,
            args.print_keymap is not None,
            args.print_plan,
            args.check_hostname is not None,
            args.check_locale is not None,
            args.check_keymap is not None,
            args.check_timezone is not None,
            args.connect_wifi is not None,
        )
    )


def read_wifi_password() -> str:
    """Wi-Fi 密码从 stdin 读一行；TTY 下改成不回显地问。

    开放网络（无密码）就是空串 —— 所以这里不像 `--password-stdin` 那样拒绝空行。
    """
    if sys.stdin.isatty():
        return getpass.getpass("Wi-Fi 密码（开放网络直接回车）：")
    return sys.stdin.readline().rstrip("\n")


def run_query(args: argparse.Namespace) -> int:
    """跑一个只读出口，把结果打到 stdout。

    stdout 上**恰好一份 JSON 文档**，所以 `Runner` 的旁白（`--print-disks` 会跑
    `blkid`）走 stderr。混进 stdout 会让消费方「读一份 JSON」变成「先剥掉几行人话」，
    而那正是前端最不该做的事。
    """
    narration = TextReporter(stream=sys.stderr, log_path=args.log)
    runner = Runner(narration)
    try:
        if args.print_disks:
            payload = queries.disks(runner)
        elif args.print_network:
            payload = queries.network_state(runner)
        elif args.print_wifi:
            payload = queries.wifi(runner, rescan=args.rescan)
        elif args.print_timezones:
            payload = queries.timezones()
        elif args.print_locales:
            payload = queries.locales()
        elif args.print_keymaps:
            payload = queries.keymaps()
        elif args.print_keymap is not None:
            payload = queries.keymap(args.print_keymap)
        elif args.print_plan:
            payload = queries.plan_summary(runner)
        elif args.check_hostname is not None:
            payload = queries.check_hostname(args.check_hostname)
        elif args.check_locale is not None:
            payload = queries.check_locale(args.check_locale)
        elif args.check_keymap is not None:
            payload = queries.check_keymap(args.check_keymap)
        elif args.check_timezone is not None:
            payload = queries.check_timezone(args.check_timezone)
        elif args.connect_wifi is not None:
            payload = queries.connect_wifi(runner, args.connect_wifi, read_wifi_password())
        else:  # pragma: no cover - query_requested() 与上面这支必须同步
            raise InstallerError(
                "这个只读出口没有实现",
                util.EXIT_UNEXPECTED,
                hint="cli.query_requested() 与 cli.run_query() 的分支对不上了",
            )
    except InstallerError as exc:
        print(f"[失败] {exc.render()}", file=sys.stderr)
        return exc.exit_code
    finally:
        narration.close()

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return util.EXIT_OK


# ── 安装 ──────────────────────────────────────────────────────────────
def report_failure(reporter, exc: InstallerError, *, json_mode: bool) -> None:
    """失败的两种说法：人读的进 stderr，界面读的进事件流（**两种都要**）。

    JSON 模式下 stderr 也留着 —— 实机上 `journalctl -u mipl-installer` 收的是
    子进程的 stderr，只发事件流的话，日志里就只剩一行行 JSON 了。
    """
    if json_mode:
        reporter.error(exc.exit_code, str(exc), exc.hint)
    print(f"[失败] {exc.render()}", file=sys.stderr)


def run_install(args: argparse.Namespace) -> int:
    json_mode = bool(args.json_events)
    reporter = JsonReporter(log_path=args.log) if json_mode else TextReporter(log_path=args.log)
    # 实机教训：日志在 Live 的内存盘上，强杀/重启即没。目标盘挂上之后日志会持续
    # 并写进去（pipeline.attach_target_log），这里先说清楚两份各在哪
    reporter.note(
        f"安装日志：分区挂载后持续并写到目标系统 /{pipeline.TARGET_LOG_NAME}（强杀 / 重启后仍在）"
        + (f"；Live 侧副本：{args.log}（内存盘，重启即没）" if args.log else "")
    )
    cancel = CancelFlag()
    previous = signal.signal(signal.SIGUSR1, cancel.request)
    code = util.EXIT_OK
    try:
        queries.require_disk_argv(args.disk)
        password, root_password = read_passwords(args)
        pipeline.run(
            build_plan(args),
            reporter,
            password=password,
            root_password=root_password,
            confirm=confirm_hook(args),
            dry_run=args.dry_run,
            should_cancel=cancel,
        )
    except InstallerError as exc:
        code = exc.exit_code
        report_failure(reporter, exc, json_mode=json_mode)
    except KeyboardInterrupt:
        code = pipeline.EXIT_CANCELLED
        report_failure(reporter, InstallerError("用户取消", code), json_mode=json_mode)
    except Exception as exc:  # noqa: BLE001 - 兜底也要给退出码，别让 traceback 当成成功
        code = util.EXIT_UNEXPECTED
        report_failure(reporter, InstallerError(f"未预期的异常：{exc!r}", code), json_mode=json_mode)
    finally:
        signal.signal(signal.SIGUSR1, previous)
        # `end` 一定要发：界面靠它把「子进程结束了」和「装完了」分开 ——
        # 只看 close 事件的话，被杀掉的进程和装完的进程长得一模一样。
        if json_mode:
            reporter.finish(code)
        reporter.close()
    return code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if query_requested(args):
        return run_query(args)
    return run_install(args)
