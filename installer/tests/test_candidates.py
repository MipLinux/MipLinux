"""候选盘的枚举与事实采集（界面选盘页的数据源）。

判据全在 sysfs，所以搭一棵假目录就能验 —— 不需要真盘、不需要 root。
两条判据都必须独立成立：只认 `device` 会把光驱（它有 `device`）当盘列出来，
只认名字前缀会把 virtio 盘（`vda`）漏掉，两个都错都会让用户在安装器里
看见一块装不进去、或者根本看不见自己的盘。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import disk
from mipl_installer.util import InstallerError
from tests.support import FakeRunner

GiB = disk.GiB

#: 40 GiB 盘在 sysfs 里的扇区数（512 B 扇区）
SECTORS_40GIB = str(40 * GiB // 512)


def _disk(block: Path, name: str, *, device: bool = True, size: str | None = SECTORS_40GIB) -> Path:
    entry = block / name
    entry.mkdir(parents=True)
    if device:
        (entry / "device").mkdir()
    if size is not None:
        (entry / "size").write_text(size + "\n", encoding="utf-8")
    return entry


def _partition(parent: Path, name: str, number: str, start: str, size: str) -> Path:
    entry = parent / name
    entry.mkdir()
    (entry / "partition").write_text(number + "\n", encoding="utf-8")
    (entry / "start").write_text(start + "\n", encoding="utf-8")
    (entry / "size").write_text(size + "\n", encoding="utf-8")
    return entry


class _SysfsCase(unittest.TestCase):
    """一棵只有 `block/` 的假 sysfs。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.block = self.root / "block"
        self.block.mkdir()

    def inspect(self, name: str = "vda", **kwargs) -> disk.Candidate:
        params = dict(sysfs_root=str(self.root), sources=set(), runner=None)
        params.update(kwargs)
        return disk.inspect(f"/dev/{name}", **params)


class TestDetectDisks(_SysfsCase):
    def test_finds_a_real_disk(self):
        _disk(self.block, "vda")
        self.assertEqual(disk.detect_disks(sysfs_root=str(self.root), disk_root="/dev"), ["/dev/vda"])

    def test_name_prefix_rule_is_independent_of_the_device_rule(self):
        """**回归测试**：zram / loop / dm / md / sr / ram 在有 `device` 入口时也必须被排除。

        光有 `device` 判据不够：光驱（sr0）与软驱**有** `device`，但装不进去；
        zram0 / loop0 在 `lsblk` 里干脆被当成盘 —— 候选表里出现它们，用户会选错。
        """
        for name in ("zram0", "loop0", "dm-0", "md0", "sr0", "ram0"):
            _disk(self.block, name)
        _disk(self.block, "vda")
        self.assertEqual(disk.detect_disks(sysfs_root=str(self.root), disk_root="/dev"), ["/dev/vda"])

    def test_zero_size_is_not_a_disk(self):
        _disk(self.block, "vda")
        _disk(self.block, "vdb", size="0")
        self.assertEqual(disk.detect_disks(sysfs_root=str(self.root), disk_root="/dev"), ["/dev/vda"])

    def test_missing_size_is_not_a_disk(self):
        """没有 `size` 就不知道它多大，不能进候选表（否则「可选但装不下」）。"""
        _disk(self.block, "vda")
        _disk(self.block, "vdc", size=None)
        self.assertEqual(disk.detect_disks(sysfs_root=str(self.root), disk_root="/dev"), ["/dev/vda"])

    def test_missing_block_dir_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(disk.detect_disks(sysfs_root=tmp, disk_root="/dev"), [])


class TestPartitionGeometry(_SysfsCase):
    def test_sectors_are_converted_to_bytes(self):
        """sysfs 的 start / size 一律是 **512 字节扇区** —— 忘乘 512 会让条图画得很小。

        2048 扇区 = 1 MiB，1048576 扇区 = 512 MiB，两个数都精确到字节。
        """
        vda = _disk(self.block, "vda")
        _partition(vda, "vda1", "1", "2048", "1048576")
        part = self.inspect().partitions[0]
        self.assertEqual(part.start, 2048 * 512)
        self.assertEqual(part.size, 1048576 * 512)
        self.assertEqual(part.device, "/dev/vda1")

    def test_partitions_come_back_sorted_by_number(self):
        vda = _disk(self.block, "vda")
        # 故意先建 vda2，返回顺序仍要是 1、2（界面按分区号排，不按目录遍历顺序）
        _partition(vda, "vda2", "2", "1048576", "1048576")
        _partition(vda, "vda1", "1", "2048", "1046528")
        self.assertEqual([p.number for p in self.inspect().partitions], [1, 2])

    def test_non_numeric_children_are_skipped(self):
        """`partition` / `start` / `size` 有一个不是数字，就当没这个分区 —— 不猜。"""
        vda = _disk(self.block, "vda")
        _partition(vda, "vda1", "1", "2048", "1046528")
        _partition(vda, "vda2", "x", "4096", "2048")       # 分区号不是数字
        _partition(vda, "vda3", "3", "no", "2048")         # 起点不是数字
        _partition(vda, "vda4", "4", "4096", "no")         # 容量不是数字
        (vda / "vda5").mkdir()                             # 连 partition 文件都没有
        self.assertEqual([p.number for p in self.inspect().partitions], [1])


class TestInspectFacts(_SysfsCase):
    def test_in_use_when_the_disk_itself_is_mounted(self):
        _disk(self.block, "vda")
        self.assertTrue(self.inspect(sources={"/dev/vda"}).in_use)

    def test_in_use_when_a_partition_is_mounted(self):
        """运行环境自己的系统盘：`/dev/vda1` 挂在 / 上，整盘就是「正在使用」。"""
        _disk(self.block, "vda")
        self.assertTrue(self.inspect(sources={"/dev/vda1"}).in_use)

    def test_another_disks_partition_does_not_mark_this_one(self):
        _disk(self.block, "vda")
        self.assertFalse(self.inspect(sources={"/dev/vdb1"}).in_use)

    def test_removable_reads_the_sysfs_file(self):
        vda = _disk(self.block, "vda")
        self.assertFalse(self.inspect().removable)
        (vda / "removable").write_text("1\n", encoding="utf-8")
        self.assertTrue(self.inspect().removable)

    def test_model_strips_whitespace(self):
        vda = _disk(self.block, "vda")
        (vda / "device" / "model").write_text("  Virtual Disk  \n", encoding="utf-8")
        self.assertEqual(disk.model_of("/dev/vda", sysfs_root=str(self.root)), "Virtual Disk")

    def test_model_falls_back_to_vendor(self):
        """virtio-blk 没有 `model` 是正常的，这时用 `vendor`，别拿设备名冒充型号。"""
        vda = _disk(self.block, "vda")
        (vda / "device" / "vendor").write_text("ACME  \n", encoding="utf-8")
        self.assertEqual(disk.model_of("/dev/vda", sysfs_root=str(self.root)), "ACME")

    def test_model_is_empty_when_both_are_absent(self):
        _disk(self.block, "vda")
        self.assertEqual(disk.model_of("/dev/vda", sysfs_root=str(self.root)), "")


class TestUsableAndFits(unittest.TestCase):
    def _candidate(self, size: int, *, in_use: bool = False) -> disk.Candidate:
        return disk.Candidate(path="/dev/vda", model="", size=size, removable=False, in_use=in_use)

    def test_large_free_disk_is_usable(self):
        candidate = self._candidate(40 * GiB)
        self.assertFalse(candidate.too_small)
        self.assertTrue(candidate.usable)

    def test_small_disk_is_too_small_and_not_usable(self):
        candidate = self._candidate(2 * GiB)
        self.assertTrue(candidate.too_small)
        self.assertFalse(candidate.usable)

    def test_in_use_disk_is_not_usable_even_when_large(self):
        candidate = self._candidate(40 * GiB, in_use=True)
        self.assertFalse(candidate.too_small)
        self.assertFalse(candidate.usable)

    def test_fits_agrees_with_plan_layout(self):
        """`fits` 与 `plan_layout` 必须**同源**：两套阈值会让「列表里可选、装时被拒」。"""
        for size in (2 * GiB, 5 * GiB, 6 * GiB, 40 * GiB, 128 * GiB + 7):
            with self.subTest(size=size):
                try:
                    disk.plan_layout(size)
                    planned = True
                except InstallerError:
                    planned = False
                self.assertEqual(disk.fits(size), planned)


class TestBlkid(_SysfsCase):
    ESP_EXPORT = "\n".join([
        "DEVNAME=/dev/vda1",
        "TYPE=vfat",
        "LABEL=EFI",
        "PART_ENTRY_TYPE=c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
    ])

    def test_parses_key_value_lines_and_ignores_junk(self):
        text = "\n".join([
            "TYPE=vfat",
            "",
            "这一行没有等号",
            "LABEL=EFI",
        ])
        self.assertEqual(disk.parse_blkid_export(text), {"TYPE": "vfat", "LABEL": "EFI"})

    def test_esp_guid_is_case_insensitive(self):
        """`blkid` 的大小写随版本变，用 `==` 比 GUID 会让 ESP 时有时无。"""
        lower = FakeRunner(outputs={"blkid": self.ESP_EXPORT})
        upper = FakeRunner(outputs={"blkid": self.ESP_EXPORT.replace("c12a7328", "C12A7328")})
        self.assertEqual(disk._blkid_facts(lower, "/dev/vda1"), ("vfat", "EFI", True))
        self.assertEqual(disk._blkid_facts(upper, "/dev/vda1"), ("vfat", "EFI", True))

    def test_non_esp_type_guid_is_not_esp(self):
        text = "TYPE=ext4\nPART_ENTRY_TYPE=0fc63daf-8483-4772-8e79-3d69d8477de4\n"
        self.assertEqual(disk._blkid_facts(FakeRunner(outputs={"blkid": text}), "/dev/vda2"),
                         ("ext4", None, False))

    def test_probe_without_a_runner_is_empty(self):
        self.assertEqual(disk.probe(None, "/dev/vda1"), {})

    def test_probe_in_dry_run_attempts_no_subprocess(self):
        runner = FakeRunner(dry_run=True)
        self.assertEqual(disk.probe(runner, "/dev/vda1"), {})
        self.assertEqual(runner.history, [])

    def test_garbage_blkid_degrades_instead_of_exploding(self):
        """`blkid` 读不到（非 root、不认识的表）时只丢文件系统那两列，整页不能崩。"""
        vda = _disk(self.block, "vda")
        _partition(vda, "vda1", "1", "2048", "1048576")
        for output in ("", "这不是 export 格式\n"):
            with self.subTest(output=output):
                runner = FakeRunner(outputs={"blkid": output})
                candidates = disk.list_candidates(
                    sysfs_root=str(self.root), disk_root="/dev", sources=set(), runner=runner
                )
                self.assertEqual(len(candidates), 1)
                self.assertIsNone(candidates[0].table_type)
                part = candidates[0].partitions[0]
                self.assertIsNone(part.fs_type)
                self.assertIsNone(part.label)
                self.assertFalse(part.esp)


if __name__ == "__main__":
    unittest.main()
