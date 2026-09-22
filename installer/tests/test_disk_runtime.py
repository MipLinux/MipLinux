"""擦盘之后那段「等内核与 udev 跟上来」的行为。

这一组守的是一个**实测踩到的竞态**：Live 里第一次真跑时，分区表已经提交
（`lsblk -f` 能看到 vda1/vda2），但 `mkfs.vfat` 报
`unable to open /dev/vda1: No such file or directory` —— `lsblk` 读的是 sysfs，
看到名字不等于 `/dev` 里有节点。所以：命令顺序要被钉死，判据要落在
「节点真的存在」上。
"""

from __future__ import annotations

import tempfile
import unittest
from unittest import mock

from mipl_installer import disk
from mipl_installer.util import EXIT_CONFIGURE, EXIT_GUARD, InstallerError
from tests.support import FakeRunner

LAYOUT = disk.plan_layout(40 * disk.GiB)
#: 内核收下的两个分区（测试里不去读真的 sysfs）
FAKE_PARTS = [("/dev/vda1", 254, 1), ("/dev/vda2", 254, 2)]


def _index(commands: list[str], needle: str) -> int:
    for i, command in enumerate(commands):
        if needle in command:
            return i
    raise AssertionError(f"没有跑到含 {needle!r} 的命令：\n" + "\n".join(commands))


class TestWipeOrder(unittest.TestCase):
    """命令顺序是两次实测失败的直接修复，别改回去：

    1. **先追平 udev**，再碰任何设备节点 —— 否则 `wipefs` 会报
       `probing initialization failed: No such file or directory`（libblkid 探不到设备）。
    2. 分区表提交后 `partprobe` → 再 settle → 再等节点出现。
    """

    def setUp(self):
        self.runner = FakeRunner()
        # 让「等节点」这一步马上失败，好观察命令顺序
        patch = mock.patch.object(disk, "WAIT_ATTEMPTS", 1)
        patch.start()
        self.addCleanup(patch.stop)
        patch2 = mock.patch.object(disk, "_parted_create")
        patch2.start()
        self.addCleanup(patch2.stop)

    def _run(self, *, nodes_exist: bool) -> list[str]:
        """跑一遍并返回命令序列。`nodes_exist=False` 时会在「等节点」那步超时。"""
        with mock.patch("mipl_installer.disk.kernel_partitions", return_value=FAKE_PARTS), \
             mock.patch("mipl_installer.disk.os.path.exists", return_value=nodes_exist):
            try:
                disk.wipe_and_partition(self.runner, "/dev/vda", LAYOUT)
            except InstallerError:
                pass
        return self.runner.commands()

    def test_udev_is_settled_before_touching_any_node(self):
        commands = self._run(nodes_exist=True)
        trigger = _index(commands, "udevadm trigger")
        settle = _index(commands, "udevadm settle")
        first_wipe = _index(commands, "wipefs")
        self.assertLess(trigger, settle)
        self.assertLess(settle, first_wipe)

    def test_partprobe_then_settle_after_partitioning(self):
        commands = self._run(nodes_exist=True)
        partprobe = _index(commands, "partprobe")
        settle = commands.index("udevadm settle", partprobe)
        self.assertLess(partprobe, settle)

    def test_wipes_the_device_itself(self):
        self.assertIn("wipefs -a /dev/vda", self._run(nodes_exist=True))

    def test_skips_partitions_without_device_nodes(self):
        """sysfs 里有名字、/dev 里没节点时，别对着不存在的路径 wipefs（那是整轮白跑）。"""
        commands = self._run(nodes_exist=False)
        self.assertNotIn("wipefs -a /dev/vda1", commands)
        self.assertIn("wipefs -a /dev/vda", commands)

    def test_wipes_partitions_when_their_nodes_exist(self):
        commands = self._run(nodes_exist=True)
        self.assertIn("wipefs -a /dev/vda1", commands)
        self.assertIn("wipefs -a /dev/vda2", commands)


class TestWaitForPartitionNodes(unittest.TestCase):
    def test_returns_when_the_kernel_has_both_and_nodes_exist(self):
        runner = FakeRunner()
        with mock.patch("mipl_installer.disk.kernel_partitions", return_value=FAKE_PARTS), \
             mock.patch("mipl_installer.disk.os.path.exists", return_value=True):
            self.assertEqual(disk.wait_for_partition_nodes(runner, "/dev/vda"), ("/dev/vda1", "/dev/vda2"))

    def test_creates_the_node_when_the_kernel_has_it_but_dev_does_not(self):
        """内核收下了、`/dev` 里没有 —— 自己 `mknod` 补，别等下去。"""
        runner = FakeRunner()
        probes = {"n": 0}

        def exists(path):
            # 第一轮的两下探测说「不在」，补完节点之后就都在了
            probes["n"] += 1
            return probes["n"] > 2

        with mock.patch("mipl_installer.disk.kernel_partitions", return_value=FAKE_PARTS), \
             mock.patch("mipl_installer.disk.os.path.exists", side_effect=exists), \
             mock.patch.object(disk, "WAIT_ATTEMPTS", 3):
            self.assertEqual(disk.wait_for_partition_nodes(runner, "/dev/vda"), ("/dev/vda1", "/dev/vda2"))
        commands = runner.commands()
        self.assertIn("mknod /dev/vda1 b 254 1", commands)
        self.assertIn("chown root:disk /dev/vda1", commands)

    def test_reports_the_kernels_view_when_the_last_partition_is_missing(self):
        """**回归测试**：root 压到 GPT 备份表头时，内核只收下第一个分区。

        这时报错必须说「内核只收下了 1 个」—— 而不是含糊的「等了 N 秒」，
        更不能让人以为是 udev 的问题。
        """
        runner = FakeRunner()
        with mock.patch("mipl_installer.disk.kernel_partitions",
                        return_value=[("/dev/vda1", 254, 1)]), \
             mock.patch("mipl_installer.disk.os.path.exists", return_value=True), \
             mock.patch.object(disk, "WAIT_ATTEMPTS", 2), \
             self.assertRaises(InstallerError) as ctx:
            disk.wait_for_partition_nodes(runner, "/dev/vda")
        message = ctx.exception.render()          # render() 里带 hint
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)
        self.assertIn("只收下了 1 个分区", message)
        self.assertIn("GPT 备份表头", message)

    def test_keeps_quiet_when_there_is_nothing_to_wait_for(self):
        """一次次 sleep 是有的，但次数要跟着 WAIT_ATTEMPTS 走（最后一次不睡）。"""
        runner = FakeRunner()
        with mock.patch("mipl_installer.disk.kernel_partitions", return_value=[]), \
             mock.patch.object(disk, "WAIT_ATTEMPTS", 3):
            with self.assertRaises(InstallerError):
                disk.wait_for_partition_nodes(runner, "/dev/vda")
        self.assertEqual(len([c for c in runner.commands() if c.startswith("sleep")]), 2)


class TestFilesystemAndMount(unittest.TestCase):
    def test_make_filesystems_labels_both(self):
        runner = FakeRunner()
        disk.make_filesystems(runner, "/dev/vda1", "/dev/vda2")
        self.assertEqual(runner.commands(), [
            "mkfs.vfat -F 32 -n MIPLINUX /dev/vda1",
            "mkfs.ext4 -F -L MIPLINUX /dev/vda2",
        ])

    def test_mount_order_root_then_esp_on_boot(self):
        """ESP 必须挂到 target/boot（systemd-boot 只认 FAT，内核得落在 ESP 上）。"""
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            disk.mount_target(runner, "/dev/vda2", "/dev/vda1", tmp)
        commands = runner.commands()
        self.assertEqual(commands, [f"mount /dev/vda2 {tmp}", f"mount /dev/vda1 {tmp}/boot"])

    def test_unmount_never_raises(self):
        """收尾阶段再抛异常，只会盖掉真正的失败原因。"""
        runner = FakeRunner()
        runner.fail_patterns.add("umount")
        disk.unmount_target(runner, "/mnt")          # 不该抛
        self.assertIn("umount -R /mnt", runner.commands())

    def test_settle_udev_triggers_then_settles(self):
        runner = FakeRunner()
        disk.settle_udev(runner)
        self.assertEqual(runner.commands(), [
            "udevadm trigger --subsystem-match=block",
            "udevadm settle",
        ])


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
