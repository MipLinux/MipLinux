"""界面能要求系统做的事 —— 目前只有一件：重启。

**为什么不让 QML 自己去做**：`installer/AGENTS.md` 第一条是「前端只订阅事件，
不实现逻辑」。QML 里没有进程 API（要 `Qt.labs.platform` 之类），就算有也不该用 ——
「装完了 → 重启」这件事的**决定权**在后端/入口这一侧，界面只负责**表达意图**
（`DonePage.rebootRequested` → `Main.qml` → 这里）。

实机测试反馈（2026-09-26）：原来 `Main.qml` 里只 `Qt.quit()`，于是点「立即重启」
把安装器杀了、掉回 root 的 tty —— 看着像崩了。现在真的重启。

真接线之后，这个动作会由后端收尾流程接管（装完 → 卸载目标 → 重启），
本文件仍然只做一个「请求」的落点。
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject, Slot


class SystemActions(QObject):
    """暴露给 QML 的 `System` 对象（见 mipl-installer 里的 setContextProperty）。"""

    @Slot()
    def reboot(self) -> None:
        """重启。

        `subprocess.Popen` 而不是 `run`：`systemctl reboot` 一发起，systemd 就会
        开始停服务（包括我们这个 unit），用 `run` 等它返回会把自己卡在停服务的过程中。
        起一个独立进程让它自己走完，我们该退就退。
        """
        print("[mipl] 收到重启请求：systemctl reboot", flush=True)
        subprocess.Popen(["/usr/bin/systemctl", "reboot"])
