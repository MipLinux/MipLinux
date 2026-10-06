"""进度事件流：core 只发事件，前端只订阅。

三种 reporter 各有各的消费者：

| reporter | 消费者 | 形态 |
|---|---|---|
| `TextReporter` | CLI（人读）与 `docs/work/tech/` 的日志 | 一行一件事，带缩进 |
| `JsonReporter` | 安装器界面（`main.js` 逐行解析） | 一行一个 JSON 对象 |
| `NullReporter` | 单测 | 全丢 |

**core 里不许出现界面代码**（installer/AGENTS.md）。所以事件名是一份稳定接口 ——
改 `PHASES` 里的名字等于改接口，得先想清楚前端会不会跟着破。
"""

from __future__ import annotations

import json
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


class FileSinks:
    """日志落点的公共件：stdout/stderr 之外，主日志文件 + 可后挂的附加落点。

    附加落点给「写进目标盘」用（`attach_log_path`）：目标盘是安装期间唯一既写得进、
    又活得过重启/断电的地方。挂上时先把**内存里记下的全部历史行**补写进去，之后每行
    同时写所有落点 —— 中途挂死被强杀时，盘上是到挂死点为止的完整日志，而不是
    「收尾时抢救出来的那一点」（测试阶段 Bug 多，复盘材料必须默认就在）。
    """

    def _init_sinks(self, log_path: str | None) -> None:
        self.log_path = log_path
        self._log = open(log_path, "w", encoding="utf-8") if log_path else None
        self._extra: list[TextIO] = []
        self._lines: list[str] = []

    def attach_log_path(self, path: str) -> None:
        """再加一个日志落点（覆盖式打开，历史行先补写）。"""
        handle = open(path, "w", encoding="utf-8")
        if self._lines:
            handle.write("\n".join(self._lines) + "\n")
        handle.flush()
        self._extra.append(handle)

    def _write_line(self, line: str) -> None:
        self._lines.append(line)
        print(line, file=self.stream, flush=True)
        for handle in (self._log, *self._extra):
            if handle is not None:
                handle.write(line + "\n")
                handle.flush()

    def close(self) -> None:
        for handle in (self._log, *self._extra):
            if handle is not None:
                handle.close()
        self._log = None
        self._extra = []


class TextReporter(FileSinks):
    """CLI 用：一行一件事，同时可选地写一份日志文件。

    日志要能整份抄进 `docs/work/tech/`，所以这里不加上色、不加时间戳的
    花活 —— 逐字可读、可 diff 就够。
    """

    def __init__(self, stream: TextIO | None = None, log_path: str | None = None) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self._init_sinks(log_path)

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

    def _write(self, line: str) -> None:
        self._write_line(line)


#: JSON 行的协议版本。**事件名与字段名是接口**（见 app/README.md 的耦合层一节）：
#: 加字段可以，改名字要前端跟着改。这里只出现在 `hello` 一条里，
#: 前端拿它判断「对面是不是我认识的这个后端」。
PROTOCOL = 1


class JsonReporter(FileSinks):
    r"""界面用：**一行一个 JSON 对象**，stdout 上除了这些行什么都没有。

    为什么是行分隔的 JSON 而不是别的：前端只要 `readline` + `JSON.parse` 就能消费，
    不需要长度前缀、不需要等进程结束、也不需要让 Node 去理解 Python 的对象。
    密码仍然只走 stdin —— argv 会留在进程列表与日志里（`cli.py` 的红线），
    所以事件流只能是**单向**的：后端说、前端听，前端要看什么另外查（`--print-*`）。

    `kind` 是判别字段，一共五种：

    | kind | 谁发的 | 含义 |
    |---|---|---|
    | `hello` | `JsonReporter.__init__` | 第一条。带 `protocol` 版本，前端据此确认对得上 |
    | `event` | `emit()` | 阶段与进度。`phase` 取自 `PHASES` |
    | `note` | `note()` | 给人看的旁白（`command` 与 `note` 在前端是同一种东西） |
    | `command` | `command()` | 跑了哪条命令（不实现也行，但实机上排查靠它） |
    | `error` | `error()` | 失败：退出码 + 消息 + 提示。**之后一定跟一条 `end`** |
    | `end` | `finish()` | 收尾。带进程退出码，前端据此决定是「装完了」还是「失败了」 |

    最后两条是刻意加的：子进程的退出码当然能等到 `close` 事件再拿，
    但「为什么失败」在 stderr 上、退出码在 `close` 里，前端要拼两处才能说一句完整的话。
    `error` + `end` 让失败也走同一条流、同一个解析器。
    """

    def __init__(self, stream: TextIO | None = None, log_path: str | None = None) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self._init_sinks(log_path)
        self._write({"kind": "hello", "protocol": PROTOCOL, "version": _version()})

    # ── 事件 ──────────────────────────────────────────────────────────
    def emit(self, event: Event) -> None:
        self._write(
            {
                "kind": "event",
                "phase": event.phase,
                "message": event.message,
                "percent": event.percent,
                "detail": event.detail,
            }
        )

    def command(self, argv: list[str]) -> None:
        self._write({"kind": "command", "argv": list(argv)})

    def note(self, message: str) -> None:
        self._write({"kind": "note", "message": message})

    def error(self, code: int, message: str, hint: str | None = None) -> None:
        self._write({"kind": "error", "code": code, "message": message, "hint": hint})

    def finish(self, code: int) -> None:
        self._write({"kind": "end", "code": code})

    def _write(self, record: dict) -> None:
        self._write_line(json.dumps(record, ensure_ascii=False))


def _version() -> str:
    """包版本。放在函数里是为了避开 `__init__` 的循环 import（它 import 了本模块）。"""
    from . import __version__

    return __version__
