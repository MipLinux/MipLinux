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

from mipl_installer import disk, util
from mipl_installer.util import EXIT_CONFIGURE, EXIT_GUARD, InstallerError
from tests.support import FakeRunner, RecordingReporter

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
        for helper in ("_prepare_partitioning", "_assert_not_busy", "_verify_partition_layout", "_node_matches"):
            patcher = mock.patch.object(disk, helper, return_value=True)
            patcher.start()
            self.addCleanup(patcher.stop)
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
    def setUp(self):
        patcher = mock.patch.object(disk, "_node_matches", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

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
        runner = FakeRunner(dry_run=True)
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
        disk.unmount_target(runner, util.DEFAULT_TARGET)          # 不该抛
        self.assertIn(f"umount -R {util.DEFAULT_TARGET}", runner.commands())

    def test_unmount_says_so_when_the_target_stays_mounted(self):
        """卸不掉必须留一句话。

        `check=False` 一路静默，于是「卸载目标」这句旁白可以与事实相反 —— 实测里
        正是这样：用户只看到下一次开工装不了，没有任何解释（#105）。
        """
        runner = FakeRunner(reporter=RecordingReporter())
        with mock.patch("mipl_installer.disk.is_mountpoint", return_value=True):
            disk.unmount_target(runner, util.DEFAULT_TARGET)
        self.assertTrue(any("卸载没成功" in note for note in runner.reporter.notes),
                        runner.reporter.notes)

    def test_unmount_stays_quiet_when_it_worked(self):
        runner = FakeRunner(reporter=RecordingReporter())
        with mock.patch("mipl_installer.disk.is_mountpoint", return_value=False):
            disk.unmount_target(runner, util.DEFAULT_TARGET)
        self.assertFalse(any("卸载没成功" in note for note in runner.reporter.notes))

    def test_settle_udev_triggers_then_settles(self):
        runner = FakeRunner()
        disk.settle_udev(runner)
        self.assertEqual(runner.commands(), [
            "udevadm trigger --subsystem-match=block",
            "udevadm settle",
        ])


class TestCleanupStaleTarget(unittest.TestCase):
    """开工前清掉**我们自己**上一次留下的挂载（#105）。

    目标挂载点是专用子目录，所以归属是路径事实：`/mnt/mipl` 下面的一定是我们的，
    用户的盘挂在 `/mnt`、`/run/media/...` 都碰不到。
    """

    STALE = "\n".join([
        "40 30 8:2 / /mnt rw,relatime - ext4 /dev/vdb1 rw",
        "41 30 8:3 / /mnt/mipl rw,relatime - ext4 /dev/vdc1 rw",
        "42 30 8:4 / /mnt/mipl/boot rw,relatime - vfat /dev/vdc2 rw",
        "43 30 0:24 / /mnt/mipl/proc rw - proc proc rw",
    ])

    def test_unmounts_our_namespace_and_leaves_the_users_mount_alone(self):
        runner = FakeRunner()
        with mock.patch("mipl_installer.util.read_text", side_effect=[self.STALE, self.STALE, "", "", ""]):
            points = disk.cleanup_stale_target(runner, util.DEFAULT_TARGET)
        self.assertEqual(points, [util.DEFAULT_TARGET, f"{util.DEFAULT_TARGET}/boot",
                                  f"{util.DEFAULT_TARGET}/proc"])
        self.assertIn(f"umount -R {util.DEFAULT_TARGET}", runner.commands())
        # 用户挂在自己 /mnt 上的那块盘：一条命令都不许碰它
        self.assertNotIn("umount -R /mnt", runner.commands())
        self.assertNotIn("umount /mnt", runner.commands())

    def test_no_stale_mounts_means_no_commands(self):
        runner = FakeRunner()
        with mock.patch("mipl_installer.util.read_text", return_value=""):
            self.assertEqual(disk.cleanup_stale_target(runner, util.DEFAULT_TARGET), [])
        self.assertEqual(runner.commands(), [])

    def test_dry_run_touches_nothing(self):
        runner = FakeRunner(dry_run=True)
        self.assertEqual(disk.cleanup_stale_target(runner, util.DEFAULT_TARGET), [])
        self.assertEqual(runner.commands(), [])


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


class TestDiskSafetyRegressions(unittest.TestCase):
    def test_unmount_read_failures_do_not_escape_cleanup(self):
        for failure_on_read in (0, 1, 2):
            runner = FakeRunner(reporter=RecordingReporter())
            reads = ["1 0 8:2 / /mnt/mipl rw - ext4 /dev/vda2 rw\n", "", ""]
            reads[failure_on_read] = OSError("synthetic read failure")
            with self.subTest(failure_on_read=failure_on_read), mock.patch.object(
                util, "read_text", side_effect=reads
            ), mock.patch.object(disk.os.path, "ismount", return_value=False):
                disk.unmount_target(runner)
            self.assertTrue(any("无法确认卸载状态" in note for note in runner.reporter.notes))

    def test_busy_root_blocks_formatting_before_esp_is_modified(self):
        import stat
        from types import SimpleNamespace
        runner = FakeRunner()
        with mock.patch.object(disk, "_assert_not_busy", side_effect=[None, InstallerError("busy", EXIT_GUARD)]), \
             mock.patch.object(disk.os, "stat", return_value=SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=1)), \
             mock.patch.object(util, "is_partition", return_value=True):
            with self.assertRaises(InstallerError):
                disk.make_filesystems(runner, "/dev/FAKE1", "/dev/FAKE2")
        self.assertEqual(runner.history, [])

    def test_changed_root_identity_blocks_second_format(self):
        import stat
        from types import SimpleNamespace
        def node(number):
            return SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=number)
        runner = FakeRunner()
        with mock.patch.object(disk, "_assert_not_busy"), \
             mock.patch.object(disk.os, "stat", side_effect=[node(1), node(2), node(1), node(3)]), \
             mock.patch.object(util, "is_partition", return_value=True):
            with self.assertRaises(InstallerError):
                disk.make_filesystems(runner, "/dev/FAKE1", "/dev/FAKE2")
        self.assertEqual(len(runner.find("mkfs.vfat")), 1)
        self.assertFalse(runner.find("mkfs.ext4"))

    def test_formatting_checks_both_partitions_and_rechecks_before_each_write(self):
        import stat
        from types import SimpleNamespace
        nodes = [SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=n) for n in (1, 2, 1, 2)]
        runner = FakeRunner()
        with mock.patch.object(disk, "_assert_not_busy") as guard, \
             mock.patch.object(disk.os, "stat", side_effect=nodes), \
             mock.patch.object(util, "is_partition", return_value=True):
            disk.make_filesystems(runner, "/dev/FAKE1", "/dev/FAKE2")
        self.assertEqual(guard.call_args_list, [mock.call(p) for p in
                         ("/dev/FAKE1", "/dev/FAKE2", "/dev/FAKE1", "/dev/FAKE2")])
        self.assertEqual(len(runner.find("mkfs")), 2)

    def test_same_device_or_nonpartition_is_rejected_before_formatting(self):
        import stat
        from types import SimpleNamespace
        for partition in (True, False):
            runner = FakeRunner()
            with self.subTest(partition=partition), mock.patch.object(disk, "_assert_not_busy"), \
                 mock.patch.object(disk.os, "stat", return_value=SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=1)), \
                 mock.patch.object(util, "is_partition", return_value=partition):
                with self.assertRaises(InstallerError):
                    disk.make_filesystems(runner, "/dev/FAKE1", "/dev/FAKE2")
            self.assertEqual(runner.history, [])

    def test_dependency_failure_precedes_all_disk_commands(self):
        runner = FakeRunner()
        with mock.patch.object(disk, '_prepare_partitioning', side_effect=InstallerError('missing parted', 2)):
            with self.assertRaises(InstallerError):
                disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
        self.assertEqual(runner.history, [])

    def test_new_mount_before_wipe_is_rejected(self):
        runner = FakeRunner()
        with mock.patch.object(disk.util, 'is_block_device', return_value=True), mock.patch.object(disk, '_prepare_partitioning'), mock.patch.object(
            disk.util, 'read_text', side_effect=lambda path: (
                '31 1 254:2 / /media/data rw - ext4 /dev/vda2 rw' if path.endswith('mountinfo')
                else 'Filename Type Size Used Priority\n'
            )
        ):
            with self.assertRaises(InstallerError) as ctx:
                disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
        self.assertEqual(ctx.exception.reason, 'diskInUse')
        self.assertEqual(runner.history, [])

    def test_active_swap_blocks_an_unmounted_disk(self):
        with mock.patch.object(disk.util, 'read_text', return_value=(
            'Filename Type Size Used Priority\n/dev/vda2 partition 1024 0 -2\n'
        )):
            self.assertEqual(disk._busy_sources('/dev/vda', set()), {'/dev/vda2'})

    def test_unreadable_swap_state_fails_closed(self):
        with mock.patch.object(disk.util, 'read_text', side_effect=OSError('unreadable')):
            with self.assertRaises(InstallerError):
                disk._busy_sources('/dev/vda', set())

    def test_nvme_and_mmc_dry_run_paths(self):
        for device, expected in (('/dev/vda', ('/dev/vda1', '/dev/vda2')),
                                 ('/dev/nvme0n1', ('/dev/nvme0n1p1', '/dev/nvme0n1p2')),
                                 ('/dev/mmcblk0', ('/dev/mmcblk0p1', '/dev/mmcblk0p2'))):
            runner = FakeRunner(dry_run=True)
            with self.subTest(device=device), mock.patch.object(disk, 'kernel_partitions', return_value=[]), mock.patch.object(
                disk, '_prepare_partitioning', side_effect=AssertionError('must not probe')
            ):
                self.assertEqual(disk.wipe_and_partition(runner, device, LAYOUT), expected)

    def test_wrong_partition_set_is_rejected(self):
        for parts in ([FAKE_PARTS[0], ('/dev/vda3', 254, 3)], FAKE_PARTS + [('/dev/vda3', 254, 3)]):
            with self.subTest(parts=parts), mock.patch.object(disk, 'kernel_partitions', return_value=parts), mock.patch.object(
                disk, 'WAIT_ATTEMPTS', 1
            ), mock.patch.object(disk, '_node_matches', return_value=True):
                with self.assertRaises(InstallerError):
                    disk.wait_for_partition_nodes(FakeRunner(), '/dev/vda')

    def test_wrong_device_node_is_rejected(self):
        with mock.patch.object(disk, 'kernel_partitions', return_value=FAKE_PARTS), mock.patch.object(
            disk, 'WAIT_ATTEMPTS', 1
        ), mock.patch.object(disk.os.path, 'exists', return_value=True), mock.patch.object(disk, '_node_matches', return_value=False):
            with self.assertRaises(InstallerError):
                disk.wait_for_partition_nodes(FakeRunner(), '/dev/vda')

    def test_regular_file_is_not_a_partition_node(self):
        with tempfile.NamedTemporaryFile() as file:
            self.assertFalse(disk._node_matches(file.name, 254, 1))

    def test_partprobe_failure_does_not_reach_formatting_or_wait(self):
        runner = FakeRunner()
        runner.fail_patterns.add('partprobe')
        with mock.patch.object(disk, '_prepare_partitioning'), mock.patch.object(disk, '_assert_not_busy'), mock.patch.object(
            disk, 'kernel_partitions', return_value=[]
        ), mock.patch.object(disk, '_parted_create'), mock.patch.object(disk, 'wait_for_partition_nodes') as wait:
            with self.assertRaises(InstallerError):
                disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
        wait.assert_not_called()

    def test_residual_child_mount_is_reported_and_not_returned_as_removed(self):
        table = '31 1 254:1 / /mnt/mipl/boot rw - vfat /dev/vda1 rw'
        reporter = RecordingReporter()
        runner = FakeRunner(reporter=reporter)
        runner.fail_patterns.add('umount')
        with mock.patch.object(disk.util, 'read_text', return_value=table), mock.patch.object(disk.os.path, 'ismount', return_value=False):
            self.assertEqual(disk.cleanup_stale_target(runner), [])
            self.assertTrue(disk.is_mountpoint('/mnt/mipl'))
        self.assertTrue(any('卸载没成功' in note for note in reporter.notes))

    def test_successful_recursive_unmount_does_not_repeat_commands(self):
        runner = FakeRunner()
        with mock.patch.object(disk.util, 'read_text', return_value=''), mock.patch.object(disk.os.path, 'ismount', return_value=False):
            disk.unmount_target(runner)
        self.assertEqual(runner.commands(), ['umount -R /mnt/mipl'])

    def test_escaped_automount_path_is_decoded_before_unmount(self):
        runner = FakeRunner()
        table = r'31 1 254:2 / /run/media/My\040Disk rw - ext4 /dev/vda2 rw'
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(disk.util, 'read_text', return_value=table):
            disk.mount_target(runner, '/dev/vda2', '/dev/vda1', tmp)
        self.assertEqual(runner.history[0], ['umount', '/run/media/My Disk'])


class TestDeviceTopology(unittest.TestCase):
    def test_mapping_dependencies_include_underlying_partition_and_disk(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            block = Path(tmp) / 'class/block'
            physical = block / 'nvme0n1'
            partition = physical / 'nvme0n1p2'
            partition.mkdir(parents=True)
            (partition / 'partition').write_text('2')
            for name in ('dm-0', 'dm-1'):
                (block / name / 'slaves').mkdir(parents=True)
            (block / 'dm-0/slaves/nvme0n1p2').symlink_to(partition)
            (block / 'dm-1/slaves/dm-0').symlink_to(block / 'dm-0')
            ancestors = disk._block_ancestors('/dev/dm-1', sysfs_root=tmp)
            self.assertEqual(ancestors, {'dm-1', 'dm-0', 'nvme0n1p2', 'nvme0n1'})
            with mock.patch.object(disk, '_block_ancestors', return_value=ancestors):
                self.assertTrue(disk.same_device('/dev/dm-1', '/dev/nvme0n1'))
                self.assertTrue(disk.same_device('/dev/dm-1', '/dev/nvme0n1p2'))
                self.assertFalse(disk.same_device('/dev/dm-1', '/dev/nvme0n1p1'))

    def test_alias_and_canonical_device_match(self):
        original = disk.os.path.realpath
        def realpath(path, **kwargs):
            return '/dev/nvme0n1' if str(path) == '/dev/disk/by-id/test' else original(path, **kwargs)
        with mock.patch.object(disk.os.path, 'realpath', side_effect=realpath):
            self.assertTrue(disk.same_device('/dev/nvme0n1p2', '/dev/disk/by-id/test'))
            self.assertFalse(disk.same_device('/dev/nvme0n11p2', '/dev/disk/by-id/test'))

    def test_holder_on_an_unmounted_partition_blocks_disk(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'vda/vda2/holders/dm-0').mkdir(parents=True)
            (root / 'vda/vda2/partition').write_text('2')
            real_path = Path
            def path(value):
                return root if value == '/sys/class/block' else real_path(value)
            with mock.patch.object(disk, 'Path', side_effect=path), mock.patch.object(
                disk.util, 'read_text', return_value='Filename Type Size Used Priority\n'
            ):
                self.assertEqual(disk._busy_sources('/dev/vda', set()), {'/dev/dm-0'})


class TestPartitionPreflight(unittest.TestCase):
    def _parted(self):
        from types import SimpleNamespace
        dev = SimpleNamespace(sectorSize=512, optimalAlignedConstraint=object(), clobber=mock.Mock())
        table = mock.Mock()
        def geometry(**kwargs):
            return SimpleNamespace(start=kwargs['start'], length=kwargs['length'])
        def partition(**kwargs):
            return SimpleNamespace(geometry=kwargs['geometry'], setFlag=mock.Mock())
        module = SimpleNamespace(getDevice=mock.Mock(return_value=dev),
                                 freshDisk=mock.Mock(return_value=table),
                                 Geometry=geometry, FileSystem=mock.Mock(), Partition=partition,
                                 PARTITION_NORMAL=0, PARTITION_ESP=18)
        return module, dev, table

    def test_missing_module_or_esp_support_never_wipes(self):
        import sys
        module, dev, table = self._parted()
        del module.PARTITION_ESP
        for value in (None, module):
            runner = FakeRunner()
            with self.subTest(module=value), mock.patch.dict(sys.modules, {'parted': value}):
                with self.assertRaises(InstallerError):
                    disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
            self.assertEqual(runner.history, [])
        dev.clobber.assert_not_called()
        table.commit.assert_not_called()

    def test_geometry_failure_is_detected_without_writes(self):
        import sys
        module, dev, table = self._parted()
        table.addPartition.side_effect = ValueError('alignment impossible')
        with mock.patch.dict(sys.modules, {'parted': module}):
            with self.assertRaises(InstallerError):
                disk._prepare_partitioning('/dev/vda', LAYOUT)
        dev.clobber.assert_not_called()
        table.commit.assert_not_called()

    def test_prepared_table_is_reused_for_commit(self):
        import sys
        module, dev, table = self._parted()
        with mock.patch.dict(sys.modules, {'parted': module}):
            prepared = disk._prepare_partitioning('/dev/vda', LAYOUT)
            dev.clobber.assert_not_called()
            table.commit.assert_not_called()
            disk._parted_create('/dev/vda', LAYOUT, prepared=prepared)
        self.assertEqual(module.freshDisk.call_count, 1)
        dev.clobber.assert_called_once()
        table.commit.assert_called_once()

    def test_wrong_kernel_geometry_is_rejected(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for number, start, size in ((1, LAYOUT.esp_start, LAYOUT.esp_size),
                                       (2, LAYOUT.root_start, LAYOUT.root_size)):
                node = root / 'vda' / f'vda{number}'
                node.mkdir(parents=True)
                (node / 'start').write_text(str(start // 512))
                (node / 'size').write_text(str(size // 512))
            def path(value):
                return root if value == '/sys/class/block' else Path(value)
            with mock.patch.object(disk, 'Path', side_effect=path):
                disk._verify_partition_layout('/dev/vda', LAYOUT)
                (root / 'vda/vda2/start').write_text('2048')
                with self.assertRaises(InstallerError):
                    disk._verify_partition_layout('/dev/vda', LAYOUT)


class TestLastMomentGuards(unittest.TestCase):
    def test_mount_appearing_during_udev_settle_blocks_first_wipe(self):
        runner = FakeRunner()
        with mock.patch.object(disk, '_prepare_partitioning'), mock.patch.object(
            disk, '_assert_not_busy', side_effect=[None, InstallerError('new mount', EXIT_GUARD)]
        ), mock.patch.object(disk, '_parted_create') as create:
            with self.assertRaises(InstallerError):
                disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
        self.assertIn('udevadm settle', runner.commands())
        self.assertFalse(any(argv[0] == 'wipefs' for argv in runner.history))
        create.assert_not_called()

    def test_new_use_between_partition_wipes_stops_remaining_writes(self):
        runner = FakeRunner()
        with mock.patch.object(disk, '_prepare_partitioning'), mock.patch.object(
            disk, '_assert_not_busy', side_effect=[None, None, None, InstallerError('new swap', EXIT_GUARD)]
        ), mock.patch.object(disk, 'kernel_partitions', return_value=FAKE_PARTS), mock.patch.object(
            disk.os.path, 'exists', return_value=True
        ):
            with self.assertRaises(InstallerError):
                disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
        self.assertEqual([argv for argv in runner.history if argv[0] == 'wipefs'],
                         [['wipefs', '-a', '/dev/vda1']])

    def test_missing_external_tool_blocks_even_direct_call(self):
        for command in ('wipefs', 'partprobe', 'mkfs.vfat', 'mkfs.ext4'):
            runner = FakeRunner()
            def require(programs):
                self.assertIn(command, programs)
                raise InstallerError('missing ' + command, 2)
            with self.subTest(command=command), mock.patch.object(runner, 'require', side_effect=require), mock.patch.object(
                disk, '_prepare_partitioning'
            ) as prepare:
                with self.assertRaises(InstallerError):
                    disk.wipe_and_partition(runner, '/dev/vda', LAYOUT)
            prepare.assert_not_called()
            self.assertEqual(runner.history, [])

    def test_real_block_device_with_missing_sysfs_is_rejected(self):
        from types import SimpleNamespace
        import stat
        original = disk.os.stat
        def device_stat(path, *args, **kwargs):
            if str(path) == '/dev/issue152-no-sysfs':
                return SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=0)
            return original(path, *args, **kwargs)
        with mock.patch.object(disk.os, 'stat', side_effect=device_stat), mock.patch.object(
            disk.util, 'read_text', return_value='Filename Type Size Used Priority\n'
        ):
            with self.assertRaises(InstallerError) as ctx:
                disk._busy_sources('/dev/issue152-no-sysfs', set())
        self.assertEqual(ctx.exception.exit_code, EXIT_GUARD)


if __name__ == "__main__":
    unittest.main()
