"""CLI：阶段解析、密码怎么进来、dry-run 一行都不许动。

dry-run 是这套东西的「安全演示」：它必须在**没装 pyparted、也不是 root** 的
机器上照跑 —— 那正是「先把命令看一遍再动手」的用途。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mipl_installer import cli, pipeline, util
from mipl_installer.util import EXIT_USAGE, InstallerError


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
        with self.assertRaises(InstallerError) as ctx:
            cli.read_passwords(_args(root_password_stdin=True))
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

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
            "pacstrap -C /etc/pacman.conf -G -M /mnt",
            "arch-chroot /mnt locale-gen",
            "arch-chroot /mnt mkinitcpio -P",
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


class TestLogLocations(unittest.TestCase):
    """失败收尾里那句「日志在哪」：只报**确实存在**的文件，不报推测出来的路径。"""

    def _args(self, log=None, target="/mnt"):
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


if __name__ == "__main__":
    unittest.main()
