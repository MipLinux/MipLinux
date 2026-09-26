"""「高级安装」四项的候选名单与校验。

名单必须来自运行系统上真实的文件，**绝不内建兜底名单** —— 内建一份就等于把
「界面里能选、写进目标却不生效」重新种回去（Issue #63 / #64）。所以这一组
全在假根上验：名单读不到时宁可空着，也不摆一排好看的假选项。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from mipl_installer import options
from mipl_installer.util import EXIT_CONFIGURE, InstallerError

REAL_ZONEINFO = Path("/usr/share/zoneinfo")


class _RootCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def copy_zone(self, tz: str) -> bool:
        """从真实 zoneinfo 拷一个 TZif 进来；没有就返回 False（调用方跳过断言）。

        真的 TZif 是这一组的关键：`zone_offset` 走 `ZoneInfo.from_file`，
        空文件或自造文本只会走到 except 分支，测不出夏令时。
        """
        source = REAL_ZONEINFO / tz
        if not source.is_file():
            return False
        target = self.root / tz
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return True


class TestConfined(_RootCase):
    def test_rejects_path_escape(self):
        """路径逃逸守卫：`../../etc/passwd` 能让存在性检查**通过**，
        然后被当成合法时区写进目标 —— 那不是用户输错了，是逃逸。"""
        for value in ("../etc/passwd", "a/../../b", "/etc/passwd", ""):
            with self.subTest(value=value):
                self.assertIsNone(options.confined(str(self.root), value))

    def test_accepts_a_normal_name(self):
        self.assertEqual(options.confined(str(self.root), "Asia/Shanghai"),
                         self.root / "Asia" / "Shanghai")


class TestTimezones(_RootCase):
    TAB = "\n".join([
        "# 注释行不算",
        "CN\t+3114+12128\tAsia/Shanghai",
        "",
        "US\t+404251-0740023\tAmerica/New_York",
    ])

    def test_reads_field_three_and_skips_comments_and_blanks(self):
        (self.root / "zone1970.tab").write_text(self.TAB, encoding="utf-8")
        self.assertEqual(options.timezones(str(self.root)), ["Asia/Shanghai", "America/New_York"])

    def test_falls_back_to_zone_tab(self):
        (self.root / "zone.tab").write_text("CN\t+3114+12128\tAsia/Shanghai\n", encoding="utf-8")
        self.assertEqual(options.timezones(str(self.root)), ["Asia/Shanghai"])

    def test_no_tab_file_is_an_empty_list(self):
        """读不到就空着 —— 内建一份名单会掩盖「这个环境列不出来」。"""
        self.assertEqual(options.timezones(str(self.root)), [])


class TestZoneOffset(_RootCase):
    JANUARY = datetime(2024, 1, 15, 12, 0, tzinfo=dt_timezone.utc)
    JULY = datetime(2024, 7, 15, 12, 0, tzinfo=dt_timezone.utc)

    def test_shanghai_has_no_dst(self):
        if not self.copy_zone("Asia/Shanghai"):
            self.skipTest("本机没有 /usr/share/zoneinfo/Asia/Shanghai")
        for moment in (self.JANUARY, self.JULY):
            with self.subTest(moment=moment):
                self.assertEqual(options.zone_offset("Asia/Shanghai", str(self.root), now=moment),
                                 "UTC+08:00")

    def test_new_york_changes_with_dst(self):
        """偏移显示的是**当前**值：界面上那一列只是提示，写进目标的是 id 本身。"""
        if not self.copy_zone("America/New_York"):
            self.skipTest("本机没有 /usr/share/zoneinfo/America/New_York")
        self.assertEqual(options.zone_offset("America/New_York", str(self.root), now=self.JANUARY),
                         "UTC-05:00")
        self.assertEqual(options.zone_offset("America/New_York", str(self.root), now=self.JULY),
                         "UTC-04:00")

    def test_nonexistent_zone_is_none(self):
        self.assertIsNone(options.zone_offset("Nowhere/Nope", str(self.root), now=self.JANUARY))

    def test_escape_attempt_is_none(self):
        self.assertIsNone(options.zone_offset("../etc/passwd", str(self.root), now=self.JANUARY))


class TestKeymaps(_RootCase):
    def _map(self, relative: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x1f\x8b fake")          # 内容无关，`keymaps` 只看文件名

    def test_strips_suffix_and_directory(self):
        """名字写进 `vconsole.conf` 的 `KEYMAP=`，目录层级（`i386/qwerty/us`）不保证被认出来。"""
        self._map("i386/qwerty/us.map.gz")
        self._map("i386/qwerty/be-latin1.map.gz")
        self.assertEqual(options.keymaps(str(self.root)), ["be-latin1", "us"])

    def test_deduplicates_the_same_basename(self):
        self._map("i386/qwerty/us.map.gz")
        self._map("mac/us.map.gz")
        self.assertEqual(options.keymaps(str(self.root)), ["us"])

    def test_missing_root_is_an_empty_list(self):
        self.assertEqual(options.keymaps(str(self.root / "nope")), [])


class TestLocales(_RootCase):
    def test_takes_field_one_of_each_non_comment_line(self):
        path = self.root / "SUPPORTED"
        path.write_text("\n".join([
            "# 注释",
            "",
            "zh_CN.UTF-8 UTF-8",
            "en_US.UTF-8 UTF-8",
        ]), encoding="utf-8")
        self.assertEqual(options.locales(str(path)), ["zh_CN.UTF-8", "en_US.UTF-8"])

    def test_missing_file_is_an_empty_list(self):
        self.assertEqual(options.locales(str(self.root / "SUPPORTED")), [])


class TestValidators(_RootCase):
    def test_timezone_must_exist(self):
        """Issue #66：`ln -sf` 不检查目标，打错的时区会变成悬空软链。"""
        with self.assertRaises(InstallerError) as ctx:
            options.validate_timezone("Nowhere/Nope", str(self.root))
        self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)

    def test_timezone_escape_is_refused(self):
        # 逃逸在存在性检查**之前**就被挡下，所以假根里连 Asia/ 都不用建
        with self.assertRaises(InstallerError) as ctx:
            options.validate_timezone("../Asia/Shanghai", str(self.root))
        self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)

    def test_timezone_accepts_one_that_exists(self):
        if not self.copy_zone("Asia/Shanghai"):
            self.skipTest("本机没有 /usr/share/zoneinfo/Asia/Shanghai")
        options.validate_timezone("Asia/Shanghai", str(self.root))     # 不该抛

    def test_keymap_must_be_in_the_list(self):
        (self.root / "us.map.gz").write_bytes(b"fake")
        with self.assertRaises(InstallerError) as ctx:
            options.validate_keymap("teapot", str(self.root))
        self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)
        options.validate_keymap("us", str(self.root))                  # 名单里有，不该抛

    def test_keymap_skips_when_the_root_is_missing(self):
        """**故意的**：没装 kbd 的环境里无从判断，名单在、名字不在才要拦（Issue #64）。"""
        options.validate_keymap("teapot", str(self.root / "nope"))

    def test_hostname_accepts_rfc1123_names(self):
        for hostname in ("mipl", "my-host", "a", "a" * 63):
            with self.subTest(hostname=hostname):
                options.validate_hostname(hostname)                    # 不该抛

    def test_hostname_rejects_bad_names(self):
        for hostname in ("-x", "x-", "", "a_b", "a" * 64):
            with self.subTest(hostname=hostname):
                with self.assertRaises(InstallerError) as ctx:
                    options.validate_hostname(hostname)
                self.assertEqual(ctx.exception.exit_code, EXIT_CONFIGURE)


if __name__ == "__main__":
    unittest.main()
