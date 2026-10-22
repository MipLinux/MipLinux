"""`util` 这一层本身的测试 —— 它是所有外部命令的唯一出口，自己坏了最难查。

这里跑的是**真命令**（`/bin/true`、`/bin/false`）：`Runner` 的职责就是把 subprocess 包对，
用假的替身测它就等于什么都没测。dry-run 那几条则要证明「真的没执行」。
"""

from __future__ import annotations

import os
import shlex
import signal
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

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

    def test_capture_with_input_actually_reaches_the_child(self):
        """**回归测试**：`capture=True` 又给了 `input` 时，两个管子参数会打架。

        `subprocess.run` 同时收到 `input=` 与 `stdin=` 会直接抛
        `ValueError: stdin and input arguments may not both be used.` —— 实机症状是
        「网络页上点连接必报错」，而这正是 `nmcli --ask`（密码走 stdin）唯一走的那条路。
        """
        self.assertEqual(
            self.runner.run(["sh", "-c", "read line; printf 'got:%s' \"$line\""],
                            capture=True, input="pw\n"),
            "got:pw",
        )

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

    def test_empty_argv_is_a_usage_error_not_an_index_error(self):
        for method in (self.runner.run, self.runner.attempt):
            with self.subTest(method=method.__name__):
                with self.assertRaises(InstallerError) as ctx:
                    method([])
                self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_attempt_does_not_let_the_child_read_the_backend_stdin(self):
        """**回归测试**：`attempt` 原来是 `subprocess.run(input=None)`，stdin 直接继承。

        后端的 stdin 走着密码（`--password-stdin`），子进程读到就会把密码字节吞掉。
        这里把父进程的 fd 0 换成一只有内容的管子，再看子进程读不读得到 ——
        旧实现会读到，新实现只看到 EOF。
        """
        with tempfile.TemporaryDirectory() as tmp:
            seen = Path(tmp) / "seen-on-stdin"
            read_fd, write_fd = os.pipe()
            saved = os.dup(0)
            try:
                os.write(write_fd, b"parent-stdin-secret\n")
                os.close(write_fd)
                os.dup2(read_fd, 0)
                os.close(read_fd)
                self.assertTrue(self.runner.attempt(["sh", "-c", f"cat > {shlex.quote(str(seen))}"]))
            finally:
                os.dup2(saved, 0)
                os.close(saved)
            self.assertEqual(seen.read_text(encoding="utf-8"), "",
                             "attempt 的子进程读到了后端 stdin —— 那上面走着密码")


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

    def test_mode_is_applied_before_the_content_is_written(self):
        """**回归测试**：密码 / sudoers 的权限不许「先写内容、后 chmod」。

        旧实现是 `Path.write_text()` 再 `os.chmod()`：两步之间，文件里已经是
        明文密码、权限却还是 umask 给的 0644。这里用一个「刚拿到句柄就统计权限、
        然后停在写内容之前」的 `os.fdopen` 把那一刻按住。
        """
        seen: dict[str, int] = {}

        def spy(fd, *_args, **_kwargs):
            seen["mode"] = os.fstat(fd).st_mode & 0o777
            raise OSError("停在写内容之前")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("mipl_installer.util.os.fdopen", side_effect=spy):
            path = Path(tmp) / "shadow"
            with self.assertRaises(OSError):
                util.write_text(Runner(RecordingReporter()), str(path), "mipl:s3cret\n",
                                mode=0o600, secret=True)
        self.assertEqual(seen["mode"], 0o600,
                         "内容还没写，权限就已经该是 0600 —— 中间不许有 0644 的窗口")

    def test_a_failed_write_leaves_the_old_content_untouched(self):
        """**回归测试**（评审指出）：半途失败不许在目标路径留下截断的配置文件。

        旧实现直接 `O_TRUNC` 打开目标：`fdopen` / 写内容失败时，旧配置已经被截成
        0 字节。先写同目录临时文件、成功后再 `os.replace`，目标就只会是旧内容。
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pacman.conf"
            path.write_text("旧内容\n", encoding="utf-8")
            with mock.patch("mipl_installer.util.os.fdopen", side_effect=OSError("写不进去")):
                with self.assertRaises(OSError):
                    util.write_text(Runner(RecordingReporter()), str(path), "新内容\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "旧内容\n")
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["pacman.conf"],
                             "失败后临时文件也不许留在目标目录里")

    def test_the_rename_is_flushed_through_the_parent_directory_fd(self):
        """**回归测试**（评审指出）：只 fsync 内容不够，改名后的目录项也要落盘。

        `os.replace` 改的是目录项，临时文件的内容 fsync 管不到它：断电后目录项可能
        退回改名之前，fstab / pacman.conf 就成了「写成功、重启又变回旧内容」。
        """
        real_fsync = os.fsync
        directory_fsyncs: list[bool] = []

        def spy(fd):
            directory_fsyncs.append(stat.S_ISDIR(os.fstat(fd).st_mode))
            real_fsync(fd)

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("mipl_installer.util.os.fsync", side_effect=spy):
            path = Path(tmp) / "etc" / "pacman.conf"
            util.write_text(Runner(RecordingReporter()), str(path), "[options]\n")

        self.assertEqual(directory_fsyncs, [False, True],
                         "先 fsync 内容（普通文件），再 fsync 父目录（让改名落盘）")

    def test_replacing_an_existing_file_keeps_its_mode(self):
        """`mode=None` 覆盖已有文件时，权限要照旧 —— 别被临时文件的 umask 改掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hostname"
            path.write_text("旧\n", encoding="utf-8")
            os.chmod(path, 0o600)
            util.write_text(Runner(RecordingReporter()), str(path), "新\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "新\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_replacing_restores_ownership_before_mode_and_content(self):
        for mode in (None, 0o440):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "hostname"
                path.write_text("旧\n", encoding="utf-8")
                os.chmod(path, 0o640)
                metadata = list(path.stat())
                metadata[4:6] = [1234, 5678]  # 模拟其他属主 / 属组，不要求 root。
                calls = mock.Mock()
                with mock.patch("mipl_installer.util.os.lstat", return_value=os.stat_result(metadata)), \
                        mock.patch("mipl_installer.util.os.fchown") as chown, \
                        mock.patch("mipl_installer.util.os.fchmod", wraps=os.fchmod) as chmod, \
                        mock.patch("mipl_installer.util.os.fdopen", wraps=os.fdopen) as fdopen:
                    calls.attach_mock(chown, "chown")
                    calls.attach_mock(chmod, "chmod")
                    calls.attach_mock(fdopen, "fdopen")
                    util.write_text(Runner(RecordingReporter()), str(path), "新\n", mode=mode)
                self.assertEqual(calls.mock_calls, [
                    mock.call.chown(mock.ANY, 1234, 5678),
                    mock.call.chmod(mock.ANY, 0o640 if mode is None else mode),
                    mock.call.fdopen(mock.ANY, "w", encoding="utf-8"),
                ])
                self.assertEqual(path.read_text(encoding="utf-8"), "新\n")
                self.assertEqual(path.stat().st_mode & 0o777, 0o640 if mode is None else mode)

    def test_failed_ownership_change_keeps_original_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hostname"
            path.write_text("旧\n", encoding="utf-8")
            with mock.patch("mipl_installer.util.os.fchown", side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    util.write_text(Runner(RecordingReporter()), str(path), "新\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "旧\n")
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_a_symlink_is_refused_instead_of_written_through(self):
        """**回归测试**：root 不许跟着目标盘里的符号链接改写别的文件。

        `<target>/etc/pacman.conf -> /etc/pacman.conf` 这种绝对链接在宿主侧解析到
        **Live 的** /etc：`Path.write_text` 跟着写，就等于越过目标盘改了正在运行的
        系统。`--steps configure` 续跑时目标盘内容不一定是安装器刚铺的。
        """
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "host-file"
            victim.write_text("原样\n", encoding="utf-8")
            link = Path(tmp) / "target-file"
            link.symlink_to(victim)
            with self.assertRaises(InstallerError) as ctx:
                util.write_text(Runner(RecordingReporter()), str(link), "覆盖\n", mode=0o644)
            self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
            self.assertIn("符号链接", str(ctx.exception))
            self.assertEqual(victim.read_text(encoding="utf-8"), "原样\n")

    def test_a_symlinked_parent_directory_is_refused(self):
        """**回归测试**（#174）：父目录是符号链接时，root 不许写穿到目标盘外。

        只对最后一个分量上 `O_NOFOLLOW` 挡不住 `<root>/etc/foo -> <victim>`：
        写 `<root>/etc/foo/x` 时，`foo` 是**父目录**、不是终点，旧实现会在
        victim 里凭空造出 `x` —— 一次越过目标盘的根写入。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "etc").mkdir(parents=True)
            victim = Path(tmp) / "victim"
            victim.mkdir()
            sentinel = victim / "keep"
            sentinel.write_text("原样\n", encoding="utf-8")
            link = root / "etc" / "foo"
            link.symlink_to(victim)

            with self.assertRaises(InstallerError) as ctx:
                util.write_text(Runner(RecordingReporter()), str(link / "x"), "覆盖\n")
            self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
            self.assertIn("符号链接", str(ctx.exception))
            self.assertIn(str(link), str(ctx.exception),
                          "报错要说清父链上是哪一级链接，只给终点路径没法排错")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "原样\n")
            self.assertEqual(sorted(p.name for p in victim.iterdir()), ["keep"],
                             "写入顺着父目录链接落到了目标盘外")

    def test_a_symlink_higher_up_the_parent_chain_is_refused(self):
        """父链不止最后一级：`<root>/var -> ../victim` 时 `<root>/var/lib/x` 也拒绝。

        链接的目标故意写成相对路径 —— 逐级 `openat` 的判据必须看 `lstat` 的结果，
        而不是「绝对路径里有没有一处像链接」。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            victim = Path(tmp) / "victim"
            victim.mkdir()
            (root / "var").symlink_to(Path("..") / "victim")

            with self.assertRaises(InstallerError) as ctx:
                util.write_text(Runner(RecordingReporter()), str(root / "var/lib/app/x"), "x\n")
            self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
            self.assertIn(str(root / "var"), str(ctx.exception))
            self.assertEqual(list(victim.iterdir()), [],
                             "父链上更靠上的链接被跟随后，victim 里被建出了目录")

    def test_a_normal_parent_chain_is_created_and_written(self):
        """逐级打开不该误伤正常路径：`<root>/etc/...` 缺失的目录仍然照建照写。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            path = root / "etc" / "pacman.d" / "mirrorlist"
            util.write_text(Runner(RecordingReporter()), str(path), "Server = x\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "Server = x\n")
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["mirrorlist"],
                             "正常写入在目标目录里留下了临时文件")


class TestLineFeeder(unittest.TestCase):
    """进度条类工具的控制字符不许漏进日志 / 界面（Issue #97 的豆腐块）。"""

    def feed_all(self, *chunks):
        feeder = util.LineFeeder()
        lines = []
        for chunk in chunks:
            lines += feeder.feed(chunk)
        return lines + feeder.flush()

    def test_backspace_erases_the_previous_character(self):
        # mke2fs 进度条的真形态：写计数 → \b 擦掉它 → 空格盖 → 再擦 → 写 done
        raw = "Allocating group tables: 0/465" + "\b" * 5 + " " * 5 + "\b" * 5 + "done\n"
        self.assertEqual(self.feed_all(raw), ["Allocating group tables: done"])

    def test_carriage_return_overwrites_from_column_zero(self):
        self.assertEqual(self.feed_all("downloading 10%\rdownloading 100%\n"), ["downloading 100%"])

    def test_ansi_escapes_are_dropped(self):
        self.assertEqual(self.feed_all("\x1b[1m==>\x1b[0m Generating module dependencies\n"),
                         ["==> Generating module dependencies"])

    def test_other_control_characters_are_dropped(self):
        self.assertEqual(self.feed_all("a\x07b\x0bc\n"), ["abc"])

    def test_chunks_split_mid_line_are_stitched(self):
        self.assertEqual(self.feed_all("hello ", "world\n"), ["hello world"])

    def test_multibyte_text_split_mid_line_is_stitched(self):
        self.assertEqual(self.feed_all("正在分配组", "表：完成\n"), ["正在分配组表：完成"])

    def test_flush_returns_the_trailing_half_line(self):
        self.assertEqual(self.feed_all("no trailing newline"), ["no trailing newline"])

    def test_clean_terminal_text_joins_the_clean_lines(self):
        self.assertEqual(util.clean_terminal_text("one\r1\ntwo\n"), "1\ntwo")


class TestStreamedOutput(unittest.TestCase):
    """`Runner.run` 的非捕获路径：输出洗干净当旁白，一个字符都不许漏进本进程 stdout。"""

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = Runner(self.reporter)

    def test_subprocess_output_becomes_notes(self):
        self.runner.run(["sh", "-c", "printf 'hi\\nthere\\n'"])
        self.assertEqual(self.reporter.notes, ["hi", "there"])

    def test_output_is_forwarded_as_it_arrives_not_at_eof(self):
        """**回归测试**：日志必须一行一行到，不能攒到进程退出才一次性吐。

        旧实现是 `out.read(4096)` —— 文本管道的 `read(n)` 要**攒满 n 个字符或等到
        EOF** 才返回（实测：三行分 0.8 秒输出，1.21 秒才一次性到达）。于是
        `stdbuf -oL` 那条行缓冲白做，界面上的日志一段一段的、initramfs 那几分钟
        一句话都不来（实机反馈）。这条用例看的是**两行之间的到达间隔**，不是内容。
        """

        class Timed(RecordingReporter):
            def __init__(self):
                super().__init__()
                self.stamps = []

            def note(self, message):
                super().note(message)
                self.stamps.append(time.monotonic())

        reporter = Timed()
        Runner(reporter).run(["sh", "-c", "echo 第一行; sleep 0.5; echo 第二行"])
        self.assertEqual(reporter.notes, ["第一行", "第二行"])
        self.assertGreaterEqual(
            reporter.stamps[1] - reporter.stamps[0], 0.35,
            "第二行跟着第一行一起到了 —— 输出被攒到 EOF 才转发（read(4096) 的老毛病）",
        )

    def test_progress_control_characters_are_cleaned_before_the_reporter(self):
        self.runner.run(["sh", "-c", "printf '0/465\\b\\b\\b\\b\\bdone\\n'"])
        self.assertEqual(self.reporter.notes, ["done"])

    def test_stderr_is_merged_into_the_notes(self):
        self.runner.run(["sh", "-c", "echo out; echo err >&2"])
        self.assertEqual(sorted(self.reporter.notes), ["err", "out"])

    def test_attempt_swallows_the_output(self):
        self.assertTrue(self.runner.attempt(["sh", "-c", "echo leak"]))
        self.assertEqual(self.reporter.notes, [])

    def test_failure_detail_is_cleaned(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["sh", "-c", "printf 'bad\\rgood\\n' >&2; exit 2"], capture=True)
        self.assertIn("good", str(ctx.exception))
        self.assertNotIn("\r", str(ctx.exception))

    def test_stdin_is_not_inherited_when_no_input_is_given(self):
        # 后端的 stdin 走着密码：子进程万一读 stdin 会吞密码字节，必须只看到 EOF
        self.assertEqual(self.runner.run(["cat"], capture=True), "")

    def test_input_still_reaches_the_child(self):
        self.runner.run(["cat"], input="pw\n")
        self.assertEqual(self.reporter.notes, ["pw"])

    def test_a_large_stdin_does_not_deadlock_against_the_output(self):
        """**回归测试**（A5）：读线程必须先起，再写 stdin。

        子进程边读边回显、两个方向都超过管道缓冲区时，旧实现先
        `proc.stdin.write()` 再起读线程：父进程卡在写 stdin，子进程卡在写 stdout，
        两边互相等死 —— 而且 `timeout` 管不到这一步（它包着的是 `wait()`），
        实机上就是安装永久停在一行输出上。这里一次运 1 MiB（远超默认管道缓冲）。

        外层 SIGALRM 只是兜底：实现退回去的话，这条用例**失败**而不是挂住整个套件。
        """
        payload = ("x" * 1023 + "\n") * 1024         # 1 MiB
        lines: list[str] = []

        def deadlocked(*_args: object) -> None:
            raise TimeoutError("写 stdin 与读 stdout 互相等死了")

        previous = signal.signal(signal.SIGALRM, deadlocked)
        try:
            signal.setitimer(signal.ITIMER_REAL, 30)
            self.runner.run(["sh", "-c", "cat"], input=payload,
                            on_line=lines.append, timeout=30)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        self.assertEqual(len(lines), 1024)
        self.assertEqual(sum(len(line) for line in lines), 1024 * 1023)


class TestTimeout(unittest.TestCase):
    """碰固件 NVRAM 的命令能沉默地挂几十分钟：超时必须有，且带着 reason 走退路。"""

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = Runner(self.reporter)

    def test_streamed_timeout_raises_with_reason(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["sleep", "30"], timeout=1)
        self.assertEqual(ctx.exception.reason, "timeout")
        self.assertIn("超时", str(ctx.exception))

    def test_a_sub_second_timeout_is_not_reported_as_zero(self):
        """**回归测试**：`int(0.1)` 会把 100ms 的超时印成「超时（0s）」。

        那句报错是给复盘的人看的 —— 「0 秒就超时」读起来像时钟坏了。
        """
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["sleep", "30"], timeout=0.1)
        self.assertIn("0.1s", str(ctx.exception))

    def test_capture_timeout_raises_with_reason(self):
        with self.assertRaises(InstallerError) as ctx:
            self.runner.run(["sleep", "30"], capture=True, timeout=1)
        self.assertEqual(ctx.exception.reason, "timeout")

    def test_attempt_timeout_counts_as_failure_and_says_so(self):
        self.assertFalse(self.runner.attempt(["sleep", "30"], timeout=1))
        self.assertTrue(any("超时" in note for note in self.reporter.notes))

    def test_the_timeout_covers_writing_stdin(self):
        """**回归测试**（评审指出）：`timeout` 要覆盖「喂输入」那一段。

        子进程不读 stdin 时，1 MiB 输入会卡在写满的管道上；写在主线程里的话
        `wait(timeout=…)` 根本没开始计时 —— 命令与整组进程一直留着，超时不生效。
        外层 SIGALRM 兜底：实现退回去时用例失败而不是挂住套件。
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            argv = ["sh", "-c", f"(sleep 1; printf late > {shlex.quote(str(marker))}) & sleep 30"]

            def stuck(*_args: object) -> None:
                # 用 RuntimeError 而不是 TimeoutError：后者是 OSError 的子类，
                # 实现退回到「主线程直接写」时会被那一层的 `except OSError` 吞掉。
                raise RuntimeError("写 stdin 阻塞时 timeout 没有生效")

            previous = signal.signal(signal.SIGALRM, stuck)
            started = time.monotonic()
            try:
                signal.setitimer(signal.ITIMER_REAL, 10)
                with self.assertRaises(InstallerError) as ctx:
                    self.runner.run(argv, input="x" * (1024 * 1024), timeout=0.3)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
            self.assertEqual(ctx.exception.reason, "timeout")
            self.assertLess(time.monotonic() - started, 5.0,
                            "写 stdin 阻塞时 timeout 没有生效")
            time.sleep(1.1)
            self.assertFalse(marker.exists(),
                             f"超时返回后后代进程还写了 {marker}")

    def test_history_records_the_logical_argv_without_stdbuf(self):
        # stdbuf 只存在于 exec 的那一层：history 与 reporter.command 记的是逻辑命令
        self.runner.run(["true"])
        self.assertEqual(self.runner.history, [["true"]])
        self.assertIn("$ true", self.reporter.text())


class TestProcessGroupOnTimeout(unittest.TestCase):
    """**回归测试**（#152 跨线发现）：超时只杀直接子进程，后代还在跑。

    复现方式与那条发现一致，但不需要 root、不碰盘：包装 shell 里再起一个
    「过一会儿写标记文件」的后代，`timeout` 到点后 Runner 返回 —— 此时整组都
    该停，标记文件不许出现。旧实现只 `proc.kill()` 直接子进程，后代照写不误
    （`arch-chroot` 包装下的 bootctl / efibootmgr 就是这个形态：超时返回后
    旧的还在碰 NVRAM，新的又开一条）。
    """

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = Runner(self.reporter)

    @staticmethod
    def _deferred_write(marker: Path, delay: float = 0.6) -> list[str]:
        return ["sh", "-c", f"(sleep {delay}; printf late > {shlex.quote(str(marker))}) & wait"]

    def _assert_nothing_wrote_late(self, marker: Path) -> None:
        time.sleep(0.8)      # 比上面的 delay 长：后代活着的话，这期间一定会写
        self.assertFalse(marker.exists(),
                         f"超时返回后后代进程还写了 {marker} —— 收的只是包装器，不是整组")

    def test_streamed_timeout_kills_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            with self.assertRaises(InstallerError) as ctx:
                self.runner.run(self._deferred_write(marker), timeout=0.2)
            self.assertEqual(ctx.exception.reason, "timeout")
            self._assert_nothing_wrote_late(marker)

    def test_capture_timeout_kills_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            with self.assertRaises(InstallerError) as ctx:
                self.runner.run(self._deferred_write(marker), capture=True, timeout=0.2)
            self.assertEqual(ctx.exception.reason, "timeout")
            self._assert_nothing_wrote_late(marker)

    def test_attempt_timeout_kills_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            self.assertFalse(self.runner.attempt(self._deferred_write(marker), timeout=0.2))
            self._assert_nothing_wrote_late(marker)

    def test_a_refused_killpg_is_not_mistaken_for_a_dead_group(self):
        """**回归测试**（评审指出）：`killpg` 的 `OSError` 不等于「整组已经没了」。

        旧实现把任何 `OSError` 都当「组已退出」直接返回；调用方收尾时是无超时的
        `proc.wait()`，子进程还活着就会永久挂起。这里让 `killpg` 一律报权限错误，
        `run()` 必须仍在宽限期后收掉直接子进程并抛超时，而不是卡满 `sleep`。
        """
        started = time.monotonic()
        with mock.patch("mipl_installer.util.os.killpg",
                        side_effect=PermissionError("不许发信号")):
            with self.assertRaises(InstallerError) as ctx:
                self.runner.run(["sleep", "5"], timeout=0.1)
        elapsed = time.monotonic() - started
        self.assertEqual(ctx.exception.reason, "timeout")
        self.assertLess(elapsed, 2.5,
                        f"killpg 失败被当成杀完了，收尾卡在 wait() 上（{elapsed:.1f}s）")

    def test_the_terminate_grace_covers_the_whole_group_not_just_the_leader(self):
        """**回归测试**：SIGTERM 的宽限要给整组，不是只看组长。

        包装器（`pacstrap` / `arch-chroot`）收到 SIGTERM 会立刻退出；旧实现等的是
        `proc.wait()`（只等组长），组长一退就马上 `SIGKILL` 整组 —— 真正干活的
        `pacman` 拿不到 docstring 承诺的收尾时间，释放 `/var/lib/pacman/db.lck`
        正是在收尾里。这里让组长秒退、后代忽略 SIGTERM 再用 0.4s 写标记：宽限只看
        组长的话，标记永远写不出来（旧实现会在几毫秒内把它杀掉）。

        忽略处置在 shell 里设、由 `exec` 继承（POSIX：被忽略的信号跨 exec 保留），
        不留给 Python 去装 handler —— 那只解释器启动的几十毫秒里，0.25s 的 SIGTERM
        可能先到，用例就会假失败。外层 shell 设完再恢复默认：它自己必须照常死在
        SIGTERM 上，被测的正是「组长已退、组员还在」。
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "cleaned"
            helper = Path(tmp) / "slow_cleanup.py"
            helper.write_text(
                "import sys, time, pathlib\n"
                "time.sleep(0.4)\n"
                "pathlib.Path(sys.argv[1]).write_text('cleaned')\n",
                encoding="utf-8",
            )
            argv = ["sh", "-c",
                    "trap '' TERM; "
                    f"( exec {shlex.quote(sys.executable)} {shlex.quote(str(helper))} "
                    f"{shlex.quote(str(marker))} ) & "
                    "trap - TERM; wait"]
            with self.assertRaises(InstallerError) as ctx:
                self.runner.run(argv, timeout=0.25)
            self.assertEqual(ctx.exception.reason, "timeout")
            self.assertTrue(marker.exists(),
                            "组长一退就 SIGKILL 了整组 —— 真正干活的进程没拿到那 0.5s 收尾")


class TestStreamedReader(unittest.TestCase):
    """读线程自己的边界：后代握着管道不许把安装挂死，回调的异常不许被线程吞掉。"""

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = Runner(self.reporter)

    def test_a_descendant_that_keeps_stdout_open_does_not_hang_the_run(self):
        """**回归测试**：直接子进程退出后，后代仍握着 stdout 时不许陪它等下去。

        旧实现把 `pump()` 放在主线程里读，读到 EOF 才 `wait()`：`sh -c '… & exit 0'`
        留下的后台进程只要还开着管道，安装器就停在那一行输出上（本次单测里
        `(sleep 5) & exit 0` 会让 `run()` 整整等 5 秒）。
        """
        started = time.monotonic()
        self.runner.run(["sh", "-c", "(sleep 5) & exit 0"])
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0,
                        f"直接子进程早就退了，run() 却在等后代放管道（{elapsed:.1f}s）")

    def test_a_callback_error_is_not_swallowed_by_the_reader_thread(self):
        """**回归测试**：`on_line` 的异常必须在调用方炸开。

        旧实现只在「带超时」那条路把读输出放进线程；线程里的异常只打印一句
        traceback，主线程照常等到超时，然后报一个假的 `reason="timeout"` ——
        调用方的 bug 变成了「固件 NVRAM 卡住」。
        """
        def boom(_line: str) -> None:
            raise RuntimeError("回调坏了")

        with self.assertRaises(RuntimeError):
            self.runner.run(["sh", "-c", "echo hi; sleep 10"], timeout=5, on_line=boom)

    def test_truncated_multibyte_tail_is_flushed_at_eof(self):
        """**回归测试**：EOF 时被切开的多字节字符不许悄悄丢掉。"""
        self.runner.run(["sh", "-c", r"printf '\344\270'"])
        self.assertEqual(self.reporter.notes, ["\ufffd"])

    def test_a_reader_that_cannot_start_still_takes_the_child_down(self):
        """**回归测试**（安全评审）：读线程起不来时，子进程也不许留在那儿跑。

        线程创建失败（资源耗尽），或中断正好落在 `start()` 上时，子进程已经
        spawn 出来了 —— 收尾必须从这一步就开始，否则它带着整组命令逃出这次安装。
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            argv = ["sh", "-c", f"(sleep 1; printf late > {shlex.quote(str(marker))}) & sleep 30"]
            with mock.patch.object(threading.Thread, "start",
                                   side_effect=RuntimeError("起不了线程")):
                with self.assertRaises(RuntimeError):
                    self.runner.run(argv)
            time.sleep(1.1)
            self.assertFalse(marker.exists(),
                             f"读线程起不来，子进程却活着写了 {marker}")


class TestInterruptStopsTheCommand(unittest.TestCase):
    """**回归测试**：Ctrl-C 之后子进程不许继续跑。

    `start_new_session` 让子进程脱离了终端的进程组 —— 终端上的 SIGINT 只有安装器
    收到，`pacstrap` / `mkfs` 收不到。不在中断路径上主动收整组的话，收尾卸载目标
    时它们还在往那块盘上写；比「没装完」更糟。这里用 SIGALRM 在等待中途制造一次
    `KeyboardInterrupt`（与 Ctrl-C 走同一条 Python 路径）。
    """

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = Runner(self.reporter)

    @staticmethod
    def _deferred_write(marker: Path, delay: float = 1.0) -> list[str]:
        return ["sh", "-c", f"(sleep {delay}; printf late > {shlex.quote(str(marker))}) & wait"]

    @staticmethod
    def _raise_interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    def _run_interrupted(self, argv: list[str], **kwargs) -> None:
        previous = signal.signal(signal.SIGALRM, self._raise_interrupt)
        try:
            signal.setitimer(signal.ITIMER_REAL, 0.4)
            with self.assertRaises(KeyboardInterrupt):
                self.runner.run(argv, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)

    def _assert_nothing_wrote_late(self, marker: Path) -> None:
        time.sleep(1.1)
        self.assertFalse(marker.exists(),
                         f"中断返回后后代进程还写了 {marker} —— 子进程没跟着停下来")

    def test_streamed_interrupt_takes_the_child_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            self._run_interrupted(self._deferred_write(marker))
            self._assert_nothing_wrote_late(marker)

    def test_capture_interrupt_takes_the_child_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            self._run_interrupted(self._deferred_write(marker), capture=True)
            self._assert_nothing_wrote_late(marker)

    def test_interrupt_during_stdin_delivery_takes_the_child_down(self):
        """**回归测试**：写 stdin 还没写完时来了中断，也要收整组。

        子进程不读 stdin 时，1 MiB 输入会把写线程卡在管道上（旧实现是主线程自己
        卡在 `write()` 里）。中断落在这一段时，子进程必须跟着停 —— 它留在自己的
        会话里的话，收尾卸载目标时还在往盘上写。
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late"
            argv = ["sh", "-c", f"(sleep 1; printf late > {shlex.quote(str(marker))}) & sleep 30"]
            self._run_interrupted(argv, input="x" * (1024 * 1024))   # 远大于管道缓冲
            self._assert_nothing_wrote_late(marker)


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

    def test_size_of_device_reports_a_guard_instead_of_a_raw_oserror(self):
        """**回归测试**：盘路径打错时原来漏出裸的 `FileNotFoundError`。

        CLI 的兜底把它报成「未预期的异常」（退出码 7 + traceback），可它其实
        只是「这块盘不存在」—— 要给与 `disk.assert_usable` 同一条守卫
        （`reason="notBlockDevice"`，界面拿它挑自己的句子）。
        """
        with self.assertRaises(InstallerError) as ctx:
            util.size_of_device("/tmp/definitely-not-a-block-device")
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
        self.assertEqual(ctx.exception.reason, "notBlockDevice")
        self.assertIn("不是块设备", str(ctx.exception))

    def test_chroot_argv_prefixes_arch_chroot(self):
        self.assertEqual(util.chroot_argv(util.DEFAULT_TARGET, ["locale-gen"]),
                         ["arch-chroot", util.DEFAULT_TARGET, "locale-gen"])

    def test_error_render_shows_the_hint(self):
        text = InstallerError("出事了", EXIT_GUARD, hint="那么办").render()
        self.assertIn("出事了", text)
        self.assertIn("那么办", text)


if __name__ == "__main__":
    unittest.main()
