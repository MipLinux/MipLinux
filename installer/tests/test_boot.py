"""引导：systemd-boot 装到哪、entry 里写什么、NVRAM 写不进怎么办。

这一组守的是**检查点 4**（从盘重启能起来）。`--boot c` 只会在盘上没引导时
给一句 `no bootable device`，所以「该在的东西在不在」必须自己先断言。
"""

from __future__ import annotations

import tempfile
import struct
import unittest
from unittest.mock import patch
from pathlib import Path

from mipl_installer import boot
from mipl_installer.configure import TargetConfig
from mipl_installer.util import EXIT_BOOT, InstallerError
from tests.support import FakeRunner

ROOT_UUID = "11111111-1111-1111-1111-111111111111"
EFIBOOTMGR = "efibootmgr"
ESP_UUID = "22222222-2222-2222-2222-222222222222"


def firmware_entry(guid=ESP_UUID, number=1, active=True, order="0001",
                   loader=r"\EFI\systemd\systemd-bootx64.efi", title="Linux Boot Manager"):
    return (f"BootOrder: {order}\nBoot0001{'*' if active else ' '} {title}\t"
            f"HD({number},GPT,{guid},0x800,0x100000)/File({loader})")


class EspFixture(unittest.TestCase):
    def setUp(self):
        identity = patch.object(boot, "_esp_identity", return_value=(
            "/dev/nvme0n1p1", "/dev/nvme0n1", 1, ESP_UUID))
        self.identity = identity.start()
        self.addCleanup(identity.stop)



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
    def test_matches_identity_regardless_of_title(self):
        self.assertTrue(boot._matches_esp(firmware_entry(title="Another label"), ESP_UUID, 1))

    def test_accepts_both_device_path_formats(self):
        wrapped = firmware_entry()
        raw = wrapped.replace(r"/File(\EFI\systemd\systemd-bootx64.efi)",
                              r"/\EFI\systemd\systemd-bootx64.efi")
        self.assertNotEqual(raw, wrapped)
        for listing in (wrapped, raw):
            with self.subTest(listing=listing):
                self.assertTrue(boot._matches_esp(listing, ESP_UUID, 1))
                self.assertFalse(boot._matches_esp(listing, ROOT_UUID, 1))
                self.assertFalse(boot._matches_esp(listing, ESP_UUID, 2))
                if listing == raw:
                    self.assertFalse(boot._matches_esp(listing + ".other", ESP_UUID, 1))

    def test_rejects_wrong_disk_partition_path_inactive_and_unordered_entries(self):
        for listing in (
            firmware_entry(guid=ROOT_UUID), firmware_entry(number=2),
            firmware_entry(loader=r"\EFI\other\boot.efi"),
            firmware_entry(active=False), firmware_entry(order="0002"),
            "BootOrder: 0001\nBoot0001* MipLinux",
            "BootCurrent: 0001\nLinux Boot Manager",
        ):
            with self.subTest(listing=listing):
                self.assertFalse(boot._matches_esp(listing, ESP_UUID, 1))


class TestEspIdentity(unittest.TestCase):
    def test_requires_an_exact_separate_vfat_mount(self):
        records = "1 0 8:2 / /mnt/mipl rw - ext4 /dev/sda2 rw\n"
        with patch.object(boot.util, "read_text", return_value=records):
            with self.assertRaises(InstallerError):
                boot._mounted_device("/mnt/mipl/boot", "vfat")
        records += "2 1 8:1 / /mnt/mipl/boot rw - vfat /dev/sda1 rw\n"
        with patch.object(boot.util, "read_text", return_value=records):
            self.assertEqual(boot._mounted_device("/mnt/mipl/boot", "vfat"), "/dev/sda1")
            with self.assertRaises(InstallerError):
                boot._mounted_device("/mnt/mipl", "vfat")

    def test_reads_partition_number_and_parent_from_sysfs(self):
        for device, parent, number in (("nvme0n1p3", "nvme0n1", 3), ("vda1", "vda", 1)):
            with self.subTest(device=device), tempfile.TemporaryDirectory() as tmp:
                node = Path(tmp) / parent / device
                node.mkdir(parents=True)
                (node / "partition").write_text(str(number))
                real_path = Path

                def path(value):
                    return real_path(tmp) / parent if value == "/sys/class/block" else real_path(value)

                with patch.object(boot, "Path", side_effect=path):
                    self.assertEqual(boot._partition_disk("/dev/" + device), ("/dev/" + parent, number))

    def test_requires_gpt_esp_type_and_valid_partition_uuid(self):
        valid = f"PART_ENTRY_TYPE={boot.disk.ESP_TYPE_GUID}\nPART_ENTRY_UUID={ESP_UUID}"
        with patch.object(boot, "_mounted_device", return_value="/dev/nvme0n1p3"), patch.object(
            boot, "_partition_disk", return_value=("/dev/nvme0n1", 3)
        ):
            self.assertEqual(boot._esp_identity(FakeRunner(outputs={"blkid": valid}), TargetConfig()),
                             ("/dev/nvme0n1p3", "/dev/nvme0n1", 3, ESP_UUID))
            for facts in ("", valid.replace(boot.disk.ESP_TYPE_GUID, ROOT_UUID),
                          valid.replace(ESP_UUID, "invalid")):
                with self.subTest(facts=facts), self.assertRaises(InstallerError):
                    boot._esp_identity(FakeRunner(outputs={"blkid": facts}), TargetConfig())


class TestInstallBootloader(EspFixture):
    def test_read_failure_falls_back_without_creating_entry(self):
        for reason in (None, "timeout"):
            runner = FakeRunner()
            original = runner.run

            def run(argv, **kwargs):
                if "efibootmgr" in argv:
                    self.assertTrue(kwargs.get("check", True))
                    raise InstallerError("read failed", EXIT_BOOT, reason=reason)
                return original(argv, **kwargs)

            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp, patch.object(
                runner, "run", side_effect=run
            ):
                boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
            " ".join(next(argv for argv in runner.history if argv[0] == "cp"))
            self.assertFalse(runner.find("--create"))

    def test_successful_create_is_read_back_and_checked(self):
        for after, fallback in ((firmware_entry(number=3), False), (firmware_entry(), True)):
            runner = FakeRunner()
            self.identity.return_value = ("/dev/nvme0n1p3", "/dev/nvme0n1", 3, ESP_UUID)
            original = runner.run
            reads = iter([firmware_entry(guid=ROOT_UUID), after])

            def run(argv, **kwargs):
                if "efibootmgr" in argv:
                    runner.history.append(argv)
                    return next(reads)
                return original(argv, **kwargs)

            with self.subTest(fallback=fallback), tempfile.TemporaryDirectory() as tmp, patch.object(
                runner, "run", side_effect=run
            ):
                boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
            self.assertIn("--disk /dev/nvme0n1 --part 3", runner.assert_ran(self, "--create"))
            self.assertEqual(len(runner.find("efibootmgr -v")), 2)
            self.assertEqual(bool([argv for argv in runner.history if argv[0] == "cp"]), fallback)

    def test_valid_existing_entry_does_not_create_another(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: firmware_entry()})
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        self.assertFalse(runner.find("--create"))

    def test_dry_run_preserves_firmware_command_preview_without_probing_mounts(self):
        runner = FakeRunner(dry_run=True)
        boot.install_bootloader(runner, TargetConfig(), "<dry-run>")
        self.identity.assert_not_called()
        self.assertEqual(len(runner.find("efibootmgr")), 1)
        self.assertFalse(runner.find("efibootmgr -v"))

    def test_rejects_invalid_esp_before_installing_bootloader(self):
        self.identity.side_effect = InstallerError("wrong ESP", EXIT_BOOT)
        runner = FakeRunner()
        with self.assertRaises(InstallerError):
            boot.install_bootloader(runner, TargetConfig(), ROOT_UUID)
        self.assertFalse(runner.history)

    def test_timeout_reinstalls_files_without_touching_nvram(self):
        runner = FakeRunner()
        original_run = runner.run

        def run(argv, **kwargs):
            if "bootctl" in argv and "--no-variables" not in argv:
                runner.history.append(argv)
                raise InstallerError("timeout", EXIT_BOOT, reason="timeout")
            return original_run(argv, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "run", side_effect=run):
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        commands = runner.commands()
        retry = runner.assert_ran(self, "bootctl --esp-path=/boot --no-variables install")
        copy = " ".join(next(argv for argv in runner.history if argv[0] == "cp"))
        self.assertLess(commands.index(retry), commands.index(copy))
        self.assertFalse(runner.find("efibootmgr"))

    def test_normal_bootctl_failure_retries_without_nvram(self):
        runner = FakeRunner()
        original = runner.run

        def run(argv, **kwargs):
            if "bootctl" in argv and "--no-variables" not in argv:
                runner.history.append(argv)
                raise InstallerError("NVRAM write failed", EXIT_BOOT)
            return original(argv, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "run", side_effect=run):
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        runner.assert_ran(self, "bootctl --esp-path=/boot --no-variables install")
        self.assertTrue(any(argv[0] == "cp" for argv in runner.history))
        self.assertFalse(runner.find("efibootmgr"))

    def test_normal_file_install_failure_still_stops(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner, "run", side_effect=InstallerError("I/O failure", EXIT_BOOT)
        ) as run:
            with self.assertRaises(InstallerError) as ctx:
                boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(any(argv[0] == "cp" for argv in runner.history))

    def test_no_nvram_timeout_is_a_boot_failure(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner, "run", side_effect=InstallerError("timeout", EXIT_BOOT, reason="timeout")
        ):
            with self.assertRaises(InstallerError):
                boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID, no_nvram=True)

    def test_failed_file_reinstall_does_not_continue_to_fallback(self):
        runner = FakeRunner()
        original_run = runner.run

        def run(argv, **kwargs):
            if "bootctl" in argv:
                runner.history.append(argv)
                if "--no-variables" not in argv:
                    raise InstallerError("timeout", EXIT_BOOT, reason="timeout")
                raise InstallerError("file install failed", EXIT_BOOT)
            return original_run(argv, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "run", side_effect=run):
            with self.assertRaises(InstallerError) as ctx:
                boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)
        self.assertFalse([argv for argv in runner.history if argv[0] == "cp"])
        self.assertFalse(runner.find("efibootmgr"))

    def test_installs_with_esp_path(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: firmware_entry()})
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
            command = runner.assert_ran(self, "bootctl")
            self.assertEqual(command, f"arch-chroot {tmp} bootctl --esp-path=/boot install")
        self.assertNotIn("--no-variables", command)

    def test_writes_entry_and_loader_conf_onto_the_esp(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: firmware_entry()})
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
        self.assertIn("--disk /dev/nvme0n1 --part 1", created)

    def test_falls_back_to_removable_path_when_nvram_write_fails(self):
        runner = FakeRunner(outputs={EFIBOOTMGR: "BootCurrent: 0001\n"})
        runner.fail_patterns.add("efibootmgr --create")
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID)
        copy = " ".join(next(argv for argv in runner.history if argv[0] == "cp"))
        self.assertIn(boot.ESP_REMOVABLE_PATH, copy)

    def test_no_nvram_keeps_firmware_untouched_but_leaves_a_way_in(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            boot.install_bootloader(runner, TargetConfig(target=tmp), ROOT_UUID, no_nvram=True)
        self.assertIn("--no-variables", runner.assert_ran(self, "bootctl"))
        # 不写固件就必须留可移除介质路径，否则这块盘在真机上根本起不来
        self.assertIn(boot.ESP_REMOVABLE_PATH, " ".join(next(argv for argv in runner.history if argv[0] == "cp")))


class TestVerify(EspFixture):
    def setUp(self):
        super().setUp()
        mounted = patch.object(boot, "_mounted_device", return_value="/dev/nvme0n1p2")
        mounted.start()
        self.addCleanup(mounted.stop)

    def runner(self):
        return FakeRunner(outputs={"blkid": ROOT_UUID})

    def _fake_esp(self, tmp: str, entry_uuid: str = ROOT_UUID) -> TargetConfig:
        cfg = TargetConfig(target=tmp)
        (Path(tmp) / "boot/loader/entries").mkdir(parents=True)
        (Path(tmp) / "boot/vmlinuz-linux").write_text("kernel", encoding="utf-8")
        (Path(tmp) / "boot/initramfs-linux.img").write_text("initramfs", encoding="utf-8")
        for name in (boot.ESP_SYSTEMD_BOOT, boot.ESP_REMOVABLE_PATH):
            path = Path(tmp) / "boot" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            header = bytearray(158)
            header[:2] = b"MZ"
            struct.pack_into("<I", header, 60, 64)
            header[64:68] = b"PE\0\0"
            for offset, value in ((68, 0x8664), (84, 70), (88, 0x20b), (156, 10)):
                struct.pack_into("<H", header, offset, value)
            path.write_bytes(header)
        Path(boot.entry_path(cfg)).write_text(boot.loader_entry(entry_uuid), encoding="utf-8")
        return cfg

    def test_rejects_actual_root_uuid_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._fake_esp(tmp)
            with self.assertRaises(InstallerError) as ctx:
                boot.verify(FakeRunner(outputs={"blkid": ESP_UUID}), cfg, ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)

    def test_rejects_missing_empty_or_corrupt_efi_files(self):
        for name in (boot.ESP_SYSTEMD_BOOT, boot.ESP_REMOVABLE_PATH):
            for value in (None, b"", b"corrupt"):
                with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as tmp:
                    cfg = self._fake_esp(tmp)
                    path = Path(tmp) / "boot" / name
                    if value is None:
                        path.unlink()
                    else:
                        path.write_bytes(value)
                    with self.assertRaises(InstallerError) as ctx:
                        boot.verify(self.runner(), cfg, ROOT_UUID)
                    self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)

    def test_rejects_wrong_efi_architecture_or_subsystem(self):
        for offset, value in ((68, 0x14c), (156, 3)):
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as tmp:
                cfg = self._fake_esp(tmp)
                path = Path(tmp) / "boot" / boot.ESP_SYSTEMD_BOOT
                contents = bytearray(path.read_bytes())
                struct.pack_into("<H", contents, offset, value)
                path.write_bytes(contents)
                with self.assertRaises(InstallerError):
                    boot.verify(self.runner(), cfg, ROOT_UUID)

    def test_passes_when_everything_is_in_place(self):
        runner = self.runner()
        with tempfile.TemporaryDirectory() as tmp:
            boot.verify(runner, self._fake_esp(tmp), ROOT_UUID)

    def test_fails_when_kernel_is_not_on_the_esp(self):
        runner = self.runner()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._fake_esp(tmp)
            (Path(tmp) / "boot/vmlinuz-linux").unlink()
            with self.assertRaises(InstallerError) as ctx:
                boot.verify(runner, cfg, ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)
        self.assertIn("vmlinuz-linux", str(ctx.exception))

    def test_fails_when_uuid_does_not_match(self):
        runner = self.runner()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._fake_esp(tmp, entry_uuid="99999999-9999-9999-9999-999999999999")
            with self.assertRaises(InstallerError) as ctx:
                boot.verify(runner, cfg, ROOT_UUID)
        self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)
        self.assertIn("UUID", str(ctx.exception))

    def test_rejects_uuid_prefix_comments_and_duplicate_root_options(self):
        for entry in (
            boot.loader_entry(ROOT_UUID + "0"),
            "# " + boot.loader_entry(ROOT_UUID).replace("\n", "\n# "),
            boot.loader_entry(ROOT_UUID).replace(" rw", " root=/dev/wrong rw"),
        ):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                cfg = self._fake_esp(tmp)
                Path(boot.entry_path(cfg)).write_text(entry, encoding="utf-8")
                with self.assertRaises(InstallerError) as ctx:
                    boot.verify(self.runner(), cfg, ROOT_UUID)
                self.assertEqual(ctx.exception.exit_code, EXIT_BOOT)


if __name__ == "__main__":
    unittest.main()
