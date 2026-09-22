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
from tests.support import FakeRunner

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


if __name__ == "__main__":
    unittest.main()
