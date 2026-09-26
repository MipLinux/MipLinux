"""安装编排：阶段顺序、守卫注入、失败与取消的收尾。

这一组钉的是「守卫不许被减少」：`confirm` 是**必填**参数，注入方省不掉；
取消与失败走同一条卸载收尾，不许在残骸上接着装。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mipl_installer import disk, events, options, packages, pipeline
from mipl_installer.util import EXIT_CONFIGURE, EXIT_USAGE, InstallerError
from tests.support import FakeRunner, RecordingReporter


class TestPlan(unittest.TestCase):
    def _plan(self, **overrides) -> pipeline.Plan:
        params = dict(
            disk="/dev/vda", target="/target", hostname="host", user="who",
            locale="en_US.UTF-8", timezone="Asia/Shanghai", keymap="de",
            pacman_conf="/tmp/pacman.conf", mirrorlist="/tmp/mirrorlist",
            fonts_conf="/tmp/fonts.conf",
        )
        params.update(overrides)
        return pipeline.Plan(**params)

    def test_config_maps_every_field(self):
        """`config()` 是前后端之间唯一的翻译点 —— 漏一个字段，界面上那一页就是摆设。"""
        cfg = self._plan().config()
        self.assertEqual(
            (cfg.target, cfg.hostname, cfg.user, cfg.locale, cfg.timezone,
             cfg.pacman_conf, cfg.mirrorlist, cfg.fonts_conf),
            ("/target", "host", "who", "en_US.UTF-8", "Asia/Shanghai",
             "/tmp/pacman.conf", "/tmp/mirrorlist", "/tmp/fonts.conf"),
        )
        # 键盘映射以前写死 us，键盘页因此是个摆设（Issue #64）—— 这个字段必须真的落地
        self.assertEqual(cfg.keymap, "de")

    def test_packages_path_falls_back_to_the_shipped_list(self):
        self.assertEqual(self._plan(packages_file=None).packages_path(),
                         packages.default_packages_file())

    def test_packages_path_uses_the_explicit_value(self):
        self.assertEqual(self._plan(packages_file="/tmp/pkgs").packages_path(), "/tmp/pkgs")


class TestParseSteps(unittest.TestCase):
    def test_all_by_default(self):
        self.assertEqual(pipeline.parse_steps(",".join(pipeline.STEP_ORDER)), pipeline.STEP_ORDER)

    def test_returns_dependency_order_not_typing_order(self):
        self.assertEqual(pipeline.parse_steps("boot,disk"), ("disk", "boot"))

    def test_rejects_unknown_step(self):
        with self.assertRaises(InstallerError) as ctx:
            pipeline.parse_steps("disk,teapot")
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_rejects_empty(self):
        with self.assertRaises(InstallerError):
            pipeline.parse_steps(",,")


class _RunCase(unittest.TestCase):
    """把四个阶段全换成替身：这一组验的是循环与收尾，不是阶段内部。"""

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = FakeRunner(reporter=self.reporter)
        patches = [
            mock.patch("mipl_installer.pipeline.Runner", return_value=self.runner),
            mock.patch("mipl_installer.util.require_root"),
            mock.patch("mipl_installer.util.is_block_device", return_value=True),
            mock.patch("mipl_installer.util.is_partition", return_value=False),
            mock.patch("mipl_installer.util.size_of_device", return_value=40 * disk.GiB),
            mock.patch("mipl_installer.util.read_text", return_value=""),
            mock.patch("mipl_installer.disk.is_mountpoint", return_value=False),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

        self.steps = {}
        for name in ("step_disk", "step_packages", "step_configure", "step_boot"):
            patch = mock.patch.object(pipeline, name)
            self.steps[name] = patch.start()
            self.addCleanup(patch.stop)

    def plan(self, **overrides) -> pipeline.Plan:
        params = dict(disk="/dev/vda")
        params.update(overrides)
        return pipeline.Plan(**params)

    def phases(self) -> list[str]:
        return [event.phase for event in self.reporter.events]


class TestRunPhases(_RunCase):
    def test_start_then_steps_then_done_in_order(self):
        pipeline.run(self.plan(), self.reporter, password="pw", confirm=lambda *a: None)
        self.assertEqual(self.phases(), ["start", *pipeline.STEP_ORDER, "done"])

    def test_every_emitted_phase_is_a_member_of_events_phases(self):
        """`events.PHASES` 是稳定接口：一个拼错的阶段名会让前端静默地什么都不显示。"""
        pipeline.run(self.plan(), self.reporter, password="pw", confirm=lambda *a: None)
        for phase in {event.phase for event in self.reporter.events}:
            self.assertIn(phase, events.PHASES)

    def test_only_the_requested_steps_run(self):
        pipeline.run(self.plan(steps=("disk", "boot")), self.reporter,
                     password="pw", confirm=lambda *a: None)
        self.assertEqual(self.phases(), ["start", "disk", "boot", "done"])
        self.steps["step_packages"].assert_not_called()
        self.steps["step_configure"].assert_not_called()


class TestConfirmIsMandatory(_RunCase):
    def test_run_without_a_confirm_hook_is_a_type_error(self):
        with self.assertRaises(TypeError):
            pipeline.run(self.plan(), self.reporter, password="pw")

    def test_confirm_runs_before_any_command(self):
        """守卫必须发生在**第一条命令之前** —— 顺序反了，守卫就只是事后通知。"""
        seen: dict = {}

        def confirm(plan, layout, reporter):
            seen["history"] = len(self.runner.history)
            seen["layout"] = layout

        pipeline.run(self.plan(), self.reporter, password="pw", confirm=confirm)
        self.assertEqual(seen["history"], 0)
        self.assertIsInstance(seen["layout"], disk.Layout)


class TestPreflight(_RunCase):
    """参数守卫必须在**动盘之前**跑完。

    这几条校验原先只在 `configure` 阶段（落盘前）跑 —— 那时盘已经擦干净、包也
    装了一半，用户停在一个「系统装了一半」的现场，起因只是一个打错的时区名。
    """

    def test_bad_parameter_fails_before_confirm_and_before_any_command(self):
        confirmed = []
        with self.assertRaises(InstallerError) as ctx:
            pipeline.run(
                self.plan(timezone="Nowhere/Nowhere"),
                self.reporter,
                password="pw",
                confirm=lambda *args: confirmed.append(args),
            )
        self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
        self.assertEqual(confirmed, [], "守卫已经失败了，不该再问「确认擦盘」")
        self.assertEqual(self.runner.history, [], "一条命令都不该跑")
        self.assertEqual(self.phases(), [], "连 `start` 都不该发 —— 失败在任何阶段之前")

    def test_is_pure_for_a_valid_plan(self):
        pipeline.preflight(self.plan())
        self.assertEqual(self.runner.history, [])

    def test_rejects_bad_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 键盘名单拿假根固定下来：真机上 /usr/share/kbd 缺失时校验会**跳过**
            # （那是有意的，见 options.validate_keymap），拿它当断言就不稳了
            Path(tmp, "us.map.gz").write_text("", encoding="utf-8")
            with mock.patch.object(options, "KEYMAP_ROOT", tmp):
                for overrides in (
                    {"user": "Mipl!"},
                    {"hostname": "-x"},
                    {"hostname": "a" * 64},
                    {"keymap": "no-such-keymap"},
                ):
                    with self.subTest(overrides=overrides):
                        with self.assertRaises(InstallerError):
                            pipeline.preflight(self.plan(**overrides))


class TestConfirmBlocksDiskCommands(unittest.TestCase):
    """不 mock `step_disk`：让真的擦盘流程摆在那里，证明守卫真的挡得住。"""

    def setUp(self):
        self.reporter = RecordingReporter()
        self.runner = FakeRunner(reporter=self.reporter)
        # 替身不会从 `Runner(reporter, dry_run=...)` 继承参数，得自己对齐 ——
        # 不对齐的话擦盘流程会走到真的 pyparted 那里去
        self.runner.dry_run = True
        patches = [
            mock.patch("mipl_installer.pipeline.Runner", return_value=self.runner),
            mock.patch("mipl_installer.util.require_root"),
            mock.patch("mipl_installer.util.is_block_device", return_value=True),
            mock.patch("mipl_installer.util.is_partition", return_value=False),
            mock.patch("mipl_installer.util.size_of_device", return_value=40 * disk.GiB),
            mock.patch("mipl_installer.util.read_text", return_value=""),
            mock.patch("mipl_installer.disk.is_mountpoint", return_value=False),
            mock.patch("mipl_installer.disk.kernel_partitions", return_value=[]),
            mock.patch("mipl_installer.disk.uuid_of", return_value="UUID"),
            mock.patch.object(pipeline, "step_packages"),
            mock.patch.object(pipeline, "step_configure"),
            mock.patch.object(pipeline, "step_boot"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _run(self, confirm) -> None:
        plan = pipeline.Plan(disk="/dev/vda", steps=("disk",))
        pipeline.run(plan, self.reporter, password="pw", dry_run=True, confirm=confirm)

    def test_a_raising_hook_prevents_every_wipefs_command(self):
        def refuse(*_args):
            raise InstallerError("用户没确认", EXIT_USAGE)

        with self.assertRaises(InstallerError):
            self._run(refuse)
        self.assertFalse(any("wipefs" in c for c in self.runner.commands()))

    def test_the_same_run_without_the_block_does_wipe(self):
        # 反证：上一条不是因为「流程本来就不擦盘」才通过的
        self._run(lambda *a: None)
        self.assertTrue(any("wipefs -a /dev/vda" == c for c in self.runner.commands()))


class TestRunFailure(_RunCase):
    def test_a_failing_step_unmounts_and_propagates(self):
        # 半装的盘挂着一堆挂载点，比一句报错更难查
        self.steps["step_packages"].side_effect = InstallerError("装包失败", EXIT_USAGE)
        with self.assertRaises(InstallerError):
            pipeline.run(self.plan(), self.reporter, password="pw", confirm=lambda *a: None)
        self.assertTrue(any("umount" in c for c in self.runner.commands()))
        self.assertIn("失败收尾：卸载目标", self.reporter.notes)


class TestRunCancel(_RunCase):
    def test_cancel_raises_cancelled_and_touches_nothing(self):
        with self.assertRaises(pipeline.Cancelled) as ctx:
            pipeline.run(self.plan(), self.reporter, password="pw", dry_run=True,
                         confirm=lambda *a: None, should_cancel=lambda: True)
        self.assertIsInstance(ctx.exception, InstallerError)
        self.assertEqual(ctx.exception.exit_code, pipeline.EXIT_CANCELLED)
        self.assertEqual(ctx.exception.exit_code, 130)
        commands = self.runner.commands()
        for destructive in ("wipefs", "mkfs", "mount", "pacstrap"):
            with self.subTest(destructive=destructive):
                self.assertFalse(any(destructive in c for c in commands))
        self.assertEqual(self.phases(), ["start"])


class TestResolveLayout(_RunCase):
    def test_dry_run_on_a_non_block_device_assumes_a_size(self):
        self.runner.dry_run = True
        with mock.patch("mipl_installer.util.is_block_device", return_value=False):
            layout = pipeline.resolve_layout(self.plan(), self.runner, self.reporter)
        self.assertEqual(layout, disk.plan_layout(pipeline.DRY_RUN_ASSUMED_SIZE))

    def test_real_run_goes_through_the_full_guard(self):
        sentinel = disk.plan_layout(40 * disk.GiB)
        with mock.patch("mipl_installer.disk.assert_usable", return_value=sentinel) as guard:
            layout = pipeline.resolve_layout(self.plan(), self.runner, self.reporter)
        self.assertEqual(layout, sentinel)
        self.assertEqual(guard.call_args.kwargs["size_bytes"], 40 * disk.GiB)


if __name__ == "__main__":
    unittest.main()
