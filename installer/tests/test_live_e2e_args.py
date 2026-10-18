"""`live-e2e.py` 的取值注入：占位符必须在**发送前**被换掉。

它不需要 Live、不需要 QEMU，也就没有理由不测 —— 而这段代码恰恰是「静默出错」的类型：
脚本常量是 import 期求值的字符串，`prepare()` 只在发送前替换占位符；占位符拼错、
或者值在 import 期就被固化进 f-string，**表面上一切正常**，客机收到的却是一份带着
旧值（或空值）的脚本 —— 你只有在装完看目标盘时才发现参数没生效。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "live-e2e.py"


def load_module():
    spec = importlib.util.spec_from_file_location("live_e2e_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestLiveE2EArguments(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_timezone_reaches_every_installing_script(self):
        """装盘、取消、强杀三轮都要用**同一个**时区，否则验的是另一个问题。"""
        args = self.module.parse_args(["out/x.sock", "--timezone", "Asia/Shanghai"])
        self.assertEqual(args.timezone, "Asia/Shanghai")
        for name in ("INSTALL_SCRIPT", "CANCEL_SCRIPT"):
            with self.subTest(script=name):
                prepared = self.module.prepare(getattr(self.module, name), "", "")
                self.assertIn("--timezone Asia/Shanghai", prepared)
                self.assertNotIn("__TIMEZONE__", prepared)

    def test_default_timezone_is_not_the_installer_default(self):
        """默认取非默认值：装后系统才验得出「选择真的写进去了」。"""
        args = self.module.parse_args(["out/x.sock"])
        self.assertNotEqual(args.timezone, "Asia/Shanghai")

    def test_mirror_setup_only_touches_the_live_mirrorlist(self):
        """`--mirror` 是**这一轮**的取巧：只写运行环境的 mirrorlist，不碰仓库里的配置。"""
        prepared = self.module.prepare(self.module.PROBE_SCRIPT, "", "")
        self.assertNotIn("Server =", prepared, "不给 --mirror 时不该动镜像")

        self.module.parse_args([
            "out/x.sock",
            "--mirror", "https://geo.mirror.pkgbuild.com/$repo/os/$arch",
        ])
        prepared = self.module.prepare(self.module.PROBE_SCRIPT, "", "")
        self.assertIn("'https://geo.mirror.pkgbuild.com/$repo/os/$arch'", prepared)
        self.assertIn(f"> {self.module.LIVE_MIRRORLIST}", prepared)
        self.assertIn("pacman -Sy", prepared, "换了镜像要顺手同步库，否则解析的是构建那天的旧库")

    def test_verify_script_reports_the_resolved_path(self):
        """#149 的验收判据就在这一行上：`readlink -f` 要能直接与所选 IANA id 对照。"""
        self.assertIn("VERIFY-LOCALTIME-RESOLVED=$(readlink -f", self.module.VERIFY_SCRIPT)


if __name__ == "__main__":
    unittest.main()
