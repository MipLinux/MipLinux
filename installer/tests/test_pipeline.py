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

    def test_done_is_the_only_event_carrying_a_percent(self):
        """**全局百分比没有了**（2026-10-06 实机反馈：一进 packages 就显示 70%）。

        现在只有 `done` 那一条带 100；其余进度一律走 `step_id` + `step`/`total`
        （当前阶段内**真的数得出来**的那部分）。
        """
        pipeline.run(self.plan(), self.reporter, password="pw", confirm=lambda *a: None)
        for event in self.reporter.events:
            if event.percent is not None:
                self.assertEqual((event.phase, event.percent), ("done", 100))
                self.assertIsNone(event.step, "done 不该带细计数")

    def test_only_the_requested_steps_run(self):
        pipeline.run(self.plan(steps=("disk", "boot")), self.reporter,
                     password="pw", confirm=lambda *a: None)
        self.assertEqual(self.phases(), ["start", "disk", "boot", "done"])
        self.steps["step_packages"].assert_not_called()
        self.steps["step_configure"].assert_not_called()


class TestProgressEvents(unittest.TestCase):
    """细进度的契约：**跑真的四个阶段模块**（不换成替身），看它们各自发了什么。

    `_RunCase` 把四个 `step_*` 全 mock 掉了，所以那一组验不到「模块自己发的
    `step_id` 对不对」—— 而拼错一个 id 的表现是界面上那一格显示成缺键，
    要等到装机才看得见。这一组用 dry-run 走完整条链，专验这件事。
    """

    def setUp(self):
        self.reporter = RecordingReporter()
        # blkid 的 UUID 得给一个：`uuid_of` 读不到会当场报错（那是设计如此），
        # 而这一组验的是进度事件、不是「dry-run 下 UUID 从哪来」。
        self.runner = FakeRunner(reporter=self.reporter, dry_run=True,
                                 outputs={"blkid": "11111111-1111-1111-1111-111111111111"})
        patch = mock.patch("mipl_installer.pipeline.Runner", return_value=self.runner)
        patch.start()
        self.addCleanup(patch.stop)

    def run_chain(self, **overrides) -> list:
        plan = pipeline.Plan(disk="/dev/vda", **overrides)
        pipeline.run(plan, self.reporter, password="pw", confirm=lambda *a: None, dry_run=True)
        return [event for event in self.reporter.events if event.step_id]

    def test_every_step_id_belongs_to_its_phase(self):
        steps = self.run_chain()
        self.assertTrue(steps, "整条链一条细进度都没发 —— 进度页会退化成空壳")
        for event in steps:
            with self.subTest(phase=event.phase, step=event.step_id):
                self.assertIn(event.step_id, events.PHASE_STEPS[event.phase])

    def test_step_ids_of_a_phase_arrive_in_contract_order(self):
        """子步骤按 `PHASE_STEPS` 的顺序出现 —— 界面就是按到达顺序画的。"""
        seen: dict[str, list[str]] = {}
        for event in self.run_chain():
            seen.setdefault(event.phase, [])
            if event.step_id not in seen[event.phase]:
                seen[event.phase].append(event.step_id)
        self.assertTrue(seen)
        for phase, ids in seen.items():
            with self.subTest(phase=phase):
                contract = [step for step in events.PHASE_STEPS[phase] if step in ids]
                self.assertEqual(ids, contract, f"{phase} 的步骤顺序与 PHASE_STEPS 对不上")

    def test_no_step_event_invents_a_counter(self):
        """dry-run 下数不出包数：`step`/`total` 必须是 `None`，不是 0。

        界面按「有没有 total」决定画计数还是画不确定态 —— 编一个 0/0 出来，
        它就会画成一根一直停在 0 的条。
        """
        for event in self.run_chain():
            with self.subTest(step=event.step_id):
                self.assertIsNone(event.step)
                self.assertIsNone(event.total)


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


class TestAttachTargetLog(unittest.TestCase):
    """日志持续并写到目标盘：强杀之后盘上是到挂死点为止的完整日志。"""

    def test_reporter_replays_history_into_the_attached_sink(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            extra = Path(tmp) / "target.log"
            reporter = events.TextReporter(stream=io.StringIO())
            reporter.note("挂载前的一行")
            reporter.attach_log_path(str(extra))
            reporter.note("挂载后的一行")
            reporter.close()
            self.assertEqual(extra.read_text(encoding="utf-8"),
                             "    挂载前的一行\n    挂载后的一行\n")

    def test_json_reporter_writes_every_sink(self):
        import io
        import json as jsonmod
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "main.log"
            extra = Path(tmp) / "target.log"
            reporter = events.JsonReporter(stream=io.StringIO(), log_path=str(main))
            reporter.attach_log_path(str(extra))
            reporter.note("hi")
            reporter.close()
            for path in (main, extra):
                records = [jsonmod.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual([r["kind"] for r in records], ["hello", "note"])

    def test_attach_creates_the_dir_and_writes_from_now_on(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "mnt"
            target.mkdir()
            stream = io.StringIO()
            reporter = events.TextReporter(stream=stream)
            runner = FakeRunner(reporter=reporter)
            pipeline.attach_target_log(runner, pipeline.Plan(disk="/dev/null", target=str(target)), reporter)
            dest = target / "var" / "log" / "mipl-installer-install.log"
            self.assertTrue(dest.is_file())
            reporter.note("落盘的一行")
            reporter.close()
            self.assertIn("落盘的一行", dest.read_text(encoding="utf-8"))
            # 挂上了**不说**：正常流里「我们把日志写到哪儿了」是自我指涉的噪音，
            # 失败时由 `cli.log_locations()` 报（它会先确认文件真的在）。
            self.assertNotIn("持续并写", stream.getvalue())

    def test_reporter_without_attach_is_a_noop(self):
        runner = FakeRunner(reporter=RecordingReporter())
        pipeline.attach_target_log(runner, pipeline.Plan(disk="/dev/null"), RecordingReporter())
        self.assertEqual(runner.commands(), [])


if __name__ == "__main__":
    unittest.main()
