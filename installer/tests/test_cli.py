"""CLI：阶段解析、密码怎么进来、dry-run 一行都不许动。

dry-run 是这套东西的「安全演示」：它必须在**没装 pyparted、也不是 root** 的
机器上照跑 —— 那正是「先把命令看一遍再动手」的用途。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import unittest
from unittest import mock

from mipl_installer import cli, util
from mipl_installer.util import EXIT_USAGE, InstallerError


def _args(**overrides) -> argparse.Namespace:
    base = dict(user="mipl", password_stdin=False, dry_run=False)
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

    def test_missing_disk_argument_is_argparse_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--dry-run"])
        self.assertEqual(ctx.exception.code, EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
