"""排练脚本里的 `keep_log`：把安装日志留一份到目标盘。

这个函数在 Live 里跑过一轮真实验，结果**没生效**（目标盘 `/root/` 下没有日志）。
原因：`lsblk` 的树线（`└─`）**在管道里也会输出**，
`awk '$2 == "part" { p = $1 }'` 取到的是 `└─/dev/vda2` —— `mount` 拿到这种路径就失败，
而它被 `2>/dev/null || true` 吞掉了，于是"静默什么都没做"。

所以这里用**桩**来跑：`lsblk` 故意吐带树线的输出（照实的来），`mount`/`umount` 只记录参数。
断言两件事：挂载用的是**干净路径**，日志**真的到了**目标盘的 /root/ 下。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tests" / "live-rehearsal.sh"

#: 桩 lsblk 要像真的：**不带 -l 时带树线，带 -l（list 模式）时是干净路径**。
#: 这样它才能分辨「有没有带 -l」—— 否则这个回归测试是假的。
STUB_LSBLK = """#!/bin/sh
case "$*" in
  *-l*) printf '/dev/vda disk\\n/dev/vda1 part\\n/dev/vda2 part\\n' ;;
  *)    printf '/dev/vda disk\\n├─/dev/vda1 part\\n└─/dev/vda2 part\\n' ;;
esac
"""


class TestKeepLog(unittest.TestCase):
    def _run(self):
        """在临时目录里跑一遍 keep_log，返回 (记录下来的调用, 目标根目录)。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        target = root / "target"
        target.mkdir()
        calls = root / "calls.txt"

        (bin_dir / "lsblk").write_text(STUB_LSBLK, encoding="utf-8")
        for name in ("mount", "umount", "sync"):
            (bin_dir / name).write_text(
                f'#!/bin/sh\necho "{name} $*" >> "{calls}"\nexit 0\n', encoding="utf-8")
        for script in bin_dir.iterdir():
            script.chmod(0o755)

        log = root / "mipl-m1-rehearsal.log"
        log.write_text("日志内容\n", encoding="utf-8")

        # MIPL_REHEARSAL_SOURCED 告诉脚本「我是被 source 的，别跑主流程」
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
               "MIPL_REHEARSAL_SOURCED": "1"}
        subprocess.run(
            ["bash", "-c",
             f'source "{SCRIPT}"; keep_log /dev/vda "{log}" "{target}"'],
            check=True, env=env, capture_output=True, text=True,
        )
        return calls.read_text(encoding="utf-8") if calls.exists() else "", target

    def test_mounts_the_clean_path_not_the_tree_line(self):
        """**回归测试**：`└─/dev/vda2` 这种路径挂不上，必须解析出 `/dev/vda2`。"""
        calls, _ = self._run()
        self.assertIn("mount /dev/vda2 ", calls)
        self.assertNotIn("└─", calls)

    def test_log_lands_in_the_targets_root(self):
        calls, target = self._run()
        copied = target / "root" / "mipl-m1-rehearsal.log"
        self.assertTrue(copied.exists(), f"日志没落到 {copied}；mount 调用：\n{calls}")
        self.assertIn("日志内容", copied.read_text(encoding="utf-8"))

    def test_cleans_up_the_mountpoint_afterwards(self):
        calls, target = self._run()
        self.assertIn(f"umount {target}", calls)

    def test_does_nothing_when_the_log_is_missing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "target"
        target.mkdir()
        subprocess.run(
            ["bash", "-c",
             f'MIPL_REHEARSAL_SOURCED=1 source "{SCRIPT}"; keep_log /dev/vda /nonexistent/x.log "{target}"'],
            check=True, capture_output=True, text=True,
        )
        self.assertFalse((target / "root").exists())


if __name__ == "__main__":
    unittest.main()
