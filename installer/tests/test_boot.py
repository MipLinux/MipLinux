"""引导：systemd-boot 装到哪、entry 里写什么、NVRAM 写不进怎么办。

这一组守的是**检查点 4**（从盘重启能起来）。`--boot c` 只会在盘上没引导时
给一句 `no bootable device`，所以「该在的东西在不在」必须自己先断言。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import boot
from mipl_installer.configure import TargetConfig
from mipl_installer.util import EXIT_BOOT, InstallerError
from tests.support import FakeRunner

ROOT_UUID = "11111111-1111-1111-1111-111111111111"
EFIBOOTMGR = "efibootmgr"


class TestEntryContent(unittest.TestCase):
    def test_paths_are_relative_to_the_esp(self):
        text = boot.loader_entry(ROOT_UUID)
        self.assertIn("linux   /vmlinuz-linux", text)
        self.assertIn("initrd  /initramfs-linux.img", text)
        # ESP 就是 /boot，写成 /boot/vmlinuz-linux 会让 systemd-boot 找不到
        self.assertNotIn("/boot/vmlinuz-linux", text)

    def test_kernel_options(self):
        text = boot.loader_entry(ROOT_UUID)
        self.assertIn(f"root=UUID={ROOT_UUID} rw", text)
        self.assertIn("nvidia_drm.modeset=1", text)

    def test_loader_conf_points_at_our_entry(self):
        text = boot.loader_conf()
        self.assertIn(f"default {boot.ENTRY_NAME}", text)
        self.assertIn("timeout 3", text)


class TestEfiEntryDetection(unittest.TestCase):
    def test_recognises_ours_and_booctl_default(self):
        for line in (
            "Boot0001* MipLinux\tHD(1,GPT,...)",
            "Boot0001* Linux Boot Manager\tHD(1,GPT,...)",
            "Boot0003* systemd-boot\tHD(1,GPT,...)",
        ):
            with self.subTest(line=line):
                self.assertTrue(boot._has_entry(line))

    def test_empty_listing_means_missing(self):
        self.assertFalse(boot._has_entry("BootCurrent: 0001\nTimeout: 1 seconds\n"))


class TestInstallBootloader(unittest.TestCase):
    def test_installs_with_esp_path(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: "Boot0001* MipLinux\tHD(1,GPT,...)"})
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
            command = runner.assert_ran(self, "bootctl")
            self.assertEqual(command, f"arch-chroot {tmp} bootctl --esp-path=/boot install")
        self.assertNotIn("--no-variables", command)

    def test_writes_entry_and_loader_conf_onto_the_esp(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: "Boot0001* MipLinux"})
        with tempfile.TemporaryDirectory() as tmp:
            cfg = TargetConfig(target=tmp)
            boot.install_bootloader(runner, cfg, ROOT_UUID)
            entry = Path(boot.entry_path(cfg)).read_text(encoding="utf-8")
            loader = (Path(tmp) / "boot/loader/loader.conf").read_text(encoding="utf-8")
        self.assertIn(f"root=UUID={ROOT_UUID}", entry)
        self.assertIn(boot.ENTRY_NAME, loader)

    def test_creates_entry_when_firmware_has_none(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: "BootCurrent: 0001\n"})
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        created = runner.assert_ran(self, "efibootmgr --create")
        self.assertIn("--label MipLinux", created)

    def test_falls_back_to_removable_path_when_nvram_write_fails(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: "BootCurrent: 0001\n"})
        runner.fail_patterns.add("efibootmgr --create")
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        copy = runner.assert_ran(self, "cp")
        self.assertIn(boot.ESP_REMOVABLE_PATH, copy)

    def test_no_nvram_keeps_firmware_untouched_but_leaves_a_way_in(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID, no_nvram=True)
        self.assertIn("--no-variables", runner.assert_ran(self, "bootctl"))
        # 不写固件就必须留可移除介质路径，否则这块盘在真机上根本起不来
        self.assertIn(boot.ESP_REMOVABLE_PATH, runner.assert_ran(self, "cp"))


class TestVerify(unittest.TestCase):
    def _fake_esp(self, tmp: str, entry_uuid: str = ROOT_UUID) -> TargetConfig:
        cfg = TargetConfig(target=tmp)
        (Path(tmp) / "boot/loader/entries").mkdir(parents=True)
        (Path(tmp) / "boot/vmlinuz-linux").write_text("kernel", encoding="utf-8")
        (Path(tmp) / "boot/initramfs-linux.img").write_text("initramfs", encoding="utf-8")
        Path(boot.entry_path(cfg)).write_text(boot.loader_entry(entry_uuid), encoding="utf-8")
        return cfg

    def test_passes_when_everything_is_in_place(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            boot.verify(runner, self._fake_esp(tmp), ROOT_UUID)

    def test_fails_when_kernel_is_not_on_the_esp(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._fake_esp(tmp)
            (Path(tmp) / "boot/vmlinuz-linux").unlink()
            with self.assertRaises(InstallerError) as ctx:
                boot.verify(runner, cfg, ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)
        self.assertIn("vmlinuz-linux", str(ctx.exception))

    def test_fails_when_uuid_does_not_match(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._fake_esp(tmp, entry_uuid="99999999-9999-9999-9999-999999999999")
            with self.assertRaises(InstallerError) as ctx:
                boot.verify(runner, cfg, ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)
        self.assertIn("UUID", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
