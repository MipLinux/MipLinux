"""目标系统里那些「写出来的文件」：fstab、locale、用户、hosts、sudoers。

能写成文件的就写成文件 —— 这一组是纯函数与真文件的对拍，不需要 root，
也不需要 QEMU。
"""

from __future__ import annotations

import tempfile
import subprocess
import os
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from mipl_installer import configure
from mipl_installer.configure import TargetConfig
from mipl_installer.util import EXIT_CONFIGURE, InstallerError
from tests.support import FakeRunner, RecordingReporter

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

    def test_enables_case_insensitive_and_normalized(self):
        out = configure.enable_locales(self.LOCALE_GEN, ("zh_cn.utf8",))
        self.assertIn("\nzh_CN.UTF-8 UTF-8", out)
        self.assertTrue(configure.has_locale(self.LOCALE_GEN, "zh_CN.utf8"))
        self.assertTrue(configure.has_locale(self.LOCALE_GEN, "ZH_CN.UTF-8"))
        self.assertFalse(configure.has_locale(self.LOCALE_GEN, "zh_HK.UTF-8"))

    def test_locale_conf_matches_live_factory_settings(self):
        self.assertEqual(
            configure.locale_conf("zh_CN.UTF-8"),
            "LANG=zh_CN.UTF-8\nLANGUAGE=zh_CN:zh:en_US:en\n",
        )

    def test_locale_conf_other_locales_have_no_language(self):
        self.assertEqual(configure.locale_conf("en_US.UTF-8"), "LANG=en_US.UTF-8\n")

    def test_environment_matches_live_factory_settings(self):
        self.assertEqual(
            configure.environment_text(),
            "GTK_IM_MODULE=fcitx\nQT_IM_MODULE=fcitx\nXMODIFIERS=@im=fcitx\n",
        )


class TestUserAndHost(unittest.TestCase):
    def test_reserved_accounts_fail_in_disk_preflight(self):
        from mipl_installer.pipeline import Plan, preflight
        for user in ("root", "nobody", "daemon", "dbus", "alpm"):
            with self.subTest(user=user), self.assertRaises(InstallerError):
                preflight(Plan(disk="/dev/FAKE", user=user))

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

    def test_rejects_control_chars_in_passwords(self):
        for bad in ("pw\n", "pw\r", "pw\0"):
            with self.subTest(bad=bad):
                with self.assertRaises(InstallerError) as ctx:
                    configure._validate_passwords(bad, None)
                self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)


class TestStaticFiles(unittest.TestCase):
    def test_config_modes_do_not_depend_on_inherited_umask(self):
        for mask in (0o077, 0o000):
            with self.subTest(mask=mask), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "etc").mkdir()
                (root / "etc/locale.gen").write_text("#zh_CN.UTF-8 UTF-8\n")
                old = os.umask(mask)
                try:
                    configure.write_static_files(FakeRunner(), TargetConfig(target=tmp), ROOT_UUID, ESP_UUID)
                    source = root / "font-source"
                    source.write_text("<fontconfig/>\n")
                    configure.copy_fonts_conf(FakeRunner(), TargetConfig(target=tmp, fonts_conf=str(source)))
                finally:
                    os.umask(old)
                for name in ("fstab", "locale.conf", "environment", "hostname", "hosts", "locale.gen", "fonts/local.conf"):
                    self.assertEqual((root / "etc" / name).stat().st_mode & 0o777, 0o644)
                self.assertEqual((root / "etc/sudoers.d/10-wheel").stat().st_mode & 0o777, 0o440)
                self.assertEqual((root / "etc/fonts").stat().st_mode & 0o777, 0o755)
                self.assertEqual((root / "etc/sudoers.d").stat().st_mode & 0o777, 0o755)

    def test_writes_into_target(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            # locale.gen 由 glibc 提供，这里造一份「已装好 glibc」的样子
            (Path(tmp) / "etc").mkdir()
            (Path(tmp) / "etc/locale.gen").write_text("#zh_CN.UTF-8 UTF-8\n", encoding="utf-8")
            cfg = TargetConfig(target=tmp)

            configure.write_static_files(runner, cfg, ROOT_UUID, ESP_UUID)

            self.assertIn(f"UUID={ROOT_UUID}", (Path(tmp) / "etc/fstab").read_text(encoding="utf-8"))
            self.assertEqual((Path(tmp) / "etc/locale.conf").read_text(encoding="utf-8"),
                             configure.locale_conf("zh_CN.UTF-8"))
            self.assertEqual((Path(tmp) / "etc/environment").read_text(encoding="utf-8"),
                             configure.environment_text())
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

    def test_locale_failure_does_not_write_static_files(self):
        for content in (None, "#en_US.UTF-8 UTF-8\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                etc = Path(tmp) / "etc"
                etc.mkdir()
                hostname = etc / "hostname"
                hostname.write_text("keep-me\n")
                if content is not None:
                    (etc / "locale.gen").write_text(content)
                runner = FakeRunner()
                with self.assertRaises(InstallerError) as ctx:
                    configure.write_static_files(runner, TargetConfig(target=tmp), ROOT_UUID, ESP_UUID)
                self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
                self.assertEqual(hostname.read_text(), "keep-me\n")
                self.assertFalse((etc / "fstab").exists())
                self.assertFalse(runner.history)

    def test_localtime_replaces_directory_symlink(self):
        class LinkRunner(FakeRunner):
            def run(self, argv, **kwargs):
                super().run(argv, **kwargs)
                if argv[0] == "ln":
                    subprocess.run(argv, check=True, capture_output=True)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc").mkdir()
            (root / "etc/locale.gen").write_text("#zh_CN.UTF-8 UTF-8\n")
            old = root / "old-zoneinfo"
            old.mkdir()
            localtime = root / "etc/localtime"
            localtime.symlink_to(old, target_is_directory=True)
            configure.write_static_files(LinkRunner(), TargetConfig(target=tmp), ROOT_UUID, ESP_UUID)
            self.assertEqual(str(localtime.readlink()), "/usr/share/zoneinfo/Asia/Shanghai")
            self.assertEqual(list(old.iterdir()), [])


class TestFontsConf(unittest.TestCase):
    FALLBACK = """<?xml version="1.0"?>\n<fontconfig>\n</fontconfig>\n"""

    def test_copies_from_running_system(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            (Path(src) / "local.conf").write_text(self.FALLBACK, encoding="utf-8")
            cfg = TargetConfig(target=dst, fonts_conf=str(Path(src) / "local.conf"))
            configure.copy_fonts_conf(FakeRunner(), cfg)
            self.assertEqual((Path(dst) / "etc/fonts/local.conf").read_text(encoding="utf-8"),
                             self.FALLBACK)

    def test_missing_source_is_gracefully_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as dst:
            reporter = RecordingReporter()
            configure.copy_fonts_conf(
                FakeRunner(reporter=reporter), TargetConfig(target=dst, fonts_conf="/nonexistent/local.conf")
            )
            self.assertFalse((Path(dst) / "etc/fonts/local.conf").exists())
            self.assertTrue(any("跳过字体 fallback 复制" in note for note in reporter.notes))

    def test_missing_source_tolerated_in_dry_run(self):
        with tempfile.TemporaryDirectory() as dst:
            configure.copy_fonts_conf(
                FakeRunner(dry_run=True),
                TargetConfig(target=dst, fonts_conf="/nonexistent/local.conf"))


class TestReflectorGuard(unittest.TestCase):
    PASSWD_OK = {"passwd -S mipl": "mipl P 2026-09-22 0 99999 7 -1"}

    def test_guard_lists_disable_only_when_present(self):
        self.assertEqual(configure.reflector_guard(True),
                         ["systemctl", "disable", "reflector.timer", "reflector.service"])
        self.assertEqual(configure.reflector_guard(False), [])

    def test_target_has_reflector_detects_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(configure.target_has_reflector(tmp))
            unit = Path(tmp) / "usr/lib/systemd/system/reflector.timer"
            unit.parent.mkdir(parents=True)
            unit.write_text("", encoding="utf-8")
            self.assertTrue(configure.target_has_reflector(tmp))

    def test_run_in_chroot_without_reflector_adds_no_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            TestChrootSteps.plant_keyring(tmp)
            runner = FakeRunner(outputs=dict(self.PASSWD_OK))
            configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
            self.assertTrue(all("reflector" not in cmd for cmd in runner.commands()), runner.commands())


class TestChrootSteps(unittest.TestCase):
    PASSWD_OK = {"passwd -S mipl": "mipl P 2026-09-22 0 99999 7 -1",
                 "passwd -S root": "root P 2026-09-22 0 99999 7 -1"}

    @staticmethod
    def plant_keyring(tmp: str) -> None:
        """造出「pacstrap 已装完 archlinuxcn-keyring」的目标现场（#135）。"""
        keyring = Path(tmp) / configure.ARCHLINUXCN_KEYRING
        keyring.parent.mkdir(parents=True, exist_ok=True)
        keyring.write_text("", encoding="utf-8")

    def test_colon_passwords_reach_chpasswd_intact_on_stdin(self):
        runner = FakeRunner(outputs=dict(self.PASSWD_OK))
        original = runner.run
        inputs = []
        def run(argv, **kwargs):
            if argv[-1] == "chpasswd":
                inputs.append(kwargs.get("input"))
            return original(argv, **kwargs)
        runner.run = run
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            configure.run_in_chroot(runner, TargetConfig(target=tmp), ":user:fixture:", "root:fixture")
        self.assertEqual(inputs, ["mipl::user:fixture:\n", "root:root:fixture\n"])
        self.assertFalse(any("fixture" in cmd for cmd in runner.commands()))

    def test_invalid_passwords_fail_before_any_command(self):
        for bad in ("", "example\nextra", "example\rextra", "example\x00extra"):
            for root in (False, True):
                with self.subTest(root=root, bad=repr(bad)):
                    runner = FakeRunner()
                    with self.assertRaises(InstallerError) as ctx:
                        configure.run_in_chroot(runner, TargetConfig(), "valid" if root else bad,
                                                bad if root else None)
                    self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
                    self.assertEqual(runner.history, [])
                    if bad:
                        self.assertNotIn(bad, str(ctx.exception))

    def test_configure_entry_rejects_invalid_password_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeRunner()
            with self.assertRaises(InstallerError):
                configure.configure_system(runner, TargetConfig(target=tmp), root_uuid=ROOT_UUID,
                                           esp_uuid=ESP_UUID, password="bad\nvalue")
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertEqual(runner.history, [])

    def test_retry_after_late_failure_reuses_install_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            passwd = Path(tmp) / "etc/passwd"
            passwd.parent.mkdir()
            runner = FakeRunner(outputs=dict(self.PASSWD_OK))
            original_run = runner.run

            def run(argv, **kwargs):
                result = original_run(argv, **kwargs)
                if "useradd" in argv:
                    passwd.write_text("mipl:x:1000:1000::/home/mipl:/bin/bash\n")
                return result

            runner.run = run
            runner.fail_patterns.add("mkinitcpio -P")
            with self.assertRaises(InstallerError):
                configure.run_in_chroot(runner, TargetConfig(target=tmp), "valid")
            runner.fail_patterns.clear()
            home_info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=1000, st_gid=1000)
            with patch.object(configure.os, "lstat", return_value=home_info):
                configure.run_in_chroot(runner, TargetConfig(target=tmp), "valid")
            self.assertEqual(len(runner.find("useradd")), 1)
            self.assertEqual(len(runner.find("usermod -a -G wheel")), 1)
            self.assertEqual(len(runner.find("mkinitcpio -P")), 2)

    def test_missing_or_unsafe_home_is_not_silently_reused(self):
        cases = (
            FileNotFoundError("missing home"),
            SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=1000, st_gid=1000),
            SimpleNamespace(st_mode=stat.S_IFDIR, st_uid=0, st_gid=1000),
            SimpleNamespace(st_mode=stat.S_IFDIR, st_uid=1000, st_gid=0),
        )
        for home in cases:
            with self.subTest(home=home), tempfile.TemporaryDirectory() as tmp:
                self.plant_keyring(tmp)
                (Path(tmp) / "etc").mkdir()
                (Path(tmp) / "etc/passwd").write_text("mipl:x:1000:1000::/home/mipl:/bin/bash\n")
                parent = SimpleNamespace(st_mode=stat.S_IFDIR, st_uid=0, st_gid=0)
                runner = FakeRunner(outputs=dict(self.PASSWD_OK))
                with patch.object(configure.os, "lstat", side_effect=[parent, home]):
                    with self.assertRaises(InstallerError):
                        configure.run_in_chroot(runner, TargetConfig(target=tmp), "valid")
                self.assertEqual(runner.history, [])

    def test_existing_system_account_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            (Path(tmp) / "etc").mkdir()
            (Path(tmp) / "etc/passwd").write_text("mipl:x:0:0::/root:/bin/bash\n")
            runner = FakeRunner()
            with self.assertRaises(InstallerError):
                configure.run_in_chroot(runner, TargetConfig(target=tmp), "valid")
            self.assertEqual(runner.history, [])

    def test_order_and_password_on_stdin(self):
        runner = FakeRunner(outputs=dict(self.PASSWD_OK))
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
        commands = runner.commands()

        # 密码只能走 stdin，绝不能出现在 argv 里（进程列表与日志都会留档）
        self.assertTrue(all("s3cret" not in cmd for cmd in commands), commands)

        order = [
            f"arch-chroot {tmp} useradd -m -G wheel -s /bin/bash mipl",
            f"arch-chroot {tmp} chpasswd",
            f"arch-chroot {tmp} passwd -S mipl",
            f"arch-chroot {tmp} locale-gen",
            f"arch-chroot {tmp} pacman-key --populate archlinux",
            # archlinuxcn 的 populate 排在 archlinux 之后（#135）：装后 conf 已收紧，
            # 它依赖的 keyring 包是 pacstrap 装的，只可能在这里出现
            f"arch-chroot {tmp} pacman-key --populate archlinuxcn",
            f"arch-chroot {tmp} systemctl enable NetworkManager",
            f"arch-chroot {tmp} systemctl enable mipl-mirror-watch.service",
            f"arch-chroot {tmp} mkinitcpio -P",
        ]
        positions = [commands.index(cmd) for cmd in order]
        self.assertEqual(positions, sorted(positions), commands)

    def test_user_password_is_verified_not_assumed(self):
        """`chpasswd` 空输入时什么都不做却退 0 —— 所以必须回头问一句「设上了吗」。"""
        runner = FakeRunner(outputs=dict(self.PASSWD_OK))
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
        runner.assert_ran(self, "passwd -S mipl")

    def test_rejects_when_the_password_did_not_stick(self):
        runner = FakeRunner(outputs={"passwd -S mipl": "mipl L 2026-09-22 0 99999 7 -1"})
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            with self.assertRaises(InstallerError) as ctx:
                configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
            self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
            self.assertIn("密码没设上", str(ctx.exception))

    def test_root_password_when_asked(self):
        runner = FakeRunner(outputs=dict(self.PASSWD_OK))
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret", "rootpw")
        commands = runner.commands()
        self.assertEqual(len([c for c in commands if c.endswith("chpasswd")]), 2)
        runner.assert_ran(self, "passwd -S root")
        self.assertTrue(all("rootpw" not in cmd for cmd in commands), commands)

    def test_root_left_locked_is_said_out_loud(self):
        """不设 root 密码可以，但**不许静默** —— 装完得让人知道 root 登不进去。"""
        reporter = RecordingReporter()
        runner = FakeRunner(outputs=dict(self.PASSWD_OK), reporter=reporter)
        with tempfile.TemporaryDirectory() as tmp:
            self.plant_keyring(tmp)
            configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
        self.assertNotIn("passwd -S root", "\n".join(runner.commands()))
        runner.assert_ran(self, "passwd -l root")
        self.assertIn("root", reporter.text())
        self.assertIn("锁定", reporter.text())

    def test_missing_archlinuxcn_keyring_is_a_hard_error(self):
        """目标里没有 archlinuxcn-keyring 时不许静默：收紧的 conf 会让第一次
        `pacman -Syu` 直接验签失败，问题必须在安装阶段就炸出来（#135）。"""
        runner = FakeRunner(outputs=dict(self.PASSWD_OK))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InstallerError) as ctx:
                configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
            self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
            self.assertIn("archlinuxcn", str(ctx.exception))
            self.assertEqual(runner.history, [])

    def test_dry_run_previews_populate_without_the_keyring_file(self):
        # dry-run 的目标是「预览命令序列」，盘上自然没有 pacstrap 的产物
        runner = FakeRunner(dry_run=True, outputs=dict(self.PASSWD_OK))
        with tempfile.TemporaryDirectory() as tmp:
            configure.run_in_chroot(runner, TargetConfig(target=tmp), "s3cret")
        runner.assert_ran(self, "pacman-key --populate archlinuxcn")


if __name__ == "__main__":
    unittest.main()
