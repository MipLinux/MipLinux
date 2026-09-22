"""目标系统里那些「写出来的文件」：fstab、locale、用户、hosts、sudoers。

能写成文件的就写成文件 —— 这一组是纯函数与真文件的对拍，不需要 root，
也不需要 QEMU。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import configure
from mipl_installer.configure import TargetConfig
from mipl_installer.util import EXIT_CONFIGURE, InstallerError
from tests.support import FakeRunner

ROOT_UUID = "11111111-1111-1111-1111-111111111111"
ESP_UUID = "22222222-2222-2222-2222-222222222222"


class TestFstab(unittest.TestCase):
    def test_uuid_based_and_esp_on_boot(self):
        text = configure.fstab_text(ROOT_UUID, ESP_UUID)
        self.assertIn(f"UUID={ROOT_UUID}\t/\t\text4\t{configure.ROOT_OPTIONS}", text)
        self.assertIn(f"UUID={ESP_UUID}\t/boot", text)
        self.assertIn("vfat", text)
        self.assertIn("fmask=0137,dmask=0027", text)
        self.assertTrue(text.endswith("\n"))

    def test_no_device_paths_leak_in(self):
        # 分区号会随盘变，fstab 里出现 /dev/ 就是没按 UUID 写
        text = configure.fstab_text(ROOT_UUID, ESP_UUID)
        self.assertNotIn("/dev/", text)


class TestLocales(unittest.TestCase):
    LOCALE_GEN = "\n".join([
        "# Configuration file for locale-gen",
        "#",
        "#en_US.UTF-8 UTF-8",
        "#zh_CN.UTF-8 UTF-8",
        "#zh_CN.GBK GBK",
        "#ja_JP.UTF-8 UTF-8",
    ])

    def test_enables_only_requested(self):
        out = configure.enable_locales(self.LOCALE_GEN, ("zh_CN.UTF-8", "en_US.UTF-8"))
        self.assertIn("\nzh_CN.UTF-8 UTF-8", out)
        self.assertIn("\nen_US.UTF-8 UTF-8", out)
        self.assertIn("#zh_CN.GBK GBK", out)
        self.assertIn("#ja_JP.UTF-8 UTF-8", out)
        self.assertTrue(out.endswith("\n"))

    def test_locale_conf_sets_lang(self):
        self.assertEqual(configure.locale_conf("zh_CN.UTF-8"), "LANG=zh_CN.UTF-8\n")


class TestUserAndHost(unittest.TestCase):
    def test_sudoers_dropin_unlocks_wheel(self):
        # sudo 包自带的 /etc/sudoers 里 %wheel 是注释掉的
        self.assertEqual(configure.sudoers_dropin(), "%wheel ALL=(ALL:ALL) ALL\n")

    def test_hosts_has_hostname(self):
        text = configure.hosts("mipl")
        self.assertIn("127.0.0.1\tlocalhost", text)
        self.assertIn("127.0.1.1\tmipl.localdomain\tmipl", text)

    def test_vconsole_has_no_font(self):
        # 目标清单里没有 terminus-font，写 FONT 就是开机报缺字体
        self.assertEqual(configure.vconsole_conf(), "KEYMAP=us\n")

    def test_rejects_bad_usernames(self):
        for bad in ("Mipl", "1abc", "with space", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(InstallerError):
                    configure.validate_user(bad)


class TestStaticFiles(unittest.TestCase):
    def test_writes_into_target(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            # locale.gen 由 glibc 提供，这里造一份「已装好 glibc」的样子
            (Path(tmp) / "etc").mkdir()
            (Path(tmp) / "etc/locale.gen").write_text("#zh_CN.UTF-8 UTF-8\n", encoding="utf-8")
            cfg = TargetConfig(target=tmp)

            configure.write_static_files(runner, cfg, ROOT_UUID, ESP_UUID)

            self.assertIn(f"UUID={ROOT_UUID}", (Path(tmp) / "etc/fstab").read_text(encoding="utf-8"))
            self.assertEqual((Path(tmp) / "etc/locale.conf").read_text(encoding="utf-8"), "LANG=zh_CN.UTF-8\n")
            self.assertEqual((Path(tmp) / "etc/hostname").read_text(encoding="utf-8"), "mipl\n")
            self.assertIn("zh_CN.UTF-8 UTF-8", (Path(tmp) / "etc/locale.gen").read_text(encoding="utf-8"))
            self.assertEqual((Path(tmp) / "etc/sudoers.d/10-wheel").read_text(encoding="utf-8"),
                             configure.sudoers_dropin())
            mode = (Path(tmp) / "etc/sudoers.d/10-wheel").stat().st_mode & 0o777
            self.assertEqual(mode, 0o440)          # sudo 会拒收 group/other 可写的 drop-in

    def test_missing_locale_gen_is_an_error(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InstallerError) as ctx:
                configure.write_static_files(runner, TargetConfig(target=tmp), ROOT_UUID, ESP_UUID)
            self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)


class TestChrootSteps(unittest.TestCase):
    def test_order_and_password_on_stdin(self):
        runner = FakeRunner()
        configure.run_in_chroot(runner, TargetConfig(target="/mnt"), "s3cret")
        commands = runner.commands()

        # 密码只能走 stdin，绝不能出现在 argv 里（进程列表与日志都会留档）
        self.assertTrue(all("s3cret" not in cmd for cmd in commands), commands)

        expected = [
            "arch-chroot /mnt useradd -m -G wheel -s /bin/bash mipl",
            "arch-chroot /mnt chpasswd",
            "arch-chroot /mnt locale-gen",
            "arch-chroot /mnt pacman-key --populate archlinux",
            "arch-chroot /mnt systemctl enable NetworkManager",
            "arch-chroot /mnt mkinitcpio -P",
        ]
        self.assertEqual(commands, expected)


if __name__ == "__main__":
    unittest.main()
