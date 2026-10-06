"""分区布局与「该不该动手」的守卫。

这一组是纯算数 + 纯判断，跑得飞快，也正是最该被钉死的部分：
布局算错、守卫放行，代价是别人盘上的数据。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
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
        total = disk.ALIGN + disk.ESP_SIZE + disk.MIN_ROOT_SIZE + disk.GPT_TAIL_RESERVE
        layout = disk.plan_layout(total)
        self.assertGreaterEqual(layout.root_size, disk.MIN_ROOT_SIZE)

    def test_root_leaves_room_for_the_backup_gpt(self):
        """**回归测试**：root 不许压到盘尾的 GPT 备份表头。

        压上去的后果实测过：内核要么裁短、要么干脆不收下那个分区 ——
        `/proc/partitions` 里少一个、`/dev` 里没有节点，而 `lsblk` 照样把盘上的表
        列出来（它自己去读设备），于是报错完全指不到布局。
        """
        for total in (40 * GiB, 6 * GiB, 128 * GiB + 7):
            with self.subTest(total=total):
                layout = disk.plan_layout(total)
                tail = total - (layout.root_start + layout.root_size)
                self.assertGreaterEqual(tail, disk.GPT_TAIL_RESERVE)

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
        # 失败码是**给界面的**：界面拿它挑自己的句子，并给出「卸载 /mnt」那个按钮
        # （见 queries.unmount_target）。没有它，界面只能去比对中文报错。
        self.assertEqual(ctx.exception.reason, "targetMounted")

    def test_every_guard_carries_a_failure_code(self):
        """四条守卫都要有 `reason` —— 少一条，界面在那条路上就只能照抄中文。"""
        cases = {
            "notBlockDevice": {"is_block_device": False},
            "isPartition": {"is_partition": True},
            "targetMounted": {"target_is_mountpoint": True},
            "diskInUse": {"sources": {"/dev/vda2"}},   # 挂载来源里出现目标盘 = 它在被使用
        }
        for reason, overrides in cases.items():
            with self.subTest(reason=reason):
                patches = []
                if "is_block_device" in overrides:
                    patches.append(mock.patch("mipl_installer.util.is_block_device",
                                              return_value=overrides["is_block_device"]))
                if "is_partition" in overrides:
                    patches.append(mock.patch("mipl_installer.util.is_partition",
                                              return_value=overrides["is_partition"]))
                for patch in patches:
                    patch.start()
                try:
                    with self.assertRaises(InstallerError) as ctx:
                        self._call(**{k: v for k, v in overrides.items() if not k.startswith("is_")})
                    self.assertEqual(ctx.exception.reason, reason)
                finally:
                    for patch in patches:
                        patch.stop()

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


class TestKernelPartitions(unittest.TestCase):
    """分区列表只能信内核（sysfs），不能信 `lsblk`。

    实测过：`lsblk` 会把「盘上的分区表里写着、但内核没收下」的分区也列出来，
    照着它去 mkfs 只会得到一句 `No such file or directory`。
    """

    def _fake_sysfs(self, root: str, disk_name: str, parts: list[tuple[str, str, str]]) -> None:
        base = Path(root) / "block" / disk_name
        base.mkdir(parents=True)
        for name, dev, number in parts:
            child = base / name
            child.mkdir()
            (child / "dev").write_text(dev + "\n", encoding="utf-8")
            (child / "partition").write_text(number + "\n", encoding="utf-8")

    def test_reads_partitions_sorted_by_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 故意乱序写入，返回值必须按分区号排
            self._fake_sysfs(tmp, "vda", [("vda2", "254:2", "2"), ("vda1", "254:1", "1")])
            self.assertEqual(
                disk.kernel_partitions("/dev/vda", sysfs_root=tmp),
                [("/dev/vda1", 254, 1), ("/dev/vda2", 254, 2)],
            )

    def test_handles_nvme_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._fake_sysfs(tmp, "nvme0n1", [("nvme0n1p1", "259:1", "1"), ("nvme0n1p2", "259:2", "2")])
            self.assertEqual(
                [p for p, _, _ in disk.kernel_partitions("/dev/nvme0n1", sysfs_root=tmp)],
                ["/dev/nvme0n1p1", "/dev/nvme0n1p2"],
            )

    def test_ignores_the_disk_itself_and_junk(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "block" / "vda"
            base.mkdir(parents=True)
            (base / "vda").mkdir()                     # 整盘自己不是分区
            (base / "vda1").mkdir()
            (base / "vda1" / "dev").write_text("not-a-devnum\n", encoding="utf-8")
            (base / "vda1" / "partition").write_text("1\n", encoding="utf-8")
            self.assertEqual(disk.kernel_partitions("/dev/vda", sysfs_root=tmp), [])

    def test_missing_device_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(disk.kernel_partitions("/dev/nope", sysfs_root=tmp), [])


class TestStrayMountpoints(unittest.TestCase):
    """udisks2 会自动挂上新建的文件系统：挂载目标前必须先看见这些野挂载。"""

    MOUNTINFO = "\n".join([
        "25 1 8:2 / /mnt rw,relatime - ext4 /dev/sdb2 rw",
        "26 25 8:1 / /mnt/boot rw - vfat /dev/sdb1 rw",
        "30 1 8:2 / /run/media/neo/MIPLINUX ro - ext4 /dev/sdb2 ro",
        "31 1 8:1 / /run/media/neo/ESP ro - vfat /dev/sdb1 ro",
        "32 1 8:9 / /run/media/neo/other ro - ext4 /dev/sdc1 ro",
    ])

    def test_reports_every_mount_of_our_devices(self):
        strays = disk.stray_mountpoints(self.MOUNTINFO, ["/dev/sdb2", "/dev/sdb1"], set())
        self.assertEqual(sorted(strays), ["/mnt", "/mnt/boot",
                                          "/run/media/neo/ESP", "/run/media/neo/MIPLINUX"])

    def test_keep_hides_our_own_mounts(self):
        strays = disk.stray_mountpoints(self.MOUNTINFO, ["/dev/sdb2", "/dev/sdb1"],
                                        {"/mnt", "/mnt/boot"})
        self.assertEqual(sorted(strays), ["/run/media/neo/ESP", "/run/media/neo/MIPLINUX"])

    def test_other_devices_are_ignored(self):
        strays = disk.stray_mountpoints(self.MOUNTINFO, ["/dev/sdb2"], {"/mnt"})
        self.assertEqual(strays, ["/run/media/neo/MIPLINUX"])


if __name__ == "__main__":
    unittest.main()
