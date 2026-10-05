"""V6 主题解析（08 §3.9）—— 注入固定时钟，不依赖 Qt。

跑法（任务验收命令）::

    python3 -m unittest discover -s installer/frontend/theme/tests \
        -t installer/frontend/theme
"""

import datetime
import unittest

from theme_mode import (
    DARK_START_HOUR,
    LIGHT_START_HOUR,
    SOURCE_AUTO,
    SOURCE_MANUAL,
    THEME_DARK,
    THEME_LIGHT,
    resolve_theme,
)


class ResolveThemeAutoTest(unittest.TestCase):
    """自动规则：本地时间 07:00–18:59 → light；19:00–06:59 → dark。"""

    def test_boundary_0659_is_dark(self):
        self.assertEqual(resolve_theme(datetime.time(6, 59)), THEME_DARK)

    def test_boundary_0700_is_light(self):
        self.assertEqual(resolve_theme(datetime.time(7, 0)), THEME_LIGHT)

    def test_boundary_1859_is_light(self):
        self.assertEqual(resolve_theme(datetime.time(18, 59)), THEME_LIGHT)

    def test_boundary_1900_is_dark(self):
        self.assertEqual(resolve_theme(datetime.time(19, 0)), THEME_DARK)

    def test_boundary_seconds_do_not_change_the_hour_verdict(self):
        # 18:59:59 仍是 18 点档；07:00:00 整点的前一秒仍是暗色。
        self.assertEqual(resolve_theme(datetime.time(18, 59, 59, 999999)), THEME_LIGHT)
        self.assertEqual(resolve_theme(datetime.time(6, 59, 59, 999999)), THEME_DARK)

    def test_midnight_and_early_morning_are_dark(self):
        for hour in (0, 1, 3, 6):
            with self.subTest(hour=hour):
                self.assertEqual(resolve_theme(datetime.time(hour, 30)), THEME_DARK)

    def test_daytime_hours_are_light(self):
        for hour in (7, 9, 12, 15, 18):
            with self.subTest(hour=hour):
                self.assertEqual(resolve_theme(datetime.time(hour, 30)), THEME_LIGHT)

    def test_accepts_datetime_not_only_time(self):
        self.assertEqual(resolve_theme(datetime.datetime(2026, 10, 1, 13, 0)), THEME_LIGHT)
        self.assertEqual(resolve_theme(datetime.datetime(2026, 10, 1, 23, 0)), THEME_DARK)

    def test_explicit_source_auto_matches_default(self):
        self.assertEqual(
            resolve_theme(datetime.time(13, 0), source=SOURCE_AUTO),
            resolve_theme(datetime.time(13, 0)),
        )

    def test_manual_dark_is_ignored_under_auto(self):
        # auto 下 manual_dark 只是残留状态，不能影响判定。
        self.assertEqual(resolve_theme(datetime.time(13, 0), SOURCE_AUTO, True), THEME_LIGHT)
        self.assertEqual(resolve_theme(datetime.time(23, 0), SOURCE_AUTO, False), THEME_DARK)

    def test_rule_constants_are_the_documented_ones(self):
        self.assertEqual((LIGHT_START_HOUR, DARK_START_HOUR), (7, 19))


class ResolveThemeManualTest(unittest.TestCase):
    """手动锁定：只认 manual_dark，不再随时钟变（08 §3.9）。"""

    def test_manual_dark_is_dark_at_noon(self):
        self.assertEqual(
            resolve_theme(datetime.time(12, 0), source=SOURCE_MANUAL, manual_dark=True),
            THEME_DARK,
        )

    def test_manual_light_is_light_at_midnight(self):
        self.assertEqual(
            resolve_theme(datetime.time(0, 0), source=SOURCE_MANUAL, manual_dark=False),
            THEME_LIGHT,
        )

    def test_locked_theme_does_not_follow_the_clock(self):
        # 「跨过 19:00 应当实时切换」只对 auto 成立；锁死后同一整天必须恒定。
        for manual_dark, expected in ((True, THEME_DARK), (False, THEME_LIGHT)):
            with self.subTest(manual_dark=manual_dark):
                for hour in range(24):
                    self.assertEqual(
                        resolve_theme(
                            datetime.time(hour, 0), source=SOURCE_MANUAL, manual_dark=manual_dark
                        ),
                        expected,
                        f"hour={hour} 时手动锁定被自动规则改回去了",
                    )

    def test_manual_defaults_to_light_when_flag_absent(self):
        self.assertEqual(
            resolve_theme(datetime.time(23, 0), source=SOURCE_MANUAL), THEME_LIGHT
        )

    def test_manual_still_validates_now(self):
        # 参数顺序写错（把 source 传成 now）必须炸，不能悄悄读系统时钟。
        with self.assertRaises(TypeError):
            resolve_theme(None, source=SOURCE_MANUAL, manual_dark=True)


class ResolveThemeInputTest(unittest.TestCase):
    def test_rejects_unknown_source(self):
        with self.assertRaises(ValueError):
            resolve_theme(datetime.time(12, 0), source="sunrise")

    def test_rejects_missing_or_bad_now(self):
        for bad in (None, "12:00", 12, datetime.time, object()):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    resolve_theme(bad)

    def test_return_value_is_plain_str(self):
        value = resolve_theme(datetime.time(12, 0))
        self.assertIs(type(value), str)
        self.assertIn(value, (THEME_LIGHT, THEME_DARK))


if __name__ == "__main__":
    unittest.main()
