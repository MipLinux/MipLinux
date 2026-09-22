"""单测的公共件。

`FakeRunner` 顶替真的 `Runner`：命令只记不跑。要断言「会跑哪些命令、顺序对不对」，
这是唯一不碰盘的办法 —— 分区逻辑的测试不许落到真设备上（安全红线）。
"""

from __future__ import annotations

import unittest

from mipl_installer.events import NullReporter
from mipl_installer.util import InstallerError


class RecordingReporter:
    """把旁白记下来：有些行为（比如「root 没设密码要说出来」）只有笔记里看得到。"""

    def __init__(self) -> None:
        self.notes: list[str] = []
        self.events: list = []

    def emit(self, event) -> None:
        self.events.append(event)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def command(self, argv) -> None:
        pass

    def text(self) -> str:
        return "\n".join(self.notes)


class FakeRunner:
    """记录命令的 Runner 替身。行为与 util.Runner 对齐（run/attempt/require/have）。"""

    def __init__(self, *, dry_run: bool = False, outputs: dict[str, str] | None = None,
                 reporter=None) -> None:
        self.reporter = reporter if reporter is not None else NullReporter()
        self.dry_run = dry_run
        self.history: list[list[str]] = []
        self.outputs = outputs or {}
        self.fail_patterns: set[str] = set()

    # ── 与真 Runner 同签名 ────────────────────────────────────────────
    def run(self, argv, *, check=True, capture=False, exit_code=7, input=None, cwd=None):
        argv = [str(a) for a in argv]
        self.history.append(argv)
        joined = " ".join(argv)
        if check:
            for pattern in self.fail_patterns:
                if pattern in joined:
                    raise InstallerError(f"（替身）命令失败：{joined}", exit_code)
        if capture:
            # 按子串匹配输出：命令里常带 tmp 路径，用完整命令当键没法跨用例复用
            for key, value in self.outputs.items():
                if key in joined:
                    return value
            return ""
        return None

    def attempt(self, argv, *, input=None):
        argv = [str(a) for a in argv]
        self.history.append(argv)
        joined = " ".join(argv)
        return not any(p in joined for p in self.fail_patterns)

    def require(self, programs, *, tools=None):
        return None

    def have(self, program):
        return True

    # ── 断言助手 ──────────────────────────────────────────────────────
    def commands(self) -> list[str]:
        return [" ".join(argv) for argv in self.history]

    def find(self, needle: str) -> list[str]:
        return [cmd for cmd in self.commands() if needle in cmd]

    def assert_ran(self, case: unittest.TestCase, needle: str) -> str:
        hits = self.find(needle)
        case.assertTrue(hits, f"没有跑到含 {needle!r} 的命令；实际跑了：\n" + "\n".join(self.commands()))
        return hits[0]
