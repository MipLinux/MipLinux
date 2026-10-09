"""目标包清单与 pacstrap 的参数。

两个「不许被简化掉」的约定在这里被钉住：

* keyring 必须排在 pacstrap **之前**（否则装包时签名校验过不去）；
* `-G` / `-M` 必须在（否则 pacstrap 会顺手把运行环境的 keyring 与 mirrorlist
  抄进目标系统 —— 在 Live 里恰好对，在别处就是静默引入宿主源）。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import packages
from mipl_installer.util import EXIT_USAGE, InstallerError
from tests.support import FakeRunner, RecordingReporter

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestParsePackageList(unittest.TestCase):
    def test_comments_blanks_and_duplicates(self):
        text = "# 注释\n\nbase\nlinux   # 行尾注释\nbase\nlinux-firmware\n"
        self.assertEqual(packages.parse_package_list(text), ["base", "linux", "linux-firmware"])

    def test_multi_token_line(self):
        self.assertEqual(packages.parse_package_list("base linux"), ["base", "linux"])


class TestReadPackageList(unittest.TestCase):
    def test_default_file_is_the_m1_list(self):
        path = packages.default_packages_file()
        self.assertTrue(path.endswith("mipl_installer/data/target-packages.x86_64"), path)
        listed = packages.read_package_list(path)
        # 检查点 4 要能启动、检查点 6 要能升级：内核与网络是最低要求
        for needed in ("base", "linux", "networkmanager", "sudo"):
            self.assertIn(needed, listed)

    def test_missing_file(self):
        with self.assertRaises(InstallerError) as ctx:
            packages.read_package_list("/nonexistent/packages.x86_64")
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "packages.x86_64"
            path.write_text("# 只有注释\n", encoding="utf-8")
            with self.assertRaises(InstallerError) as ctx:
                packages.read_package_list(str(path))
            self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_refuses_the_live_list(self):
        # D6：Live 的清单不是装后系统的清单（两份清单的关系见 P10）
        with self.assertRaises(InstallerError) as ctx:
            packages.read_package_list(str(REPO_ROOT / "profile/packages.x86_64"))
        self.assertIn("Live", str(ctx.exception))
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)


class TestInstallOrder(unittest.TestCase):
    """`FakeRunner` 只在「跑命令」这一层是替身：`ensure_dir` / `write_text` 仍会
    真的落盘，所以目标一律用 tmp（也顺带证明我们没往 /mnt 乱写）。"""

    def test_keyring_before_pacstrap(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            packages.install(runner, tmp, packages.default_packages_file(), "/etc/pacman.conf")
        commands = runner.commands()

        init = next(i for i, c in enumerate(commands) if "--init" in c)
        populate = next(i for i, c in enumerate(commands) if "--populate" in c)
        strap = next(i for i, c in enumerate(commands) if c.startswith("pacstrap"))

        self.assertLess(init, strap)
        self.assertLess(populate, strap)
        self.assertIn("--gpgdir", commands[init])
        self.assertTrue(commands[init].endswith("/etc/pacman.d/gnupg --init"), commands[init])

    def test_pacstrap_flags(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            packages.pacstrap(runner, tmp, ["base", "linux"], "/etc/pacman.conf")
        command = runner.assert_ran(self, "pacstrap")
        self.assertEqual(command, f"pacstrap -C /etc/pacman.conf -G -M {tmp} base linux")
        # -K 会把 keyring 重置成空的，后面 pacman -S 就装不动了
        self.assertNotIn(" -K", command)


class TestPackageCounter(unittest.TestCase):
    """pacman 的 `(14/345)` → 阶段内的细进度（2026-10-06 进度重做的那一半）。

    两条要点：

    * **分母取自 pacman 自己** —— 不另问仓库，也就不会出现「按清单算 21、
      它连依赖装了 345」那种对不上的分母；
    * 解析**只认数字与括号**，所以 LANG 把「installing」翻成「正在安装」也不影响它。
    """

    def setUp(self):
        self.reporter = RecordingReporter()
        self.counter = packages.PackageCounter(self.reporter)

    def feed(self, *lines: str) -> list[tuple[int, int]]:
        for line in lines:
            self.counter.feed(line)
        return [(event.step, event.total) for event in self.reporter.events]

    def test_reads_step_and_total(self):
        self.assertEqual(self.feed("(3/345) installing foo"), [(3, 345)])

    def test_translated_output_is_still_read_correctly(self):
        self.assertEqual(self.feed("(3/345) 正在安装 foo"), [(3, 345)])

    def test_the_same_package_reported_twice_is_deduped(self):
        # 同一个包会打好几行（查密钥、装包）；全发出去等于让界面白重画几次
        self.assertEqual(self.feed("(3/345) checking keys", "(3/345) installing foo"), [(3, 345)])

    def test_lines_without_a_counter_are_left_alone(self):
        """认不出来就放过 —— 这条解析只影响「有没有细进度」，绝不影响装包。"""
        self.assertEqual(self.feed(":: 正在获取软件包...", "foo-1.0-1 下载中", ""), [])

    def test_event_shape_matches_the_contract(self):
        self.counter.feed("(1/7) installing a")
        event = self.reporter.events[0]
        self.assertEqual(event.phase, "packages")
        self.assertEqual(event.step_id, "install")
        self.assertEqual((event.step, event.total), (1, 7))
        self.assertIsNone(event.percent, "细进度不带全局百分比")

    def test_install_wires_the_counter_to_pacstrap_output(self):
        """整条路：`install()` → `pacstrap` → 行回调 → 事件（替身把输出逐行喂回来）。"""
        reporter = RecordingReporter()
        runner = FakeRunner(reporter=reporter, outputs={
            "pacstrap": "(1/3) installing a\n(2/3) installing b\n(3/3) installing c\n",
        })
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "pkgs"
            manifest.write_text("base\n", encoding="utf-8")
            packages.install(runner, tmp, str(manifest), "/etc/pacman.conf")
        install_events = [e for e in reporter.events if e.step_id == "install"]
        # 先声明「开始下载并安装」（这一步数不出总数），再按 pacman 的报数逐条更新
        self.assertIsNone(install_events[0].step)
        self.assertEqual([(e.step, e.total) for e in install_events[1:]], [(1, 3), (2, 3), (3, 3)])

    def test_pacstrap_only_takes_a_hook_when_a_counter_is_given(self):
        plain = FakeRunner()
        packages.pacstrap(plain, "/mnt", ["base"], "/etc/pacman.conf")
        self.assertEqual(plain.line_hooks, [None])

        wired = FakeRunner()
        packages.pacstrap(wired, "/mnt", ["base"], "/etc/pacman.conf",
                          counter=packages.PackageCounter(RecordingReporter()))
        self.assertEqual(len(wired.line_hooks), 1)
        self.assertTrue(callable(wired.line_hooks[0]))


if __name__ == "__main__":
    unittest.main()
