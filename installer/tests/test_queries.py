"""界面与后端之间的那条缝：JSON 行协议 + 只读出口。

这是 Issue #97 新长出来的一层，两侧各有一个消费者，而它坏起来**两侧都不会红**：

* `events.JsonReporter` 少发一条 `end`，界面就把「子进程结束了」和「装完了」
  混为一谈（进度环停在半路，而日志里什么都没说）；
* `cli.run_query()` 往 stdout 多写一行别的东西，界面那句 `JSON.parse` 就整个失败，
  而 `--print-disks` 单独跑起来看着完全正常。

所以这里两边都钉：**每行一个 JSON 对象**、判别字段齐全、
**stdout 上恰好一份文档**。
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from mipl_installer import cli, events, queries, util
from mipl_installer.events import Event, JsonReporter
from mipl_installer.util import EXIT_USAGE, InstallerError
from tests.support import FakeRunner


def _lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class TestFrontendArgvContract(unittest.TestCase):
    """`main.js` 能拼出来的每一个开关，后端的 argparse 都必须认得。

    **为什么不各测各的**：两侧各自绿、合起来错，是这一层最典型的坏法。
    界面加一个出口忘了在后端加开关，症状不是报错，而是「点了开始安装，什么都不发生」——
    子进程在 argparse 那一步就退了，而 `runQuery` 只会回一句 `ok:false`。

    所以这里**从 `main.js` 的源码里抽**开关名，而不是抄一份到测试里 ——
    抄一份的话，测试与实现会一起漂，谁也拦不住。
    """

    #: 只在这个区间里抽：从 `QUERY_ARGV` 到窗口那一节之前 ——
    #: 也就是 `QUERY_ARGV` / `PLAN_FLAGS` / `installArgv` / `startInstall` / `cancelInstall`
    #: 全部拼命令行的地方（`--root-password-stdin` 就在 `startInstall` 里，
    #: 区间切早了会把它漏掉）。区间之外是 Electron 自己的 `--theme` / `--ui-scale`
    #: （启动器传给主进程的，根本不进后端），全文件抽会把它们一起算进来。
    START = "const QUERY_ARGV"
    END = "// ---------------------------------------------------------------- 窗口"

    def _flags_from_main_js(self) -> set[str]:
        from pathlib import Path

        main_js = (Path(__file__).resolve().parents[1]
                   / "frontend" / "app" / "main.js").read_text(encoding="utf-8")
        section = main_js[main_js.index(self.START):main_js.index(self.END)]
        # 单引号与**反引号**都要认：收值的出口写的是 `` `--check-locale=${…}` ``，
        # 只认单引号会把它们整批漏掉 —— 而漏掉的表现是这条断言悄悄变成假绿。
        return set(re.findall(r"['`](--[a-z][a-z-]*)", section))

    def test_the_section_is_actually_there(self):
        """区间标记本身也会漂 —— 抽不到东西时必须红，而不是默默通过一个空集合。

        `> 15` 这个阈值**拦不住「漏抽一半」**（漏了照样过），所以再点名几个
        **只出现在模板串里**的开关：它们是上面那条正则的活体检测。
        """
        flags = self._flags_from_main_js()
        self.assertGreater(len(flags), 15, f"只从 main.js 里抽出 {len(flags)} 个开关：{sorted(flags)}")
        for must in ("--connect-wifi", "--check-hostname", "--check-locale",
                     "--check-keymap", "--check-timezone", "--print-keymap",
                     "--root-password-stdin"):
            with self.subTest(flag=must):
                self.assertIn(must, flags, f"{must} 没被抽出来 —— 抽取逻辑漏了模板串里的开关")

    def test_every_flag_main_js_can_emit_is_accepted(self):
        """比对**名字**，不去猜 argparse 收不收值。

        `--yes` / `--print-disks` 是开关（`store_true`），`--disk` / `--print-keymap` 收值；
        硬塞一个 `=x` 给前者会得到「不认识」的假红。而「认不认识这个名字」才是这条
        断言要问的 —— 值怎么给由 `main.js` 统一用 `--开关=值` 保证。
        """
        known = {opt for action in cli.build_parser()._actions for opt in action.option_strings}
        for flag in sorted(self._flags_from_main_js()):
            with self.subTest(flag=flag):
                self.assertIn(flag, known, f"main.js 会发 {flag}，而后端的 argparse 不认识它")

    def test_the_gui_install_flag_set_parses_into_a_plan(self):
        """界面点「开始安装」时拼的那一串 —— 原样送给 argparse，应当得到一份完整的 `Plan`。"""
        argv = [
            "--json-events", "--yes",
            "--disk=/dev/vda", "--hostname=mipl", "--user=mipl",
            "--locale=ja_JP.UTF-8", "--timezone=Asia/Tokyo", "--keymap=de",
            "--password-stdin",
        ]
        args = cli.build_parser().parse_args(argv)
        self.assertTrue(args.json_events and args.yes and args.password_stdin)
        plan = cli.build_plan(args)
        self.assertEqual(plan.disk, "/dev/vda")
        self.assertEqual(plan.hostname, "mipl")
        self.assertEqual(plan.locale, "ja_JP.UTF-8")
        self.assertEqual(plan.timezone, "Asia/Tokyo")
        self.assertEqual(plan.keymap, "de")
        # 界面不传 `--steps`：装盘的四个阶段永远是全部四段（少勾一段就装出半成品）
        self.assertEqual(plan.steps, cli.STEP_ORDER)


class TestJsonReporter(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.reporter = JsonReporter(stream=self.stream)

    def test_starts_with_a_hello_carrying_the_protocol_version(self):
        """第一条必须是 `hello`：界面靠它确认「对面是不是我认识的这个后端」。"""
        first = _lines(self.stream.getvalue())[0]
        self.assertEqual(first["kind"], "hello")
        self.assertEqual(first["protocol"], events.PROTOCOL)

    def test_one_json_object_per_line(self):
        self.reporter.emit(Event("disk", "正在重新分区并创建文件系统"))
        self.reporter.note("目标盘：  /dev/vda（40.0 GiB）")
        self.reporter.command(["wipefs", "-a", "/dev/vda"])
        for line in self.stream.getvalue().splitlines():
            with self.subTest(line=line):
                self.assertIsInstance(json.loads(line), dict, "每一行都要能单独 parse")

    def test_event_keeps_the_phase_and_percent(self):
        self.reporter.emit(Event("done", "装完了", percent=100, detail="账号：mipl"))
        record = _lines(self.stream.getvalue())[-1]
        self.assertEqual(record["kind"], "event")
        self.assertEqual(record["phase"], "done")
        self.assertEqual(record["percent"], 100)
        self.assertEqual(record["detail"], "账号：mipl")

    def test_unknown_percent_is_null_not_zero(self):
        """`None` = 后端也不知道装了多少（`pacstrap` 不报百分比）。
        写成 0 的话界面会把它画成「刚开始」，那是替后端编了一个数。"""
        self.reporter.emit(Event("packages", "正在从镜像源下载并安装软件包"))
        self.assertIsNone(_lines(self.stream.getvalue())[-1]["percent"])

    def test_error_carries_the_machine_readable_reason(self):
        """失败码是**给界面的**：界面拿它挑自己的句子、并决定给不给补救按钮。

        没有它，界面只能去比对中文报错 —— 那是措辞，改一个字就失效
        （2026-10-06：`/mnt` 被占用那条要能一键卸载，靠的就是这个字段）。
        """
        self.reporter.error(3, "/mnt 已经是个挂载点，拒绝把系统装上去",
                            "手动卸载后再跑", "targetMounted")
        record = _lines(self.stream.getvalue())[-1]
        self.assertEqual(record["reason"], "targetMounted")
        self.assertEqual(record["code"], 3)
        self.assertEqual(record["hint"], "手动卸载后再跑")

    def test_error_without_a_reason_says_null_not_empty(self):
        self.reporter.error(7, "出事了", None)
        self.assertIsNone(_lines(self.stream.getvalue())[-1]["reason"])

    def test_error_is_followed_by_end(self):
        """失败也要走同一条流、同一个解析器：只看 `close` 事件的话，
        被杀掉的进程和装完的进程长得一模一样。"""
        self.reporter.error(2, "非交互环境必须用 --password-stdin", "先加 --yes")
        self.reporter.finish(2)
        records = _lines(self.stream.getvalue())
        self.assertEqual(records[-2]["kind"], "error")
        self.assertEqual(records[-2]["code"], 2)
        self.assertEqual(records[-1], {"kind": "end", "code": 2})

    def test_chinese_is_not_escaped(self):
        """日志要能整份抄进 docs/work/tech/ —— `\\u4e2d\\u6587` 是没法读的。"""
        self.reporter.note("中文")
        self.assertIn("中文", self.stream.getvalue())


class TestQueryRequested(unittest.TestCase):
    """`query_requested()` 与 argparse 的开关表必须同步。

    漏一个的症状：那个开关被当成安装模式，然后抱怨没给 `--disk`。
    所以这里对**每个**只读开关都点一次名。
    """

    FLAGS = [
        ["--print-disks"],
        ["--print-network"],
        ["--print-wifi"],
        ["--print-timezones"],
        ["--print-locales"],
        ["--print-keymaps"],
        ["--print-keymap=de"],
        ["--print-plan"],
        ["--check-hostname=mipl"],
        ["--check-locale=zh_CN.UTF-8"],
        ["--check-keymap=us"],
        ["--check-timezone=Asia/Shanghai"],
        ["--connect-wifi=MyNet"],
        ["--reboot"],
        ["--unmount-target"],
    ]

    def test_every_read_only_flag_is_recognised(self):
        parser = cli.build_parser()
        for argv in self.FLAGS:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(cli.query_requested(args), f"{argv} 没被认成只读出口")

    def test_installing_is_not_a_query(self):
        args = cli.build_parser().parse_args(["--disk", "/dev/vda", "--dry-run"])
        self.assertFalse(cli.query_requested(args))


class TestRunQuery(unittest.TestCase):
    """stdout 上**恰好一份 JSON 文档**，别的什么都没有。"""

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_stdout_carries_exactly_one_json_document(self):
        code, out, _err = self._run(["--print-keymaps"])
        self.assertEqual(code, 0)
        payload = json.loads(out)                     # 整份必须一次 parse 成功
        self.assertIn("keymaps", payload)
        self.assertIsInstance(payload["keymaps"], list)

    def test_empty_answer_is_still_a_document(self):
        """空答案也要是一份能 parse 的文档 —— 界面不该为「什么都没有」写第二条路径。"""
        code, out, _err = self._run(["--print-locales"])
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out).get("locales"), list)

    def test_read_only_exits_do_not_need_a_disk(self):
        """只读出口不该逼人先指一块盘 —— 这正是 `--disk` 从 required 拿掉的原因。"""
        code, out, err = self._run(["--print-plan"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["filesystem"], "ext4")

    def test_unknown_keymap_is_a_usage_error_not_a_traceback(self):
        code, out, err = self._run(["--print-keymap=teapot"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual(out, "", "失败时 stdout 上不该有半份文档")
        self.assertIn("没有这份键位映射", err)

    def test_check_hostname_answers_with_a_reason_code(self):
        code, out, _err = self._run(["--check-hostname=mipl"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": True, "reason": None, "message": ""})

        code, out, _err = self._run(["--check-hostname=-bad-"])
        self.assertEqual(code, 0, "「这个值不合规」是正常答案，不是命令失败")
        self.assertEqual(json.loads(out)["reason"], "format")

    def test_check_locale_answers_with_a_reason_code(self):
        code, out, _err = self._run(["--check-locale=zh_CN.UTF-8"])
        self.assertEqual((code, json.loads(out)["ok"]), (0, True))
        code, out, _err = self._run(["--check-locale=ja_XX.UTF-8"])
        self.assertEqual((code, json.loads(out)["reason"]), (0, "notInList"))

    def test_runner_narration_goes_to_stderr(self):
        """`--print-disks` 会跑 `blkid`，那些命令行如果落在 stdout，
        界面就得先剥掉几行人话才能 parse。"""
        code, out, _err = self._run(["--print-disks"])
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out), dict)   # 整份仍是纯 JSON

    def test_wifi_password_comes_from_stdin(self):
        """密码只走 stdin —— 这条在 `--connect-wifi` 上同样成立。"""
        fake = mock.Mock()
        fake.isatty.return_value = False
        fake.readline.return_value = "hunter2\n"
        with mock.patch.object(sys, "stdin", fake):
            self.assertEqual(cli.read_wifi_password(), "hunter2")

        fake.readline.return_value = "\n"
        with mock.patch.object(sys, "stdin", fake):
            self.assertEqual(cli.read_wifi_password(), "", "开放网络就是空密码，不该拒绝")

    def test_reboot_is_a_query_and_starts_nothing_under_dry_run(self):
        """`--reboot` 走出口那一支，且 `--dry-run` 下**一个子进程都不许起**。

        回归（2026-10-06 实机事故）：`run_query()` 造 `Runner` 时漏传了
        `dry_run=args.dry_run`，于是 `--reboot --dry-run` 在开发机上真的执行了
        `systemctl reboot`。这条用例因此把 subprocess **封死** —— 它要证明的不是
        「命令跑了」，而是「dry-run 下 subprocess 根本没被叫到」。
        凡是碰系统动作的用例都该这样写：把出口封住，而不是指望参数拦得住。
        """
        boom = AssertionError("dry-run 下不许起任何子进程")
        with mock.patch.object(util.subprocess, "run", side_effect=boom), \
                mock.patch.object(util.subprocess, "Popen", side_effect=boom):
            code, out, err = self._run(["--reboot", "--dry-run"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"ok": True})

    def test_reboot_runs_systemctl_reboot_through_the_runner(self):
        """命令从**后端**发出（`Runner` 是动系统的唯一出口），且只跑这一条。

        用 `FakeRunner`：这条断言看的是「拼出来的是哪条命令」，真去跑它就会重启
        这台机器 —— 单测里不许出现真的 `systemctl reboot`。
        """
        runner = FakeRunner(dry_run=True)
        self.assertEqual(queries.reboot(runner), {"ok": True})
        self.assertEqual(runner.commands(), ["systemctl reboot"])

    def test_unmount_target_reports_what_it_actually_saw(self):
        """卸完**再看一眼** `/mnt` 还在不在挂载表里 —— 说「卸好了」而实际还挂着，
        用户点第二次还是失败，只会以为按钮坏了。"""
        runner = FakeRunner()
        with mock.patch("mipl_installer.disk.is_mountpoint", return_value=False):
            self.assertEqual(queries.unmount_target(runner), {"ok": True, "mounted": False})
        self.assertIn("umount -R /mnt", runner.commands())

        still = FakeRunner()
        with mock.patch("mipl_installer.disk.is_mountpoint", return_value=True):
            self.assertEqual(queries.unmount_target(still), {"ok": False, "mounted": True})

    def test_unmount_target_never_touches_the_disk_itself(self):
        """它只卸挂载：命令里不许出现 wipefs / mkfs / parted 这类动盘的东西。"""
        runner = FakeRunner()
        with mock.patch("mipl_installer.disk.is_mountpoint", return_value=False):
            queries.unmount_target(runner)
        joined = " ".join(runner.commands())
        for forbidden in ("wipefs", "mkfs", "parted", "partprobe"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, joined)

    def test_unmount_target_is_a_query_and_never_runs_under_dry_run(self):
        boom = AssertionError("dry-run 下不许起任何子进程")
        with mock.patch.object(util.subprocess, "run", side_effect=boom), \
                mock.patch.object(util.subprocess, "Popen", side_effect=boom):
            code, out, err = self._run(["--unmount-target", "--dry-run"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"ok": True, "mounted": True})

    def test_reboot_failure_is_not_reported_as_success(self):
        """`systemctl reboot` 失败时不许回 `ok` —— 界面据此说「重启失败，请手动重启」。"""
        runner = FakeRunner()
        runner.fail_patterns.add("systemctl reboot")
        with self.assertRaises(InstallerError):
            queries.reboot(runner)


class TestProgressContract(unittest.TestCase):
    """进度事件的**跨语言契约**：后端发 `step_id`，前端查 `progress.step.<id>`。

    两边各写各的、谁也不知道对方漏了什么的代价是：实机上那一格显示成 `⟨缺键⟩`，
    或者英文模式下冒出一句中文。所以这里从后端唯一的 `PHASE_STEPS` 抽出全部 id，
    逐个到两份文案里找 —— 抽的是**实现**，不是抄一份到测试里（抄一份会一起漂）。
    """

    def _strings(self, lang: str) -> dict:
        path = (Path(__file__).resolve().parents[1]
                / "frontend" / "app" / "renderer" / "i18n" / f"{lang}.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_every_step_id_has_copy_in_both_languages(self):
        for lang in ("zh_CN", "en_US"):
            strings = self._strings(lang)
            for phase, ids in events.PHASE_STEPS.items():
                for step_id in ids:
                    with self.subTest(lang=lang, phase=phase, step=step_id):
                        self.assertIn(f"progress.step.{step_id}", strings)

    def test_progress_page_knows_every_phase(self):
        """进度页的阶段表与 `events.PHASES` 对齐：少一个，那一格就永远不亮。"""
        source = (Path(__file__).resolve().parents[1]
                  / "frontend" / "app" / "renderer" / "js" / "pages" / "progress.js").read_text(encoding="utf-8")
        for phase in events.PHASES:
            if phase == "done":
                continue  # done 不是轨道上的一格，它是收尾
            with self.subTest(phase=phase):
                self.assertIn(f"phase: '{phase}'", source)

    def test_the_ring_no_longer_claims_a_global_percentage(self):
        """**回归**：环上不许再出现「一进阶段就领了这一段的百分比」。

        旧版那张 `until: 70` 的落格表就是实机反馈里「刚开始下载就显示 70%」的来源。
        """
        source = (Path(__file__).resolve().parents[1]
                  / "frontend" / "app" / "renderer" / "js" / "pages" / "progress.js").read_text(encoding="utf-8")
        self.assertNotIn("until:", source)


class TestQueryShapes(unittest.TestCase):
    """出口吐的是**事实**，不是界面词汇。"""

    def test_wifi_failure_is_an_answer_not_a_command_failure(self):
        """连不上是**预期内**的结果（密码打错最常见）。
        用退出码表达它就等于让界面去分辨「哪个非零码是密码错」。"""
        result = queries.connect_wifi(_FailingRunner(), "MyNet", "wrong")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "auth")
        self.assertIn("message", result)

    def test_hostname_verdict_never_raises(self):
        self.assertTrue(queries.check_hostname("mipl")["ok"])
        self.assertEqual(queries.check_hostname("-x")["reason"], "format")

    def test_candidate_dict_is_facts_only(self):
        """没有「推荐」「危险」「胶囊」这类词 —— 它们要翻译成中英两套，属于渲染层。"""
        from mipl_installer import disk

        candidate = disk.Candidate(path="/dev/vda", model="", size=40 * disk.GiB, removable=False,
                                   in_use=False, table_type=None, partitions=())
        record = queries.candidate_dict(candidate)
        self.assertEqual(record["size"], 40 * disk.GiB)
        self.assertEqual(record["size_label"], "40.0 GiB")
        self.assertEqual(record["model"], "")
        self.assertTrue(record["usable"])
        self.assertNotIn("recommended", record)
        self.assertNotIn("badges", record)

    def test_timezone_offset_drops_the_utc_prefix(self):
        """界面那句 `timezone.display` 已经是 `%1（UTC%2）`，前缀由文案提供 ——
        留着前缀会渲染成「中国标准时间（UTCUTC+08:00）」。"""
        payload = queries.timezones()
        shanghai = [zone for zone in payload["timezones"] if zone["id"] == "Asia/Shanghai"]
        if not shanghai:
            self.skipTest("本机 zone1970.tab 里没有 Asia/Shanghai")
        self.assertEqual(shanghai[0]["offset"], "+08:00")


class TestDiskArgument(unittest.TestCase):
    def test_missing_disk_is_a_usage_error(self):
        with self.assertRaises(InstallerError) as ctx:
            queries.require_disk_argv(None)
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_given_disk_passes_through(self):
        self.assertEqual(queries.require_disk_argv("/dev/vda"), "/dev/vda")


class TestCancelFlag(unittest.TestCase):
    def test_sigusr1_raises_the_hand_and_the_probe_reads_it(self):
        """取消的语义是「阶段之间生效」（`pipeline.run(should_cancel=…)`），
        所以这里只是举手，不在信号处理函数里抛异常。"""
        flag = cli.CancelFlag()
        self.assertFalse(flag())
        flag.request(15, None)          # 信号处理函数拿到的两个参数
        self.assertTrue(flag())


class _FailingRunner:
    """连着就失败的 Runner 替身：`nmcli` 报的是密码不对。"""

    dry_run = False

    def run(self, argv, **kwargs):
        raise InstallerError(
            "命令失败（退出码 4）：nmcli --ask device wifi connect MyNet：\n"
            "    Error: Connection activation failed: (7) Secrets were required, but not provided."
        )


if __name__ == "__main__":
    unittest.main()
