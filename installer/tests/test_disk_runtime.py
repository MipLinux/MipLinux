"""擦盘之后那段「等内核与 udev 跟上来」的行为。

这一组守的是一个**实测踩到的竞态**：Live 里第一次真跑时，分区表已经提交
（`lsblk -f` 能看到 vda1/vda2），但 `mkfs.vfat` 报
`unable to open /dev/vda1: No such file or directory` —— `lsblk` 读的是 sysfs，
看到名字不等于 `/dev` 里有节点。所以：命令顺序要被钉死，判据要落在
「节点真的存在」上。
"""

from __future__ import annotations

import unittest
from unittest import mock

from mipl_installer import disk
from mipl_installer.util import EXIT_CONFIGURE, EXIT_GUARD, InstallerError
from tests.support import FakeRunner

LAYOUT = disk.plan_layout(40 * disk.GiB)


def _index(commands: list[str], needle: str) -> int:
    for i, command in enumerate(commands):
        if needle in command:
            return i
    raise AssertionError(f"没有跑到含 {needle!r} 的命令：\n" + "\n".join(commands))


class TestWipeOrder(unittest.TestCase):
    """这条顺序是那次竞态的直接修复，别改回去。"""

    def setUp(self):
        self.runner = FakeRunner(outputs={"lsblk": "/dev/vda1 part\n/dev/vda2 part\n"})
        # 让「等节点」这一步马上失败，好观察命令顺序
        patch = mock.patch.object(disk, "WAIT_ATTEMPTS", 1)
        patch.start()
        self.addCleanup(patch.stop)
        patch2 = mock.patch.object(disk, "_parted_create")
        patch2.start()
        self.addCleanup(patch2.stop)

    def test_partprobe_then_trigger_then_settle(self):
        with self.assertRaises(InstallerError):
            disk.wipe_and_partition(self.runner, "/dev/vda", LAYOUT)
        commands = self.runner.commands()
        self.assertLess(_index(commands, "partprobe"), _index(commands, "udevadm trigger"))
        self.assertLess(_index(commands, "udevadm trigger"), _index(commands, "udevadm settle"))

    def test_wipefs_runs_on_device_and_old_partitions(self):
        self.runner.outputs["lsblk"] = "/dev/vda1 part\n/dev/vda disk\n/dev/vda2 part\n"
        with self.assertRaises(InstallerError):
            disk.wipe_and_partition(self.runner, "/dev/vda", LAYOUT)
        commands = self.runner.commands()
        self.assertIn("wipefs -a /dev/vda1", commands)
        self.assertIn("wipefs -a /dev/vda2", commands)
        self.assertIn("wipefs -a /dev/vda", commands)


class TestWaitForPartitionNodes(unittest.TestCase):
    def test_returns_when_both_nodes_exist(self):
        runner = FakeRunner(outputs={"lsblk": "/dev/vda1 part\n/dev/vda2 part\n"})
        with mock.patch("mipl_installer.disk.os.path.exists", return_value=True):
            self.assertEqual(disk.wait_for_partition_nodes(runner, "/dev/vda"), ("/dev/vda1", "/dev/vda2"))

    def test_keeps_waiting_while_nodes_are_missing(self):
        """sysfs 里有名字、/dev 里没节点 —— 就是那次失败的样子。"""
        runner = FakeRunner(outputs={"lsblk": "/dev/vda1 part\n/dev/vda2 part\n"})
        with mock.patch.object(disk, "WAIT_ATTEMPTS", 3), \
             mock.patch("mipl_installer.disk.os.path.exists", return_value=False), \
             self.assertRaises(InstallerError) as ctx:
            disk.wait_for_partition_nodes(runner, "/dev/vda")
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
        self.assertIn("设备节点", str(ctx.exception))
        self.assertEqual(len([c for c in runner.commands() if c.startswith("sleep")]), 2)  # 最后一次不再睡

    def test_reports_how_long_it_waited(self):
        runner = FakeRunner(outputs={"lsblk": "/dev/vda1 part\n/dev/vda2 part\n"})
        with mock.patch.object(disk, "WAIT_ATTEMPTS", 2), \
             mock.patch.object(disk, "WAIT_INTERVAL", "0.5"), \
             mock.patch("mipl_installer.disk.os.path.exists", return_value=False), \
             self.assertRaises(InstallerError) as ctx:
            disk.wait_for_partition_nodes(runner, "/dev/vda")
        self.assertIn("1 秒", str(ctx.exception))


class TestUuidGuard(unittest.TestCase):
    def test_returns_the_uuid(self):
        runner = FakeRunner(outputs={"blkid": "11111111-1111-1111-1111-111111111111\n"})
        self.assertEqual(disk.uuid_of(runner, "/dev/vda2"), "11111111-1111-1111-1111-111111111111")

    def test_empty_output_is_an_error_not_an_empty_uuid(self):
        """空串会被写成 `UUID=` —— 那种系统起不来，宁可在这里停下。"""
        runner = FakeRunner(outputs={"blkid": ""})
        with self.assertRaises(InstallerError) as ctx:
            disk.uuid_of(runner, "/dev/vda2")
        self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)

    def test_dry_run_returns_the_placeholder(self):
        from mipl_installer import util

        runner = FakeRunner()
        runner.dry_run = True
        runner.outputs["blkid"] = util.DRY
        self.assertEqual(disk.uuid_of(runner, "/dev/vda2"), util.DRY)


if __name__ == "__main__":
    unittest.main()
