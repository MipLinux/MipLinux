"""pacman.conf 与它 Include 的文件怎么进目标系统。

这一组守的是**检查点 6**（装后系统能 `pacman -Syu`）：少写一个 mirrorlist，
装完的系统第一次升级就找不到仓库，而那时已经不在 Live 里了。
"""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
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


class TestTargetPacmanConf(unittest.TestCase):
    """Live conf → 装后 conf：去掉 Optional Trust（#135）。"""

    def test_strips_optional_trust_from_repo_siglevel(self):
        source = "\n".join([
            "[options]",
            "SigLevel    = Required DatabaseOptional",
            "LocalFileSigLevel = Optional",
            "[archlinuxcn]",
            "SigLevel = Optional TrustAll",
            "Include = /etc/pacman.d/mirrorlist-archlinuxcn",
        ])
        out = configure.target_pacman_conf(source)
        self.assertNotIn("TrustAll", out)
        self.assertNotIn("[archlinuxcn]\nSigLevel", out)
        # 全局那行与本地文件策略不受影响
        self.assertIn("SigLevel    = Required DatabaseOptional", out)
        self.assertIn("LocalFileSigLevel = Optional", out)
        self.assertIn("[archlinuxcn]", out)
        self.assertTrue(out.endswith("\n"))

    def test_removes_disabled_and_prefixed_signature_overrides(self):
        for value in ("Never", "PackageNever", "PackageOptional", "PackageTrustAll",
                      "DatabaseNever", "DatabaseTrustAll", "Required PackageNever"):
            with self.subTest(value=value):
                source = f"[core]\nSigLevel = {value}\n"
                self.assertEqual(configure.target_pacman_conf(source), "[core]\n")

    def test_comment_does_not_change_strict_signature_setting(self):
        source = "SigLevel = Required DatabaseOptional # Optional TrustAll Never\n"
        self.assertEqual(configure.target_pacman_conf(source), source)

    def test_keeps_siglevel_without_holes(self):
        source = "\n".join([
            "[core]",
            "SigLevel = Required DatabaseOptional",
            "[archlinuxcn]",
            "SigLevel = Required",
        ])
        self.assertEqual(configure.target_pacman_conf(source), source + "\n")

    def test_live_conf_becomes_strict(self):
        live = LIVE_CONF.read_text(encoding="utf-8")
        out = configure.target_pacman_conf(live)
        # 装后系统里不许再有任何「不校验」的口径（#135 的验收判据）
        self.assertNotIn("TrustAll", out)
        self.assertNotIn("\nSigLevel = Optional", out)
        # 收紧只是「去行」，段与 Include 结构原样 —— 检查点 6 还要靠它找仓库
        self.assertEqual(configure.iter_includes(out), configure.iter_includes(live))
        self.assertIn("[archlinuxcn]", out)
        self.assertIn("Include = /etc/pacman.d/mirrorlist-archlinuxcn", out)


class TestCopyPacmanConfig(unittest.TestCase):
    def test_glob_and_nested_relative_includes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            (source / "repos").mkdir(parents=True)
            (source / "lists").mkdir()
            conf = source / "pacman.conf"
            conf.write_text("Include = repos/*.conf\n")
            (source / "repos/core.conf").write_text("[core]\nInclude = ../lists/core\n")
            (source / "lists/core").write_text("Server = https://example.invalid/$repo\n")
            target = root / "target"
            configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target), pacman_conf=str(conf)))
            self.assertEqual((target / "etc/pacman.conf").read_text(), "Include = /etc/repos/core.conf\n")
            self.assertEqual((target / "etc/repos/core.conf").read_text(), "[core]\nInclude = /etc/lists/core\n")
            self.assertEqual((target / "etc/lists/core").read_text(), (source / "lists/core").read_text())

    def test_packaged_baseline_glob_preserves_target_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "baseline"
            (baseline / "etc/repos").mkdir(parents=True)
            (baseline / "etc/pacman.conf").write_text("Include = /etc/repos/*.conf\n")
            (baseline / "etc/repos/core.conf").write_text("[core]\nServer = https://example.invalid\n")
            target = root / "target"
            with patch.object(configure, "PACMAN_BASELINE", baseline):
                configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target)))
            self.assertEqual((target / "etc/pacman.conf").read_text(), "Include = /etc/repos/core.conf\n")
            self.assertTrue((target / "etc/repos/core.conf").is_file())

    def test_packaged_baseline_include_cannot_escape_to_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "baseline"
            (baseline / "etc").mkdir(parents=True)
            (baseline / "etc/pacman.conf").write_text("Include = /etc/outside\n")
            outside = root / "outside"
            outside.write_text("Server = https://example.invalid\n")
            (baseline / "etc/outside").symlink_to(outside)
            target = root / "target"
            with patch.object(configure, "PACMAN_BASELINE", baseline):
                with self.assertRaises(InstallerError):
                    configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target)))
            self.assertFalse(target.exists())

    def test_signature_policy_applies_to_nested_includes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / "pacman.conf"
            conf.write_text("[options]\nSigLevel = Required DatabaseOptional\nInclude = repo.conf\n")
            (root / "repo.conf").write_text("[core]\nSigLevel = Never\nInclude = mirrors\n")
            (root / "mirrors").write_text("SigLevel = PackageNever\nServer = https://example.invalid\n")
            target = root / "target"
            configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target), pacman_conf=str(conf)))
            self.assertIn("Required DatabaseOptional", (target / "etc/pacman.conf").read_text())
            self.assertNotIn("SigLevel", (target / "etc/repo.conf").read_text())
            self.assertEqual((target / "etc/mirrors").read_text(), "Server = https://example.invalid\n")

    def test_include_cycle_fails_before_writing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / "pacman.conf"
            conf.write_text("Include = pacman.conf\n")
            target = root / "target"
            with self.assertRaises(InstallerError) as ctx:
                configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target), pacman_conf=str(conf)))
            self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
            self.assertFalse(target.exists())

    def test_nested_missing_include_fails_before_writing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / "pacman.conf"
            conf.write_text("Include = child.conf\n")
            (root / "child.conf").write_text("Include = missing.conf\n")
            target = root / "target"
            with self.assertRaises(InstallerError):
                configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target), pacman_conf=str(conf)))
            self.assertFalse(target.exists())

    def test_default_uses_packaged_baseline_for_both_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "baseline"
            (baseline / "etc/pacman.d").mkdir(parents=True)
            (baseline / "etc/pacman.conf").write_text(LIVE_CONF.read_text())
            for name in ("mirrorlist", "mirrorlist-archlinuxcn"):
                (baseline / "etc/pacman.d" / name).write_text(
                    f"Server = https://factory.invalid/{name}/$repo/$arch\n")
            target = root / "target"
            with patch.object(configure, "PACMAN_BASELINE", baseline):
                configure.copy_pacman_config(FakeRunner(), TargetConfig(target=str(target)))
            for name in ("mirrorlist", "mirrorlist-archlinuxcn"):
                self.assertEqual((target / "etc/pacman.d" / name).read_bytes(),
                                 (baseline / "etc/pacman.d" / name).read_bytes())
            self.assertNotIn("TrustAll", (target / "etc/pacman.conf").read_text())

    def test_missing_baseline_never_falls_back_to_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(configure, "PACMAN_BASELINE", Path(tmp) / "missing"):
                with self.assertRaises(InstallerError):
                    configure.copy_pacman_config(FakeRunner(), TargetConfig(target=tmp))

    def test_missing_baseline_include_is_a_hard_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "baseline"
            (baseline / "etc").mkdir(parents=True)
            (baseline / "etc/pacman.conf").write_text(LIVE_CONF.read_text())
            with patch.object(configure, "PACMAN_BASELINE", baseline):
                with self.assertRaises(InstallerError):
                    configure.copy_pacman_config(FakeRunner(), TargetConfig(target=tmp))

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

    def test_writes_strict_conf_when_source_has_optional_trust(self):
        """照抄 Live conf 会把 `Optional TrustAll` 带进装后系统 —— 不许（#135）。"""
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            source.mkdir()
            mirrorlist = source / "mirrorlist"
            mirrorlist.write_text("Server = https://mirror.invalid/$repo/os/$arch\n", encoding="utf-8")
            conf = source / "pacman.conf"
            conf.write_text(
                "[archlinuxcn]\nSigLevel = Optional TrustAll\n"
                f"Include = {mirrorlist}\n", encoding="utf-8")

            target = root / "target"
            target.mkdir()
            configure.copy_pacman_config(
                runner, TargetConfig(target=str(target), pacman_conf=str(conf)))

            written = (target / "etc/pacman.conf").read_text(encoding="utf-8")
            self.assertNotIn("TrustAll", written)
            # Include 依旧解析并复制
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
