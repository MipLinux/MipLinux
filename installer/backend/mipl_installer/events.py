"""进度事件流：core 只发事件，前端只订阅。

M2 的 Qt 前端实现同一个 `Reporter` 协议；**core 里不许出现界面代码**
（installer/AGENTS.md）。所以事件名是一份稳定接口 —— 改 `PHASES` 里的名字
等于改接口，得先想清楚前端会不会跟着破。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol, TextIO

# 阶段名：前端按它分组显示。顺序即执行顺序。
PHASES = ("start", "disk", "packages", "configure", "boot", "done")


@dataclass(frozen=True)
class Event:
    """一件事：在哪个阶段、干了什么、进度多少（0-100，未知则 None）。"""

    phase: str
    message: str
    percent: int | None = None
    detail: str | None = None


class Reporter(Protocol):
    """前端要实现的东西。`emit` 是事件流，`note`/`command` 是给人看的旁白。

    界面（M2）可以只实现 `emit`，把另外两个当空操作 —— 它们的信息量都在
    日志里，不该逼着界面去画。
    """

    def emit(self, event: Event) -> None: ...


class NullReporter:
    """测试用：把事件与旁白都丢掉。"""

    def emit(self, event: Event) -> None:
        pass

    def note(self, message: str) -> None:
        pass

    def command(self, argv: list[str]) -> None:
        pass


class TextReporter:
    """CLI 用：一行一件事，同时可选地写一份日志文件。

    日志要能整份抄进 `docs/work/tech/`，所以这里不加上色、不加时间戳的
    花活 —— 逐字可读、可 diff 就够。
    """

    def __init__(self, stream: TextIO | None = None, log_path: str | None = None) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self._log = open(log_path, "w", encoding="utf-8") if log_path else None
        self.log_path = log_path

    # ── 事件 ──────────────────────────────────────────────────────────
    def emit(self, event: Event) -> None:
        suffix = f" ({event.percent}%)" if event.percent is not None else ""
        self._write(f"[{event.phase}] {event.message}{suffix}")
        if event.detail:
            for line in event.detail.rstrip("\n").splitlines():
                self._write(f"    {line}")

    # ── 命令与提示（不属于事件流，但同样要进日志）──────────────────────
    def command(self, argv: list[str]) -> None:
        self._write("  $ " + " ".join(argv))

    def note(self, message: str) -> None:
        self._write(f"    {message}")

    def close(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None

    def _write(self, line: str) -> None:
        print(line, file=self.stream, flush=True)
        if self._log is not None:
            self._log.write(line + "\n")
            self._log.flush()
