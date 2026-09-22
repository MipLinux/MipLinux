"""`util` 这一层本身的测试 —— 它是所有外部命令的唯一出口，自己坏了最难查。

这里跑的是**真命令**（`/bin/true`、`/bin/false`）：`Runner` 的职责就是把 subprocess 包对，
用假的替身测它就等于什么都没测。dry-run 那几条则要证明「真的没执行」。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import util
from mipl_installer.util import EXIT_GUARD, EXIT_USAGE, InstallerError, Runner
from tests.support import RecordingReporter


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = Runner(self.reporter)

    def test_runs_and_records_the_command(self):
        self.runner.run(["true"])
        self.assertEqual(self.runner.history, [["true"]])
        self.assertIn("$ true", self.reporter.text())

    def test_failure_carries_the_exit_code_it_was_given(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["false"], exit_code=EXIT_GUARD)
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)

    def test_check_false_does_not_raise(self):
        self.runner.run(["false"], check=False)          # 有退路的场合用它

    def test_capture_returns_stdout_without_the_trailing_newline(self):
        self.assertEqual(self.runner.run(["printf", "hi\n"], capture=True), "hi")

    def test_capture_includes_stderr_in_the_error_message(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["sh", "-c", "echo 出事 >&2; exit 3"], capture=True)
        self.assertIn("出事", str(ctx.exception))
        self.assertIn("退出码 3", str(ctx.exception))

    def test_missing_program_is_a_usage_error(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["definitely-not-a-real-program-xyz"])
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)
        self.assertIn("找不到命令", str(ctx.exception))

    def test_attempt_reports_boolean_instead_of_raising(self):
        self.assertTrue(self.runner.attempt(["true"]))
        self.assertFalse(self.runner.attempt(["false"]))

    def test_require_passes_when_everything_is_there(self):
        self.runner.require(["true", "false"])

    def test_require_names_what_is_missing(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.require(["definitely-not-a-real-program-xyz"])
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)
        self.assertIn("definitely-not-a-real-program-xyz", str(ctx.exception))


class TestDryRun(unittest.TestCase):
    def test_run_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "should-not-exist"
            runner = Runner(RecordingReporter(), dry_run=True)
            runner.run(["touch", str(victim)])
            self.assertEqual(runner.history, [["touch", str(victim)]])   # 命令记下来了
            self.assertFalse(victim.exists())                            # 但没真的跑

    def test_capture_returns_the_placeholder(self):
        runner = Runner(RecordingReporter(), dry_run=True)
        self.assertEqual(runner.run(["blkid"], capture=True), util.DRY)

    def test_attempt_is_optimistic(self):
        runner = Runner(RecordingReporter(), dry_run=True)
        self.assertTrue(runner.attempt(["false"]))

    def test_write_text_only_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "fstab"
            reporter = RecordingReporter()
            util.write_text(Runner(reporter, dry_run=True), str(victim), "UUID=…\n")
            self.assertFalse(victim.exists())
            self.assertIn("UUID=…", reporter.text())        # 内容预览打出来给人看


class TestWriteText(unittest.TestCase):
    def test_writes_content_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "10-wheel"
            util.write_text(Runner(RecordingReporter()), str(path), "x\n", mode=0o440)
            self.assertEqual(path.read_text(encoding="utf-8"), "x\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o440)

    def test_secret_content_is_never_printed(self):
        """密码这类内容连 dry-run 的预览都不许出现 —— 日志是要给人看、要进仓库的。"""
        with tempfile.TemporaryDirectory() as tmp:
            reporter = RecordingReporter()
            util.write_text(Runner(reporter, dry_run=True), f"{tmp}/.pw", "mipl:s3cret\n", secret=True)
            self.assertNotIn("s3cret", reporter.text())
            self.assertIn("内容不打印", reporter.text())


class TestSmallHelpers(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(util.human_size(1024 ** 3), "1.0 GiB")
        self.assertEqual(util.human_size(512 * 1024 ** 2), "512.0 MiB")
        self.assertEqual(util.human_size(1024), "1024 B")

    def test_is_block_device_rejects_non_devices(self):
        self.assertFalse(util.is_block_device("/dev/null"))    # 字符设备
        self.assertFalse(util.is_block_device("/tmp"))         # 目录
        self.assertFalse(util.is_block_device("/nonexistent"))

    def test_is_partition_rejects_a_whole_device(self):
        self.assertFalse(util.is_partition("/dev/null"))

    def test_chroot_argv_prefixes_arch_chroot(self):
        self.assertEqual(util.chroot_argv("/mnt", ["locale-gen"]), ["arch-chroot", "/mnt", "locale-gen"])

    def test_error_render_shows_the_hint(self):
        text = InstallerError("出事了", EXIT_GUARD, hint="那么办").render()
        self.assertIn("出事了", text)
        self.assertIn("那么办", text)


if __name__ == "__main__":
    unittest.main()
