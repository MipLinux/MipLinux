"""分区布局与「该不该动手」的守卫。

这一组是纯算数 + 纯判断，跑得飞快，也正是最该被钉死的部分：
布局算错、守卫放行，代价是别人盘上的数据。
"""

from __future__ import annotations

import unittest
from unittest import mock

from mipl_installer import disk
from mipl_installer.util import EXIT_GUARD, InstallerError

GiB = disk.GiB
MiB = disk.MiB


class TestPlanLayout(unittest.TestCase):
    def test_40gib_default(self):
        layout = disk.plan_layout(40 * GiB)
        self.assertEqual(layout.esp_start, 1 * MiB)          # 1 MiB 对齐，不占 0 扇区
        self.assertEqual(layout.esp_size, 512 * MiB)
        self.assertEqual(layout.root_start, 513 * MiB)       # ESP 之后重新对齐
        self.assertLessEqual(layout.root_start + layout.root_size, 40 * GiB)

    def test_root_is_aligned_and_tail_is_left_alone(self):
        # 故意给一个不整的数字：尾部余数只能被丢掉，不能被算进 root
        layout = disk.plan_layout(40 * GiB + 12345)
        self.assertEqual(layout.root_size % MiB, 0)
        self.assertLessEqual(layout.root_start + layout.root_size, 40 * GiB + 12345)

    def test_smallest_accepted(self):
        total = disk.ALIGN + disk.ESP_SIZE + disk.MIN_ROOT_SIZE
        layout = disk.plan_layout(total)
        self.assertGreaterEqual(layout.root_size, disk.MIN_ROOT_SIZE)

    def test_too_small_is_refused(self):
        with self.assertRaises(InstallerError) as ctx:
            disk.plan_layout(2 * GiB)
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
        self.assertIn("太小", str(ctx.exception))


class TestMountSources(unittest.TestCase):
    SAMPLE = "\n".join([
        "25 30 0:23 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw",
        "26 30 0:24 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sys rw",
        "31 30 8:1 / / rw,relatime - ext4 /dev/vda1 rw",
        "35 30 8:2 / /boot rw,relatime - vfat /dev/vda2 rw",
        "40 30 0:50 / /run/user/1000 rw - tmpfs tmpfs rw",
    ])

    def test_takes_the_source_column_not_the_mountpoint(self):
        sources = disk.mount_sources(self.SAMPLE)
        self.assertIn("/dev/vda1", sources)
        self.assertIn("/dev/vda2", sources)
        self.assertNotIn("/", sources)          # 挂载点那一列不是设备
        self.assertNotIn("/proc", sources)

    def test_ignores_malformed_lines(self):
        self.assertEqual(disk.mount_sources("garbage without separator\n"), set())


class TestSameDevice(unittest.TestCase):
    def test_partition_belongs_to_disk(self):
        self.assertTrue(disk.same_device("/dev/vda1", "/dev/vda"))
        self.assertTrue(disk.same_device("/dev/nvme0n1p2", "/dev/nvme0n1"))
        self.assertTrue(disk.same_device("/dev/loop0p1", "/dev/loop0"))

    def test_other_disk_is_not_the_same(self):
        self.assertFalse(disk.same_device("/dev/vdb1", "/dev/vda"))
        self.assertFalse(disk.same_device("/dev/vda", "/dev/vda1"))


class TestAssertUsable(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch("mipl_installer.util.is_block_device", return_value=True),
            mock.patch("mipl_installer.util.is_partition", return_value=False),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def _call(self, **kwargs):
        params = dict(
            device="/dev/vda",
            size_bytes=40 * GiB,
            sources={"/dev/vdb1"},
            target_mountpoint="/mnt",
            target_is_mountpoint=False,
        )
        params.update(kwargs)
        return disk.assert_usable(**params)

    def test_happy_path(self):
        layout = self._call()
        self.assertEqual(layout.esp_size, 512 * MiB)

    def test_refuses_non_block_device(self):
        with mock.patch("mipl_installer.util.is_block_device", return_value=False):
            with self.assertRaises(InstallerError) as ctx:
                self._call(device="/tmp/notadisk")
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)

    def test_refuses_partition(self):
        with mock.patch("mipl_installer.util.is_partition", return_value=True):
            with self.assertRaises(InstallerError) as ctx:
                self._call(device="/dev/vda1")
        self.assertIn("分区", str(ctx.exception))
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)

    def test_refuses_mounted_target(self):
        with self.assertRaises(InstallerError) as ctx:
            self._call(target_is_mountpoint=True)
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)

    def test_refuses_disk_in_use(self):
        # 这是最要命的一条：运行环境自己的盘
        with self.assertRaises(InstallerError) as ctx:
            self._call(sources={"/", "/dev/vda2", "/dev/vda1"})
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
        self.assertIn("正在被使用", str(ctx.exception))

    def test_refuses_small_disk(self):
        with self.assertRaises(InstallerError) as ctx:
            self._call(size_bytes=2 * GiB)
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)


class TestPartitionPaths(unittest.TestCase):
    VIRTIO = "/dev/vda disk\n/dev/vda1 part\n/dev/vda2 part\n"
    NVME = "/dev/nvme0n1 disk\n/dev/nvme0n1p1 part\n/dev/nvme0n1p2 part\n"
    LOOP = "/dev/loop0 disk\n/dev/loop0p1 part\n/dev/loop0p2 part\n"

    def test_three_naming_schemes(self):
        for tree, expected in (
            (self.VIRTIO, ("/dev/vda1", "/dev/vda2")),
            (self.NVME, ("/dev/nvme0n1p1", "/dev/nvme0n1p2")),
            (self.LOOP, ("/dev/loop0p1", "/dev/loop0p2")),
        ):
            with self.subTest(tree=tree):
                self.assertEqual(disk.partition_paths(tree), expected)

    def test_refuses_when_partitions_are_missing(self):
        with self.assertRaises(InstallerError) as ctx:
            disk.partition_paths("/dev/vda disk\n")
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)


if __name__ == "__main__":
    unittest.main()
