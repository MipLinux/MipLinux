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

import codecs
import errno
import os
import signal
import stat
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

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

#: 装系统时目标挂载在哪。**专用子目录，不是 `/mnt` 本身** —— 归属由路径判定：
#: `/mnt` 上可能是用户自己挂的盘，而这个名字下面只可能是安装器留下的（#105）。
#: 默认值只有这一处，其余模块一律引它。
DEFAULT_TARGET = "/mnt/mipl"


class InstallerError(Exception):
    """带退出码的失败。消息面向用户，hint 是「接下来敲什么」。

    `reason` 是给**界面**用的机器可读代码（`format` / `notInList` / `notFound` …）：
    界面有一份自己的文案表（中/英），不能把后端这句中文直接摆上去 —— 英文模式会露馅。
    有 `reason` 时界面走它自己的句子，没有就当普通失败只显示消息。
    **只有校验类失败需要它**；装包/引导那些失败的文案本来就不翻译。
    """

    def __init__(
        self,
        message: str,
        exit_code: int = EXIT_UNEXPECTED,
        hint: str | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.hint = hint
        self.reason = reason

    def render(self) -> str:
        text = str(self)
        return f"{text}\n  → {self.hint}" if self.hint else text


class DirectorySyncError(InstallerError):
    """写入已经替换目标文件，但父目录 fsync 失败 —— 一次**部分提交**。

    `write_text` 先 `os.replace` 成功、再 `fsync` 父目录；后者失败时，目标路径上
    **已经是新内容**，只是目录项能不能扛住断电还没有确认。它和「没写进去」不是
    一回事：调用方不能按「目标文件还是旧内容」处理，也不能吞掉这次失败。
    """


#: 一条命令跑满多少秒就在日志里留一句「耗时 Ns」。这一句是给实机复盘用的：
#: 「二十分钟花在哪了」该由日志回答，不该由截图猜（Issue #97 实机教训）。
SLOW_COMMAND_SECONDS = 15

#: 直接子进程退出后，读线程再等多久收尾。正常命令这时候早就 EOF（毫秒级）；
#: 等不到说明有后代还握着 stdout（`cmd &` 之类）——再等下去就是替它陪葬。
DRAIN_GRACE_SECONDS = 1.0

#: 停一整组进程时，SIGTERM 与 SIGKILL 之间给多久收尾。
TERMINATE_GRACE_SECONDS = 0.5


class LineFeeder:
    """把子进程的输出切成「干净的可读行」。

    进度条类工具（mke2fs、pacman、mkinitcpio）会对终端耍三种花活：`\\b` 擦掉前一个
    字符、`\\r` 回到行首覆写、ANSI 转义序列改颜色。这些都不是内容 —— 原样漏进日志或
    界面，轻则满屏豆腐块（Issue #97 的实机教训：mke2fs 的 `\\b` 在安装日志里画成方块），
    重则把 JSON 事件流冲垮。在这里把它们**当场应用掉**，出来的就是普通文本行。
    """

    def __init__(self) -> None:
        self._current: list[str] = []
        #: text | esc | csi | osc —— 转义序列的三个状态，免得序列跨块时被当成内容
        self._state = "text"

    def feed(self, chunk: str) -> list[str]:
        """吃一块输出，返回其中**完整**的行（半行留着跟下一块拼）。"""
        lines: list[str] = []
        for ch in chunk:
            if self._state == "esc":
                self._state = "csi" if ch == "[" else "osc" if ch == "]" else "text"
            elif self._state == "csi":
                if 0x40 <= ord(ch) <= 0x7E:      # CSI 的终止字节
                    self._state = "text"
            elif self._state == "osc":
                if ch == "\x07":
                    self._state = "text"
                elif ch == "\x1b":
                    self._state = "esc"
            elif ch == "\x1b":
                self._state = "esc"
            elif ch == "\n":
                lines.append("".join(self._current).rstrip())
                self._current = []
            elif ch == "\r":
                self._current = []               # 回行首：接下来的内容整行覆写
            elif ch == "\b":
                if self._current:
                    self._current.pop()          # 擦掉前一个字符
            elif ch == "\t" or (ord(ch) >= 0x20 and ch != "\x7f"):
                self._current.append(ch)
            # 其余 C0 控制字符（响铃、竖制表……）：不是内容，直接丢
        return lines

    def flush(self) -> list[str]:
        """输出结束时剩下的半行（有的工具收尾不补换行）。"""
        line = "".join(self._current).rstrip()
        self._current = []
        return [line] if line else []


def clean_terminal_text(text: str) -> str:
    """把一整块已捕获的输出过一遍 `LineFeeder`（报错消息之类用）。"""
    feeder = LineFeeder()
    lines = feeder.feed(text) + feeder.flush()
    return "\n".join(line for line in lines if line)


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
        timeout: float | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> str | None:
        """跑一条命令。

        capture=True 时返回 stdout（去掉尾部换行）；dry-run 下返回 `DRY`。
        check=True 时非零退出码抛 `InstallerError`（带 exit_code）。
        capture=False 时**输出逐行清洗后交给 reporter**（见 `_run_streamed`），绝不继承
        本进程的 stdout：界面下 stdout 是 JSON 事件流，混进一行原文就是满屏
        「后端输出无法解析」。
        `input` 给了就写进子进程的 stdin（配合 capture=True 用）—— 密码那条红线：
        argv 会留在进程列表与日志里，所以「问一句答一句」的命令走它。
        `on_line` 给「要**边跑边读**输出」的调用方用（pacman 的 `(14/345)` 就是
        这么变成细进度的）：每清洗出一行回调一次，**在**它被当旁白记下来之前。
        只在流式路径（`capture=False`）上有意义 —— 捕获路径要收完才返回。
        timeout 给了就超时杀进程并抛 `reason="timeout"` 的 `InstallerError` ——
        给**会去碰固件 NVRAM 的命令**用的：固件变量存储卡住时那些命令能沉默地
        挂几十分钟（实机教训：引导阶段挂 40 分钟），安装器不该陪着等。
        **超时覆盖整条命令**，包括把 `input` 写进 stdin 的那一段：子进程不读 stdin
        时，那一写会卡在写满的管道上 —— 写在主线程里的话 `wait(timeout=…)` 根本
        没机会开始计时（评审指出）。流式路径的写因此交给线程。
        **杀的是整组进程，不只是直接子进程**：`arch-chroot` / `stdbuf` 这类包装器
        下面干活的进程、以及它们再生的后代，全在同一个会话里（`start_new_session`）——
        只杀包装器会留下一群还在写盘 / 还在碰 NVRAM 的孤儿，超时返回后它们与
        下一条命令重叠执行（#151 跨线发现的那一幕）。

        **`input` 与 `stdin=` 不能同时给** `subprocess.run`（它自己会抛
        `ValueError: stdin and input arguments may not both be used.`）。所以这里
        按「给没给 input」二选一：给了就走 `input=`（它内部会接 PIPE），
        没给才显式接 `DEVNULL` —— 后端的 stdin 走着密码，子进程万一去读 stdin
        会把密码字节吞掉（与 `_run_streamed` 同一条纪律）。
        """
        argv = [str(a) for a in argv]
        if not argv:
            raise InstallerError("空命令：没有可执行的东西", EXIT_USAGE,
                                 hint="argv 至少要有程序名")
        self.history.append(argv)
        self.reporter.command(argv)
        if self.dry_run:
            return DRY if capture else None

        # 先查工具在不在：流式路径套了 stdbuf 之后，「命令不存在」会变成 stdbuf
        # 退出 127 —— 那句报错对不上事实（该说「装哪个包」而不是「命令失败」）
        if not self.have(argv[0]):
            raise InstallerError(
                f"找不到命令：{argv[0]}",
                EXIT_USAGE,
                hint="这个命令属于哪个包见 cli.py 的 TOOL_PACKAGES —— 先装它，再重跑",
            )

        started = time.monotonic()
        stderr_text = ""
        try:
            if capture:
                # 给了 `input` 就接 PIPE（`communicate` 负责写进去），没给才接
                # `DEVNULL` —— 后端的 stdin 走着密码，子进程自说自话去读 stdin
                # 会把密码字节吞掉。这条纪律与 `_run_streamed` 一致。
                proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=cwd,
                    # 自己当会话 / 进程组长，超时才能连后代一起收掉（见 _terminate_process_group）
                    start_new_session=True,
                )
                try:
                    stdout, stderr_text = proc.communicate(input, timeout=timeout)
                except subprocess.TimeoutExpired as exc:
                    self._terminate_process_group(proc)
                    proc.wait()
                    # 不再 `communicate()` 收尾：真有后代逃出进程组还握着管子时，
                    # 那一下会一直等 EOF。超时路径本来就不看输出，关掉就是了。
                    self._close_pipes(proc)
                    raise self._timeout_error(argv, timeout, exit_code) from exc
                except BaseException:
                    # Ctrl-C / 进程被信号打断：子进程已经脱离终端的进程组
                    # （`start_new_session`），不会自己收到 SIGINT —— 不在这里
                    # 收掉的话，收尾卸载时它还在往盘上写。
                    self._terminate_process_group(proc)
                    proc.wait()
                    self._close_pipes(proc)
                    raise
                stdout = (stdout or "").rstrip("\n")
            else:
                proc = self._run_streamed(argv, input=input, cwd=cwd,
                                          timeout=timeout, exit_code=exit_code,
                                          on_line=on_line)
                stdout = None
        except FileNotFoundError as exc:
            raise InstallerError(
                f"找不到命令：{argv[0]}",
                EXIT_USAGE,
                hint="这个命令属于哪个包见 cli.py 的 TOOL_PACKAGES —— 先装它，再重跑",
            ) from exc
        self._note_if_slow(argv, started)

        if check and proc.returncode != 0:
            detail = ""
            if capture and stderr_text:
                detail = "：\n    " + clean_terminal_text(stderr_text).strip().replace("\n", "\n    ")
            raise InstallerError(f"命令失败（退出码 {proc.returncode}）：{' '.join(argv)}{detail}", exit_code)

        return stdout

    def _terminate_process_group(self, proc: subprocess.Popen) -> None:
        """停掉**整组**进程，而不是只停直接子进程。

        子进程一律用 `start_new_session=True` 启动，自己就是会话 / 进程组长：
        组号 = 组长 pid，所以 `killpg(proc.pid, …)` 能覆盖 `arch-chroot`、`stdbuf`
        下面的真正工作进程，以及它们再生的后代。只 `proc.kill()` 的话，超时返回时
        后代还在写标记文件 / 还在碰 NVRAM —— 新旧命令叠在一起，#152 的复现正是
        这一条（`timeout=0.15s` 返回后标记文件随后出现）。

        先 SIGTERM 给一次收尾机会，过 `TERMINATE_GRACE_SECONDS` 再 SIGKILL 兜底。
        组长可能已经先退出了，但组号只要还有组员就仍然有效 —— 所以宽限期内看的是
        **整组还有没有进程**，不是只看组长。`pacstrap` / `arch-chroot` 这类包装器
        收到 SIGTERM 会立刻退出；只对组长 `wait()` 的话，真正干活的 `pacman` /
        `bootctl` 会在几毫秒后吃到 SIGKILL —— 来不及释放 `/var/lib/pacman/db.lck`
        这类东西，续跑就被自己的锁拦在门外。

        组长每轮都要 `wait()` 回收：留着僵尸组长，`killpg(pid, 0)` 会一直报「组还在」，
        宽限期就变成固定的 `TERMINATE_GRACE_SECONDS` 硬等。

        只有 `ProcessLookupError` 才是「整组已经没了」。别的 `OSError`（信号被拒、
        参数不被接受）**不能当成杀完了**：调用方收尾时是无超时的 `proc.wait()`，
        子进程还活着就会一直等下去。这种失败照样走完宽限期，最后用 `proc.kill()`
        把直接子进程收掉兜底 —— 组员可能已经逃出进程组，但调用方不会再挂死。
        """
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return                           # 整组都没了；组长是僵尸的话交给调用方 wait()
        except OSError:
            pass                             # 信号没发出去，不是「已经杀完」：继续兜底
        deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
        while True:
            try:
                proc.wait(timeout=0.05)      # 回收组长，免得僵尸组长让组一直「存在」
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(proc.pid, 0)       # 组里还有活着的成员吗
            except ProcessLookupError:
                return                       # 整组都已退出，不必 SIGKILL
            except OSError:
                pass                         # 探不清就当作还活着，宽限期结束后再 SIGKILL
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            # 整组收不掉（不是「已经没了」）：至少把直接子进程收掉，
            # 调用方随后的 proc.wait() 才不会永久挂起。
            try:
                proc.kill()
            except ProcessLookupError:
                pass                         # 已经被别的线程回收了；收尾函数不再节外生枝

    @staticmethod
    def _close_pipes(proc: subprocess.Popen) -> None:
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe is None:
                continue
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

    def _timeout_error(self, argv: list[str], timeout: float | None, exit_code: int) -> InstallerError:
        return InstallerError(
            f"命令超时（{float(timeout or 0):g}s）：{' '.join(argv)}",
            exit_code,
            hint="固件 NVRAM 写入停滞、设备不应是常见原因；现场已保留，先看日志再按该阶段的退路绕行或重跑",
            reason="timeout",
        )

    def _run_streamed(self, argv: list[str], *, input: str | None = None, cwd: str | None = None,
                      timeout: float | None = None, exit_code: int = EXIT_UNEXPECTED,
                      on_line: Callable[[str], None] | None = None):
        """跑一条命令，输出逐行（清洗后）转发给 reporter。

        八条纪律：

        * **不继承 stdout**：mke2fs / pacman 的进度条、mkinitcpio 的旁白是给终端看的，
          直接流进本进程的 stdout，在界面下会把 JSON 事件流冲成满屏「后端输出无法解析」，
          在 CLI 下会把日志的缩进冲垮。收过来、洗干净、当旁白发，两边日志才都读得下去。
        * **不继承 stdin**：后端的 stdin 走着密码；不给 input 的子进程一律接 DEVNULL。
        * **C 工具强制行缓冲**：pacman / mke2fs 这类 C 实现的工具 stdout 接管道时是
          **全缓冲** —— 攒满 4 KiB 或进程退出才吐一次，实机症状是「一个阶段爆出一堆
          日志、随后装死」。有 stdbuf 就套 `stdbuf -oL -eL`（脚本类工具无副作用）。
        * **读用 `read1()`，不用 `read()`**：文本管道的 `read(n)` 要**攒满 n 个字符
          或等到 EOF** 才返回（实测：三行分 0.8 秒输出，1.21 秒才一次性到达）——
          于是上面那条 stdbuf 白做，日志仍然一段一段的。`read1()` 是「有多少给多少」，
          子进程吐一行就转发一行。这两个字之差就是「日志是流式还是分段」的全部原因。
        * **`on_line` 先于旁白**：想在输出里认东西的调用方（pacman 的 `(14/345)`）
          拿到的是**同一条清洗过的行**，与日志里那行一字不差；认出来的进度因此不会
          与日志对不上。回调抛异常不吞 —— 那是调用方的 bug，不该在管道里静默。
        * **读线程先起，再写 stdin**：子进程可能先吐一屏输出才来读 stdin；输出管
          写满后它就不会来读 stdin，父进程又卡在写 stdin 上 —— 两个方向互相等死。
          先起读线程，这条路就不存在。
        * **写 stdin 也交给线程**：子进程根本不读 stdin 时，大段输入会卡在写满的
          管道上。写在主线程里，超时与中断都要等这一写返回才轮得到 —— 写线程让
          `wait(timeout=…)` 照常计时，收整组之后写端拿到 EPIPE，线程自己退出。
        * **整组进程归这里管**：子进程用 `start_new_session=True` 启动。超时、或
          直接子进程退出后仍有后代握着 stdout（`cmd &`）时，收的是整组，不是只收
          那一个包装器 —— 后者会留下继续写盘的后代（#151 跨线发现）。
        """
        exec_argv = argv
        if self.have("stdbuf"):
            exec_argv = ["stdbuf", "-oL", "-eL", *argv]
        proc = subprocess.Popen(
            exec_argv,
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            cwd=cwd,
            start_new_session=True,
        )
        feeder = LineFeeder()
        #: 读线程里抛出的异常（`on_line` 的 bug、管道错）：由主线程在收尾时原样抛出。
        #: 线程里的异常只会打印一句 traceback，调用方看不见 —— 那等于吞掉。
        errors: list[BaseException] = []

        def deliver(line: str) -> None:
            if on_line is not None:
                on_line(line)
            self.reporter.note(line)

        def pump() -> None:
            out = proc.stdout
            if out is None:
                return
            # 走底层字节流：`TextIOWrapper` 上没有 read1，而它的 `read()` 正是要避开的那一个。
            # 解码用**这个流自己的编码**（`out.encoding`），与原来 text=True 的行为一致；
            # 多字节字符被管道从中间切开时，增量解码器会把它留到下一块拼起来。
            stream = getattr(out, "buffer", out)
            read1 = getattr(stream, "read1", None) or stream.read
            decoder = codecs.getincrementaldecoder(getattr(out, "encoding", None) or "utf-8")("replace")
            binary = False
            try:
                while True:
                    chunk = read1(4096)
                    if not chunk:
                        break
                    if isinstance(chunk, bytes):
                        binary = True
                        text = decoder.decode(chunk)
                    else:
                        text = chunk
                    for line in feeder.feed(text):
                        if line:
                            deliver(line)
                if binary:
                    tail = decoder.decode(b"", final=True)  # 收尾那个被切开的字符
                    for line in feeder.feed(tail):
                        if line:
                            deliver(line)
                for line in feeder.flush():
                    if line:
                        deliver(line)
            except BaseException as exc:  # noqa: BLE001 - 记下来交给主线程原样抛
                errors.append(exc)
                # 读端坏了（回调抛异常 / 管道错）：子进程没人收输出了，再等只会卡在
                # 写满的管子上 —— 停掉整组，让主线程的 wait() 立刻返回。
                self._terminate_process_group(proc)
            finally:
                try:
                    out.close()
                except OSError:
                    pass

        # 先起读线程再写 stdin（见 docstring 里「两个方向互相等死」那一条）
        reader = threading.Thread(target=pump, daemon=True)
        try:
            reader.start()
        except BaseException:
            # 线程起不来（资源耗尽，或中断正好落在 start 上）：子进程已经在跑了，
            # 不在这里收掉，它就会带着整组命令逃出这次安装。
            self._terminate_process_group(proc)
            proc.wait()
            self._close_pipes(proc)
            raise

        #: 写 stdin 的线程。写必须离开主线程：子进程不读 stdin 时，写满管道后
        #: `write()` 会一直阻塞，`wait(timeout=…)` 根本没机会开始计时 —— 那样
        #: `timeout` 就只覆盖了「等进程」，没覆盖「喂输入」。
        writer: threading.Thread | None = None

        def feed_stdin(stdin, text: str) -> None:
            try:
                stdin.write(text)
            except (OSError, ValueError):
                pass  # 子进程没读完就退了：退出码自会说话，别在这儿炸
            finally:
                try:
                    stdin.close()
                except (OSError, ValueError):
                    pass

        try:
            if input is not None and proc.stdin is not None:
                feed = threading.Thread(target=feed_stdin, args=(proc.stdin, input), daemon=True)
                feed.start()
                writer = feed

            if timeout is not None:
                proc.wait(timeout=timeout)
            else:
                proc.wait()

            # 直接子进程已经退出。正常命令这时读线程也到 EOF 了（毫秒级）；若某个
            # 后代还握着 stdout（`cmd &`），它会一直等 —— 再等就是替那个后代陪葬。
            # 给一小段收尾宽限，之后收掉整组，让读线程随管道 EOF 结束。
            reader.join(DRAIN_GRACE_SECONDS)
            if reader.is_alive():
                self._terminate_process_group(proc)
                reader.join(5)
            # 写线程同理：子进程退了但没读完 stdin 的话，写端会拿到 EPIPE 自己
            # 结束；还活着的唯一原因是某个后代攥着 stdin 读端不肯放 —— 收整组。
            if writer is not None:
                writer.join(DRAIN_GRACE_SECONDS)
                if writer.is_alive():
                    self._terminate_process_group(proc)
                    writer.join(5)
        except subprocess.TimeoutExpired:
            self._terminate_process_group(proc)
            proc.wait()
            reader.join(5)
            if writer is not None:
                writer.join(5)      # 整组收掉之后写端拿到 EPIPE，线程自己退出
            if errors:
                raise errors[0]
            raise self._timeout_error(argv, timeout, exit_code)
        except BaseException:
            # Ctrl-C / 进程被信号打断 —— 卡在写 stdin 上的那种也在内（写由写线程
            # 负责，主线程收掉整组之后它拿到 EPIPE 就退）。子进程自己开了新会话，
            # 终端上的 SIGINT 到不了它 —— 不在这里收掉，收尾卸载目标时
            # `pacstrap` / `mkfs` 还在往那块盘上写。
            self._terminate_process_group(proc)
            proc.wait()
            reader.join(5)
            if writer is not None:
                writer.join(5)
            elif proc.stdin is not None:
                # 写线程没起来（`start()` 自己失败）：stdin 还是本进程的句柄，
                # 子进程已经收掉，这一关不会卡在写满的管子上。
                try:
                    proc.stdin.close()
                except (OSError, ValueError):
                    pass
            raise
        if errors:
            raise errors[0]
        return proc

    def _note_if_slow(self, argv: list[str], started: float) -> None:
        elapsed = time.monotonic() - started
        if elapsed >= SLOW_COMMAND_SECONDS:
            self.reporter.note(f"耗时 {int(round(elapsed))}s：{' '.join(argv)}")

    def have(self, program: str) -> bool:
        from shutil import which

        return which(program) is not None

    def attempt(self, argv: list[str], *, input: str | None = None, timeout: float | None = None) -> bool:
        """跑一条命令，只回报成没成功。

        用于「失败有退路」的场合（NVRAM 写不进 → 退到可移除介质路径）。
        普通的失败路径别用它 —— 抛异常的 `run()` 才带得上退出码与提示。
        超时算失败（并留一句旁白）：碰固件的命令卡住时，退路才有意义。
        **和 `run()` 同一条 stdin 纪律**：没给 `input` 就接 `DEVNULL`，子进程读不到
        后端 stdin 上的密码；超时同样收整组进程（见 `_terminate_process_group`）。
        """
        argv = [str(a) for a in argv]
        if not argv:
            raise InstallerError("空命令：没有可执行的东西", EXIT_USAGE,
                                 hint="argv 至少要有程序名")
        self.history.append(argv)
        self.reporter.command(argv)
        if self.dry_run:
            return True
        started = time.monotonic()
        try:
            # 输出捕获后丢掉：语义是「只报成败」，但输出同样不许漏进本进程 stdout
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError:
            return False
        try:
            proc.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            self._terminate_process_group(proc)
            proc.wait()
            self._close_pipes(proc)        # 有后代逃逸时 communicate() 会等到天荒地老
            self.reporter.note(
                f"命令超时（{float(timeout or 0):g}s）：{' '.join(argv)}（按失败走退路）"
            )
            return False
        except BaseException:
            # 同 run()：新会话里的子进程收不到终端的 SIGINT，得这里收掉再抛。
            self._terminate_process_group(proc)
            proc.wait()
            self._close_pipes(proc)
            raise
        self._note_if_slow(argv, started)
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
    # 流式输出靠它把 C 工具切成行缓冲（见 Runner._run_streamed）
    "stdbuf": "coreutils",
}

#: 每个阶段需要哪些工具（开跑前一次性检查，别跑到一半才炸）
STEP_TOOLS = {
    "disk": ["parted", "partprobe", "wipefs", "udevadm", "mkfs.vfat", "mkfs.ext4",
             "mount", "umount", "blkid", "mknod", "chown", "chmod", "stdbuf"],
    "packages": ["pacstrap", "pacman-key", "pacman", "stdbuf"],
    "configure": ["arch-chroot", "stdbuf"],
    "boot": ["bootctl", "efibootmgr", "stdbuf"],
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
#: 打开父链上一级目录用的 flags。**`O_NOFOLLOW` 是这里的核心**：目标盘里的
#: 目录一旦被换成符号链接，`openat` 就拒绝它，而不是跟到宿主机（Live）上同名
#: 的目录 —— 那是 root 越过目标盘的一次写入（#174）。
_DIR_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


def _symlink_error(parent_fd: int, name: str, link_path: Path, target: Path,
                   cause: OSError) -> InstallerError | None:
    """父链上这一级是不是符号链接；是就给一条说清路径的 `EXIT_GUARD`。

    只对 `ELOOP` / `ENOTDIR` 两类错误做这项判断：`O_NOFOLLOW` 遇到链接时
    在不同内核 / 系统上落在这两个 errno 上（带 `O_DIRECTORY` 的 Linux 是
    `ENOTDIR`）。判据看 `lstat` 本身，而不是「打开失败」—— 一个普通文件同样
    会让 `O_DIRECTORY` 报 `ENOTDIR`，那不是符号链接，不该按守卫拒绝。
    """
    if cause.errno not in (errno.ELOOP, errno.ENOTDIR):
        return None
    try:
        st = os.lstat(name, dir_fd=parent_fd)
    except OSError:
        return None
    if not stat.S_ISLNK(st.st_mode):
        return None
    return InstallerError(
        f"拒绝写入：父目录是符号链接 —— {link_path}",
        EXIT_GUARD,
        hint=f"要写的是 {target}；安装器只沿真实目录写，不跟着链接改到目标盘外",
    )


def _open_dir(parent_fd: int, name: str, link_path: Path, target: Path) -> int:
    """在 `parent_fd` 下打开一级目录；父链上遇到符号链接就拒绝。"""
    try:
        return os.open(name, _DIR_OPEN_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        error = _symlink_error(parent_fd, name, link_path, target, exc)
        if error is not None:
            raise error from exc
        raise


def _open_or_make_dir(parent_fd: int, name: str, link_path: Path, target: Path) -> int:
    """在 `parent_fd` 下打开一级父目录；缺失就建，**绝不跟随符号链接**。

    名字相对 `parent_fd` 解析，父链上的每一级都钉在它自己的上一层目录上 ——
    这样「符号链接」不再是字符串解析时看不见的一件事，而是这一级 `openat`
    的直接结果。
    """
    try:
        return _open_dir(parent_fd, name, link_path, target)
    except FileNotFoundError:
        pass                              # 还没建：下面建它
    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        pass                              # 并发（或续跑）刚建出来：按同一条纪律打开
    return _open_dir(parent_fd, name, link_path, target)


def _open_parent_dir(target: Path) -> int:
    """从根（相对路径则从当前目录）逐级打开 `target` 的父目录，返回它的 fd。

    调用方负责 `os.close()`。逐级 `openat` 的意义见 `write_text` 的 docstring：
    父链上的符号链接在**它所在的那一级**就被拒绝，不会解析到目标盘外。
    """
    base = Path(os.sep) if target.is_absolute() else Path(".")
    fd = os.open(str(base), _DIR_OPEN_FLAGS)
    walked = base
    try:
        for part in target.parent.parts:
            if part in (os.sep, "."):
                continue
            walked = walked / part
            child = _open_or_make_dir(fd, part, walked, target)
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)                      # 半途失败：已经打开的那几级也还回去
        raise
    return fd


def write_text(runner: Runner, path: str, text: str, *, mode: int | None = None,
               secret: bool = False) -> None:
    """写一个文件（含父目录）。dry-run 下只打印内容，不落盘。

    dry-run 把内容也打出来，是因为「将要生成的 fstab / 引导项长什么样」正是
    最值得先看一眼的东西 —— 分区表只是手段，这两个文件才决定它能不能起来。

    `secret=True` 时**连预览都不打**：密码那类内容一旦进了日志，日志就会跟着进仓库、
    进 issue、进别人的终端。要写的路径照旧说出来，内容一个字都不落。

    `mode` 在**写内容之前**就落到文件描述符上（`os.open` + `os.fchmod`），不是写完
    再 `chmod`：后者会留下一个「密码 / sudoers 已经在文件里、权限还是 umask 给的
    0644」的窗口。窗口很短，但它是 root 在写密码文件 —— 这种窗口不该有。

    **先写临时文件，`fsync` 后再 `os.replace`**：直接 `O_TRUNC` 覆盖的话，写到一半
    失败 / 断电会在目标路径上留下半份配置（fstab、pacman.conf 半份就等于起不来的
    系统）。同目录的临时文件 + 原子改名让目标要么是旧内容、要么是新内容。
    改名之后再 `fsync` 一次**父目录 fd**：只同步内容不足以让目录项（改名本身）扛住
    断电 —— 目录项可能退回改名前的状态，刚写完的配置「看起来成功、重启又没了」。
    目录 fsync 失败时抛 `DirectorySyncError`：**目标路径上已经是新内容**，失败的是
    「这次改名能否扛住断电」，与「没写进去」是两回事，调用方不许混为一谈。

    **不跟随符号链接**（`O_NOFOLLOW`）：写的是 `<target>/etc/pacman.conf` 这类
    目标盘路径，而目标盘内容在 `--steps configure` 这种续跑场景里不一定是安装器
    自己刚铺的。一个 `pacman.conf -> /etc/pacman.conf` 的链接会让 root 在宿主机
    （Live）上改文件 —— 越过目标盘的一次根写入。目标系统里这些文件本来就该是
    普通文件，遇到链接就拒绝并说清楚。

    **父链上的每一级也不跟随**（#174）：从根开始逐级
    `os.open(..., O_DIRECTORY|O_NOFOLLOW, dir_fd=...)`，缺失的目录用
    `os.mkdir(..., dir_fd=...)` 建（`EEXIST` 时再按同一条纪律打开）。只守最后
    一个分量不够 —— `<target>/etc/foo -> /etc` 这种**父目录**链接会让
    `<target>/etc/foo/x` 写进 Live 的 `/etc`，同样是一次越过目标盘的根写入。
    临时文件与改名也都挂在最后一级父目录的 fd 上：父链打开之后，路径解析不再
    经过字符串。
    """
    runner.reporter.note(f"写入 {path}" + (f"（mode {mode:04o}）" if mode is not None else "")
                         + ("（内容不打印）" if secret else ""))
    if runner.dry_run:
        if not secret:
            _preview(runner.reporter, text)
        return
    target = Path(path)
    parent_fd = _open_parent_dir(target)
    try:
        try:
            existing = os.lstat(target.name, dir_fd=parent_fd)
        except FileNotFoundError:
            existing = None
        if existing is not None and stat.S_ISLNK(existing.st_mode):
            raise InstallerError(
                f"拒绝写入符号链接：{path}",
                EXIT_GUARD,
                hint="目标系统里这个路径是符号链接 —— 安装器只写普通文件，不跟着链接改别处",
            )
        # 覆盖已有文件时保持它原来的属主、属组和权限（与 O_TRUNC 直接写的旧行为一致）。
        existing_mode = stat.S_IMODE(existing.st_mode) if existing is not None else None

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = -1
        temp: str | None = None
        try:
            for _ in range(100):
                candidate = f".{target.name}.{os.getpid()}.{os.urandom(6).hex()}.tmp"
                try:
                    fd = os.open(candidate, flags, 0o666, dir_fd=parent_fd)   # umask 照常生效
                except FileExistsError:
                    continue
                temp = candidate
                break
            else:
                raise OSError(errno.EEXIST, f"找不到可用的临时文件名：{path}")
            if existing is not None:
                # chown 可能清除 setuid/setgid 位，因此先恢复属主和属组，再设置权限。
                os.fchown(fd, existing.st_uid, existing.st_gid)
            if mode is not None:
                # `os.open` 的 mode 会被 umask 掩掉；fchmod 一次拿到调用方要求的精确
                # 权限，仍然在写内容之前。
                os.fchmod(fd, mode)
            elif existing_mode is not None:
                os.fchmod(fd, existing_mode)
            handle = os.fdopen(fd, "w", encoding="utf-8")
            fd = -1
            with handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())      # 内容先落盘，再让改名把它换上去
            os.replace(temp, target.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            temp = None                    # 改名成功：清理分支别再删这个名字
            try:
                os.fsync(parent_fd)        # 让改名后的目录项也落盘（只 fsync 内容不够）
            except OSError as exc:
                # 改名已生效：目标路径上就是新内容，失败的只是「目录项能否扛住断电」。
                # 不能报成普通的写入失败（那会让调用方以为目标还是旧内容），也不能吞。
                detail = exc.strerror or str(exc) or type(exc).__name__
                raise DirectorySyncError(
                    f"文件已替换，但目录项持久化未确认：{path}（父目录 fsync 失败：{detail}）",
                    hint=("目标路径上已经是新内容（os.replace 成功）；这次改名能否扛住"
                          "断电没确认 —— 它不是「没写进去」，但断电后可能退回旧内容。"
                          "先查 dmesg / 磁盘健康，再重跑这一步。"),
                ) from exc
        finally:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if temp is not None:
                try:
                    os.unlink(temp, dir_fd=parent_fd)   # 失败时别在目标目录里留下半份临时文件
                except OSError:
                    pass
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass


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
    """块设备的字节数（走 sysfs，不解析 `lsblk` 的文本）。

    不是块设备就报与 `disk.assert_usable` 同一条守卫（`reason="notBlockDevice"`）。
    原来这里会漏出一个裸的 `FileNotFoundError` —— CLI 把它当「未预期的异常」
    （退出码 7）报成 traceback，可它其实只是「这块盘不存在」。
    """
    name = os.path.basename(os.path.realpath(path))
    try:
        sectors = Path(f"/sys/class/block/{name}/size").read_text(encoding="utf-8").strip()
        return int(sectors) * 512
    except (OSError, ValueError) as exc:
        raise InstallerError(
            f"不是块设备：{path}",
            EXIT_GUARD,
            hint="给整块盘的路径，例如 Live 里挂上来的 /dev/vda（先 lsblk 确认）",
            reason="notBlockDevice",
        ) from exc
