"""pacman.conf 与它 Include 的文件怎么进目标系统。

这一组守的是**检查点 6**（装后系统能 `pacman -Syu`）：少写一个 mirrorlist，
装完的系统第一次升级就找不到仓库，而那时已经不在 Live 里了。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import configure
from mipl_installer.configure import TargetConfig
from mipl_installer.util import EXIT_CONFIGURE, InstallerError
from tests.support import FakeRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_CONF = REPO_ROOT / "profile/airootfs/etc/pacman.conf"
BUILD_CONF = REPO_ROOT / "profile/pacman.conf"


class TestIterIncludes(unittest.TestCase):
    def test_only_uncommented(self):
        text = "\n".join([
            "[core]",
            "#Include = /etc/pacman.d/mirrorlist",
            "Include = /etc/pacman.d/mirrorlist-archlinuxcn",
            "Server = https://example.invalid/$repo/os/$arch",
        ])
        self.assertEqual(configure.iter_includes(text), ["/etc/pacman.d/mirrorlist-archlinuxcn"])

    def test_live_conf_has_two_includes(self):
        # Live 的出厂设置：core/extra/multilib 用 mirrorlist，archlinuxcn 用另一份
        includes = configure.iter_includes(LIVE_CONF.read_text(encoding="utf-8"))
        self.assertEqual(includes, ["/etc/pacman.d/mirrorlist"] * 3 + ["/etc/pacman.d/mirrorlist-archlinuxcn"])

    def test_build_conf_has_none(self):
        # profile/pacman.conf 的 Include 全注释掉，这是 D3 的落地形态
        self.assertEqual(configure.iter_includes(BUILD_CONF.read_text(encoding="utf-8")), [])


class TestCopyPacmanConfig(unittest.TestCase):
    def test_copies_conf_and_its_includes(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            source.mkdir()
            mirrorlist = source / "mirrorlist"
            mirrorlist.write_text("Server = https://mirror.invalid/$repo/os/$arch\n", encoding="utf-8")
            conf = source / "pacman.conf"
            conf.write_text(f"[core]\nInclude = {mirrorlist}\n", encoding="utf-8")

            target = root / "target"
            target.mkdir()
            cfg = TargetConfig(target=str(target), pacman_conf=str(conf))

            configure.copy_pacman_config(runner, cfg)

            self.assertEqual((target / "etc/pacman.conf").read_text(encoding="utf-8"),
                             conf.read_text(encoding="utf-8"))
            # Include 是按它在 conf 里的**绝对路径**落到目标系统里
            self.assertEqual((target / str(mirrorlist).lstrip("/")).read_text(encoding="utf-8"),
                             mirrorlist.read_text(encoding="utf-8"))

    def test_falls_back_to_mirrorlist_when_conf_has_no_include(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / "pacman.conf"
            conf.write_text("[core]\nServer = https://mirror.invalid/$repo/os/$arch\n", encoding="utf-8")
            mirrorlist = root / "mirrorlist"
            mirrorlist.write_text("Server = https://cn.invalid/$repo/os/$arch\n", encoding="utf-8")
            target = root / "target"
            target.mkdir()

            cfg = TargetConfig(target=str(target), pacman_conf=str(conf), mirrorlist=str(mirrorlist))
            configure.copy_pacman_config(runner, cfg)

            self.assertIn("cn.invalid", (target / "etc/pacman.d/mirrorlist").read_text(encoding="utf-8"))

    def test_missing_include_is_a_hard_error(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / "pacman.conf"
            conf.write_text("[core]\nInclude = /nonexistent/mirrorlist\n", encoding="utf-8")
            target = root / "target"
            target.mkdir()

            with self.assertRaises(InstallerError) as ctx:
                configure.copy_pacman_config(runner, TargetConfig(target=str(target), pacman_conf=str(conf)))
            self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
            self.assertIn("Include", str(ctx.exception))

    def test_missing_conf_is_a_hard_error(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InstallerError) as ctx:
                configure.copy_pacman_config(
                    runner, TargetConfig(target=tmp, pacman_conf=f"{tmp}/nope.conf")
                )
            self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)


if __name__ == "__main__":
    unittest.main()
