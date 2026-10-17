"""CLI：阶段解析、密码怎么进来、dry-run 一行都不许动。

dry-run 是这套东西的「安全演示」：它必须在**没装 pyparted、也不是 root** 的
机器上照跑 —— 那正是「先把命令看一遍再动手」的用途。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mipl_installer import cli, disk, events, pipeline, util
from mipl_installer.util import EXIT_GUARD, EXIT_USAGE, InstallerError
from tests.support import FakeRunner


def _args(**overrides) -> argparse.Namespace:
    base = dict(user="mipl", password_stdin=False, root_password_stdin=False, dry_run=False)
    base.update(overrides)
    return argparse.Namespace(**base)


class TestParseSteps(unittest.TestCase):
    def test_all_by_default(self):
        self.assertEqual(cli.parse_steps(",".join(cli.STEP_ORDER)), cli.STEP_ORDER)

    def test_returns_dependency_order_not_typing_order(self):
        self.assertEqual(cli.parse_steps("boot,disk"), ("disk", "boot"))

    def test_rejects_unknown_step(self):
        with self.assertRaises(InstallerError) as ctx:
            cli.parse_steps("disk,teapot")
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_rejects_empty(self):
        with self.assertRaises(InstallerError):
            cli.parse_steps(",,")


class TestPassword(unittest.TestCase):
    def test_stdin_password(self):
        fake = mock.Mock()
        fake.readline.return_value = "s3cret\n"
        with mock.patch.object(sys, "stdin", fake):
            self.assertEqual(cli.read_password(_args(password_stdin=True)), "s3cret")

    def test_empty_stdin_password_is_refused(self):
        fake = mock.Mock()
        fake.readline.return_value = "\n"
        with mock.patch.object(sys, "stdin", fake):
            with self.assertRaises(InstallerError):
                cli.read_password(_args(password_stdin=True))

    def test_non_interactive_requires_password_stdin(self):
        fake = mock.Mock()
        fake.isatty.return_value = False
        with mock.patch.object(sys, "stdin", fake):
            with self.assertRaises(InstallerError) as ctx:
                cli.read_password(_args())
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)
        self.assertIn("--password-stdin", str(ctx.exception))

    def test_dry_run_asks_nothing(self):
        fake = mock.Mock()
        fake.isatty.return_value = False
        with mock.patch.object(sys, "stdin", fake):
            self.assertEqual(cli.read_password(_args(dry_run=True)), util.DRY)


class TestPasswords(unittest.TestCase):
    def test_user_then_root_in_that_order(self):
        fake = mock.Mock()
        fake.readline.side_effect = ["userpw\n", "rootpw\n"]
        with mock.patch.object(sys, "stdin", fake):
            args = _args(password_stdin=True, root_password_stdin=True)
            self.assertEqual(cli.read_passwords(args), ("userpw", "rootpw"))

    def test_root_is_optional(self):
        fake = mock.Mock()
        fake.readline.return_value = "userpw\n"
        with mock.patch.object(sys, "stdin", fake):
            self.assertEqual(cli.read_passwords(_args(password_stdin=True)), ("userpw", None))

    def test_root_password_needs_password_stdin(self):
        """**回归测试**（#152 交叉审查）：错的参数组合要在**问密码之前**拒绝。

        旧顺序是先 `read_password()`、再查 `--password-stdin` 在不在：交互式终端下
        会先弹出 `getpass("给用户 mipl 设密码：")`，输完才被告知参数错了；单测在
        TTY 下直接挂在这个提示上。这里把 getpass 换成「一被调用就失败」，
        旧实现会以 AssertionError 炸在这里。
        """
        stdin = mock.Mock()
        stdin.isatty.return_value = True
        with mock.patch.object(sys, "stdin", stdin), \
                mock.patch.object(cli.getpass, "getpass",
                                  side_effect=AssertionError("参数错了，不该先问密码")):
            with self.assertRaises(InstallerError) as ctx:
                cli.read_passwords(_args(root_password_stdin=True))
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)
        self.assertIn("--password-stdin", str(ctx.exception))

    def test_empty_root_password_is_refused(self):
        fake = mock.Mock()
        fake.readline.side_effect = ["userpw\n", "\n"]
        with mock.patch.object(sys, "stdin", fake):
            with self.assertRaises(InstallerError):
                cli.read_passwords(_args(password_stdin=True, root_password_stdin=True))

    def test_dry_run_returns_placeholders(self):
        self.assertEqual(cli.read_passwords(_args(dry_run=True, root_password_stdin=True)),
                         (util.DRY, util.DRY))


class TestDryRun(unittest.TestCase):
    """dry-run 必须能在一台「什么都没有」的机器上把命令序列打印全。"""

    def _run(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = cli.main(argv)
        return code, buffer.getvalue()

    def test_prints_the_whole_chain_without_touching_anything(self):
        code, output = self._run(["--disk", "/dev/vda", "--yes", "--dry-run"])
        self.assertEqual(code, util.EXIT_OK, output)

        for expected in (
            "wipefs -a /dev/vda",
            "mkfs.vfat",
            "mkfs.ext4",
            "mount",
            f"pacstrap -C /etc/pacman.conf -G -M {util.DEFAULT_TARGET}",
            f"arch-chroot {util.DEFAULT_TARGET} locale-gen",
            f"arch-chroot {util.DEFAULT_TARGET} mkinitcpio -P",
            "bootctl --esp-path=/boot install",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, output)

        # 数据依赖的取值在 dry-run 下拿不到，留下显眼的占位符而不是编一个假 UUID
        self.assertIn(util.DRY, output)

    def test_no_second_confirmation_needed_with_yes(self):
        code, output = self._run(["--disk", "/dev/vda", "--yes", "--dry-run"])
        self.assertEqual(code, util.EXIT_OK)
        self.assertIn("跳过二次确认", output)

    def test_unknown_step_exits_with_usage_code(self):
        code, output = self._run(["--disk", "/dev/vda", "--yes", "--dry-run", "--steps", "teapot"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("不认识的阶段", output)

    def test_missing_disk_argument_is_a_usage_error(self):
        """`--disk` 不再是 argparse 的必填项（只读出口不该逼人先指一块盘），
        但**安装模式**下缺了它照样是 `EXIT_USAGE`。

        这条守的是「退出码没变」而不是「谁报的错」：脚本与文档按退出码分流，
        从 `SystemExit(2)` 换成 `return 2` 如果顺手改成了别的码，外面看不出来。
        """
        with contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--dry-run"])
        self.assertEqual(code, EXIT_USAGE)

    def test_disk_is_still_required_for_installing(self):
        """反过来钉一次：给了 `--disk` 就不再抱怨它 —— 否则上面那条可以被
        「一律返回 EXIT_USAGE」蒙过去。"""
        code, output = self._run(["--disk", "/dev/vda", "--yes", "--dry-run", "--steps", "disk"])
        self.assertEqual(code, util.EXIT_OK, output)
        self.assertNotIn("要装系统就得指出目标盘", output)

    def test_a_successful_start_says_nothing_about_where_the_log_is(self):
        """「我们会把过程写进哪儿」在正常流程里是自我指涉的噪音（实机反馈）。

        它只在**出事之后**有用 —— 那时由 `log_locations()` 报，而且只报真的在的那份。
        """
        code, output = self._run(["--disk", "/dev/vda", "--yes", "--dry-run"])
        self.assertEqual(code, util.EXIT_OK, output)
        self.assertNotIn("安装日志", output)


class TestConfirmHook(unittest.TestCase):
    """确认那一步只许说在事件流 / stderr 上，stdout 上不许混进非 JSON 的原文。"""

    def _args(self):
        return cli.build_parser().parse_args(["--disk", "/dev/vda", "--dry-run"])

    def _run(self, typed: str):
        out = io.StringIO()
        reporter = events.JsonReporter(stream=out)
        stdin = mock.Mock()
        stdin.isatty.return_value = True
        stdin.readline.return_value = typed
        stderr = io.StringIO()
        plan = pipeline.Plan(disk="/dev/vda")
        layout = disk.plan_layout(40 * disk.GiB)
        try:
            with mock.patch.object(sys, "stdin", stdin), contextlib.redirect_stderr(stderr):
                cli.confirm_hook(self._args())(plan, layout, reporter)
        finally:
            reporter.close()
        return out.getvalue(), stderr.getvalue()

    def test_the_warning_and_prompt_do_not_put_raw_text_on_stdout(self):
        """**回归测试**：JSON 模式下 stdout 一行只许一个 JSON 对象。

        旧实现用 `print()` + `input()`：警告和提示都落在 stdout 上，前端
        `JSON.parse` 第一行就炸（实机症状「后端输出无法解析」）。
        """
        out, err = self._run("/dev/vda\n")
        records = [json.loads(line) for line in out.splitlines()]
        self.assertTrue(records, "事件流上是空的 —— 警告没走 reporter")
        for record in records:
            self.assertIn(record["kind"],
                          ("hello", "event", "note", "command", "error", "end"))
        notes = [record["message"] for record in records if record["kind"] == "note"]
        self.assertTrue(any("整盘擦除" in note for note in notes), notes)
        self.assertIn("确认请原样输入设备路径", err)

    def test_eof_at_the_prompt_is_a_clean_refusal(self):
        """**回归测试**：旧 `input()` 在 EOF 时抛 `EOFError`，被兜底成退出码 7。

        EOF 就是「没人确认」，该走守卫那条路：`EXIT_GUARD`，盘一个字节都没动。
        """
        with self.assertRaises(InstallerError) as ctx:
            self._run("")
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)


class TestBadLogPath(unittest.TestCase):
    """**回归测试**：`--log` 打不开时要给退出码与一句话，而不是 traceback。

    旧实现把 reporter 建在 try 外面，`open()` 的 `FileNotFoundError` 一路冒到
    `__main__`：退出码 1、屏幕上只有栈。这只是「参数打错了」，该是 `EXIT_USAGE`。
    """

    BAD = "/nonexistent-mipl-dir-151/trace.log"

    def test_install_mode(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--disk", "/dev/vda", "--yes", "--dry-run", "--log", self.BAD])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("打不开日志文件", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_query_mode(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--print-timezones", "--log", self.BAD])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("打不开日志文件", err.getvalue())
        self.assertEqual(out.getvalue(), "", "失败时 stdout 上不该有半份 JSON")


class TestQueryInterrupt(unittest.TestCase):
    def test_ctrl_c_returns_the_cancel_exit_code(self):
        """Ctrl-C 在只读出口里同样要落到 130，不能是一屏 traceback。"""
        with mock.patch.object(cli.queries, "timezones", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = cli.main(["--print-timezones"])
        self.assertEqual(code, pipeline.EXIT_CANCELLED)
        self.assertIn("已取消", err.getvalue())


class TestLogLocations(unittest.TestCase):
    """失败收尾里那句「日志在哪」：只报**确实写出来过**的那几份，不报推测的路径。

    目标盘那份按「挂上过」的记录报 —— 失败收尾会先卸载，卸完 `target/var/log/…`
    在目录里已经看不见了，但文件确实在目标盘上。
    """

    def _args(self, log=None, target=util.DEFAULT_TARGET):
        return argparse.Namespace(log=log, target=target)

    def test_nothing_to_report_when_nothing_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self._args(log=f"{tmp}/never-written.log", target=f"{tmp}/mnt")
            self.assertEqual(cli.log_locations(args), [])

    def test_reports_the_live_copy_and_the_target_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.log"
            live.write_text("x", encoding="utf-8")
            target = Path(tmp) / "mnt"
            (target / "var" / "log").mkdir(parents=True)
            (target / pipeline.TARGET_LOG_NAME).write_text("x", encoding="utf-8")
            locations = cli.log_locations(self._args(log=str(live), target=str(target)))
            self.assertEqual(len(locations), 2)
            self.assertTrue(any("重启即没" in item for item in locations))
            self.assertTrue(any("重启后仍在" in item for item in locations))

    def test_target_copy_alone_is_enough(self):
        """没给 `--log`（JSON 事件流也行）时，目标盘那份照样要报出来。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "mnt"
            (target / "var" / "log").mkdir(parents=True)
            (target / pipeline.TARGET_LOG_NAME).write_text("x", encoding="utf-8")
            locations = cli.log_locations(self._args(log=None, target=str(target)))
            self.assertEqual(len(locations), 1)
            self.assertIn("重启后仍在", locations[0])

    def test_the_target_copy_survives_the_unmount_that_hides_it(self):
        """**回归测试**：失败收尾先卸载目标，`target/var/log/…` 就不再是文件了。

        只按「文件在不在」判断，会把唯一活过重启的那份日志漏报 —— 而它正是
        出事时最该看的那一份。挂上过就在 reporter 上留了路径，`run_install()`
        再把它抄到 args 上传给 `log_locations()`（签名不改，#151）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "mnt"
            target.mkdir()
            reporter = events.TextReporter(stream=io.StringIO())
            try:
                pipeline.attach_target_log(
                    FakeRunner(reporter=reporter),
                    pipeline.Plan(disk="/dev/null", target=str(target)),
                    reporter,
                )
                dest = target / pipeline.TARGET_LOG_NAME
                self.assertTrue(dest.is_file())
                shutil.rmtree(target)       # 卸载之后：路径记着，文件看不见
                args = self._args(log=None, target=str(target))
                args.target_log_path = reporter.target_log_path
                locations = cli.log_locations(args)
            finally:
                reporter.close()
        self.assertEqual(len(locations), 1)
        self.assertIn("重启后仍在", locations[0])

    def test_run_install_hands_the_attached_path_to_log_locations(self):
        """**回归测试**：`run_install()` 要把 reporter 上那条记录交给 args。

        这条钉的是那一层交接 —— 只改 `log_locations()` 自己的话，失败收尾里
        「目标盘那份」照样会漏报（`args.target_log_path` 永远不存在）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "var" / "log" / "mipl-installer-install.log"

            def fake_run(plan, reporter, **kwargs):
                reporter.target_log_path = str(dest)
                raise InstallerError("装包失败", util.EXIT_PACKAGES)

            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(cli.pipeline, "run", side_effect=fake_run), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["--disk", "/dev/vda", "--yes", "--dry-run"])
        self.assertEqual(code, util.EXIT_PACKAGES)
        self.assertIn(str(dest), out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
