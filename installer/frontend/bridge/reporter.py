"""`mipl_installer.events.Reporter` 的 Qt 实现 —— 事件流回到界面的唯一通路。

**跨线程的规矩**（[bridge/README](README.md) 里的老话，仍然算数）：后端是阻塞的，
跑在工作线程里；它发出来的每件事都只能经 Qt 信号回到界面线程。**不许**在工作
线程里直接改 QML 属性 —— 那是偶发白屏与随机崩溃的经典来源。

信号名与协议方法名**故意不一样**（`noted` / `commanded` 对应 `note()` /
`command()`）：同一个类里一个叫 `note` 的 `Signal` 与一个叫 `note` 的方法只能
留一个，而协议里那两个必须是**方法**。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from mipl_installer.events import Event


class QtReporter(QObject):
    #: 阶段 + 那句话（`Event.phase` / `Event.message`）—— 进度条与「正在做什么」
    phased = Signal(str, str)
    #: 一行日志（旁白、命令、`Event.detail` 的每一行）。`LogView` 吃的就是它。
    logged = Signal(str)

    # ── Reporter 协议 ─────────────────────────────────────────────────
    def emit(self, event: Event) -> None:
        self.phased.emit(event.phase, event.message)
        if event.detail:
            for line in event.detail.rstrip("\n").splitlines():
                self.logged.emit(line)

    def note(self, message: str) -> None:
        self.logged.emit(message)

    def command(self, argv: list[str]) -> None:
        self.logged.emit("$ " + " ".join(str(arg) for arg in argv))
