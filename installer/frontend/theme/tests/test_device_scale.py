"""V7 的纯函数侧：设备层缩放（08 §3.10）+ 界面层缩放档位推荐 —— 无副作用、不依赖界面栈。

跑法（任务验收命令）::

    python3 -m unittest discover -s installer/frontend/theme/tests \
        -t installer/frontend/theme
"""

import unittest

from device_scale import (
    UI_SCALE_PERCENTS,
    recommend_ui_scale_percent,
    DPI_2X,
    DPI_3X,
    RES_WIDTH_2X,
    RES_WIDTH_3X,
    SOURCE_COMPOSITOR,
    SOURCE_FALLBACK,
    SOURCE_PHYSICAL_DPI,
    SOURCE_RESOLUTION,
    DeviceScale,
    device_scale,
    physical_dpi,
)

# 常见面板的物理尺寸（mm），用来把 DPI 档位定在一个确定的数上。
FHD_24IN = (531.0, 299.0)      # 1920x1080 @ ~24" → ~92 DPI
UHD_156IN = (345.0, 194.0)     # 3840x2160 @ 15.6" → ~282 DPI
UHD_12IN = (260.0, 150.0)      # 3840x2160 @ ~12"  → ~373 DPI
UHD = (3840, 2160)
UHD_5K = (5120, 2880)
FHD = (1920, 1080)

# 维护者裁决的反例：27" 4K —— 3840x2160，物理对角线 685.8mm（16:9），163.2 DPI。
# ② 因 DPI < 192 不终局，改走 ③；宽 3840 ≥ 3200 → 2x（不是字面版规则的 1x）。
UHD_27IN = (597.7265033600158, 336.2211581400089)

# 阈值精确用例（分辨率取 UHD，好让「① 终局」与「改走 ③」的 source 可区分）：
# 3840x2160 的对角线是 4405.814…px；512.0 x 278.51941135224297mm → 192.00000000000003 DPI，
# 恰好在 ② 的下界上，应当由 ② 终局给出 2x。
DPI_EXACTLY_192_SIZE = (512.0, 278.51941135224297)
# 同宽再高 0.635mm → 191.9 DPI，刚好掉到阈值下，必须改走 ③（宽 3840 ≥ 3200 → 2x）。
DPI_191_9_SIZE = (512.0, 279.15445741501287)
# 同一支 191.9 DPI 但分辨率只有 1920 宽 → ③ 兜底给 1x（source 仍必须是 resolution）。
DPI_191_9_FHD_SIZE = (256.0, 523.9610778432595)


class Level1CompositorTest(unittest.TestCase):
    """① 合成器 scale > 1 → 以它为准。"""

    def test_compositor_2_wins(self):
        decision = device_scale(2, UHD_12IN, UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_COMPOSITOR)
        self.assertFalse(decision.log_required)

    def test_compositor_3_wins(self):
        self.assertEqual(device_scale(3, None, FHD), 3)

    def test_compositor_overrides_dpi_conclusion(self):
        # 面板 DPI 算出 3x，但合成器说 2x —— 合成器优先（08 §3.10 ①）。
        self.assertEqual(physical_dpi(UHD_12IN, UHD) >= DPI_3X, True)
        decision = device_scale(2, UHD_12IN, UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_COMPOSITOR)

    def test_compositor_1_does_not_short_circuit(self):
        # Wayland 在没配置缩放时也报 1 —— 1 不是信息，必须继续走 ②③。
        decision = device_scale(1, None, UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)

    def test_compositor_1_with_only_low_res_gives_1(self):
        decision = device_scale(1, None, FHD)
        self.assertEqual(decision, 1)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertFalse(decision.log_required)

    def test_compositor_float_2_0_is_accepted(self):
        decision = device_scale(2.0, None, FHD)
        self.assertEqual(decision, 2)
        self.assertFalse(decision.log_required)

    def test_odd_compositor_value_is_normalized_and_flagged_for_log(self):
        decision = device_scale(1.5, None, FHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_COMPOSITOR)
        self.assertTrue(decision.log_required)
        self.assertTrue(decision.notes)

    def test_compositor_above_contract_is_clamped_to_3x_and_flagged(self):
        decision = device_scale(4, None, FHD)
        self.assertEqual(decision, 3)
        self.assertTrue(decision.log_required)

    def test_compositor_below_1_is_treated_as_no_info(self):
        decision = device_scale(0.5, None, UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertTrue(decision.log_required)
        self.assertTrue(any("0.5" in note for note in decision.notes))

    def test_rejects_non_numeric_output_scale(self):
        for bad in ("2", True):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    device_scale(bad, None, UHD)

    def test_rejects_non_finite_output_scale(self):
        with self.assertRaises(ValueError):
            device_scale(float("nan"), None, UHD)


class Level2PhysicalDpiTest(unittest.TestCase):
    """② 物理尺寸 → DPI：≥288 → 3x、≥192 → 2x；<192 **不终局**，改走 ③（维护者裁决 2026-10-01）。"""

    def test_high_dpi_laptop_panel_is_2x(self):
        self.assertTrue(DPI_2X <= physical_dpi(UHD_156IN, UHD) < DPI_3X)
        decision = device_scale(None, UHD_156IN, UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_PHYSICAL_DPI)
        self.assertFalse(decision.log_required)

    def test_very_high_dpi_panel_is_3x(self):
        self.assertTrue(physical_dpi(UHD_12IN, UHD) >= DPI_3X)
        decision = device_scale(None, UHD_12IN, UHD)
        self.assertEqual(decision, 3)
        self.assertEqual(decision.source, SOURCE_PHYSICAL_DPI)

    def test_dpi_exactly_192_is_2x_and_terminal_in_level_2(self):
        # 边界含等号：DPI == 192 走 ②，不落 ③。
        dpi = physical_dpi(DPI_EXACTLY_192_SIZE, UHD)
        self.assertGreaterEqual(dpi, DPI_2X)
        self.assertLess(dpi, DPI_2X + 0.001)
        decision = device_scale(None, DPI_EXACTLY_192_SIZE, UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_PHYSICAL_DPI)
        self.assertFalse(decision.log_required)

    def test_dpi_191_9_falls_through_to_resolution_fallback(self):
        # 阈值之下不能停在 1x：27" 4K 这类 163 DPI 面板是同一格。
        dpi = physical_dpi(DPI_191_9_SIZE, UHD)
        self.assertTrue(DPI_2X - 1 < dpi < DPI_2X)
        decision = device_scale(None, DPI_191_9_SIZE, UHD)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertEqual(decision, 2)  # 宽 3840 ≥ 3200
        self.assertIn("分辨率兜底", decision.reason)
        # 正常确定路线，不要求调用方记日志。
        self.assertFalse(decision.log_required)

    def test_191_9_dpi_with_low_resolution_gets_1x_from_level_3(self):
        decision = device_scale(None, DPI_191_9_FHD_SIZE, FHD)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertEqual(decision, 1)  # 宽 1920 < 3200
        self.assertFalse(decision.log_required)

    def test_27inch_4k_goes_to_resolution_fallback_and_is_2x(self):
        # 维护者裁决的反例：字面版规则会给 1x（画面过小），裁决版给 2x。
        # 3840x2160 @ 对角线 685.8mm（16:9）→ 163.2 DPI < 192。
        dpi = physical_dpi(UHD_27IN, UHD)
        self.assertTrue(160 < dpi < DPI_2X)
        decision = device_scale(None, UHD_27IN, UHD)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertEqual(decision, 2)
        self.assertIn("改走分辨率兜底", decision.reason)
        self.assertFalse(decision.log_required)

    def test_low_dpi_24inch_1080p_is_1x_via_level_3(self):
        # 92 DPI 的 24" 1080p：② 不终局，③ 兜底宽 1920 < 3200 → 1x，结论仍然正确。
        self.assertTrue(physical_dpi(FHD_24IN, FHD) < DPI_2X)
        decision = device_scale(None, FHD_24IN, FHD)
        self.assertEqual(decision, 1)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertFalse(decision.log_required)

    def test_physical_size_without_resolution_falls_through(self):
        # 算 DPI 要用 resolution；缺了就算不出 → 落 ④，1x 且必须记日志。
        decision = device_scale(None, UHD_156IN, None)
        self.assertEqual(decision, 1)
        self.assertEqual(decision.source, SOURCE_FALLBACK)
        self.assertTrue(decision.log_required)
        self.assertTrue(any("physical_size" in note for note in decision.notes))

    def test_invalid_physical_size_falls_back_to_resolution_and_logs(self):
        decision = device_scale(None, (0, 0), UHD)
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertTrue(decision.log_required)

    def test_physical_dpi_helper_returns_none_on_bad_input(self):
        for size, res in (
            (None, UHD),
            (UHD_156IN, None),
            ((345.0,), UHD),
            ((345.0, -194.0), UHD),
            (("345", "194"), UHD),
            (UHD_156IN, (0, 0)),
        ):
            with self.subTest(size=size, res=res):
                self.assertIsNone(physical_dpi(size, res))


class Level3ResolutionFallbackTest(unittest.TestCase):
    """③ 没有物理尺寸（虚拟显示 / QEMU / EDID 缺失）→ 按分辨率兜底。"""

    def test_3840_wide_virtual_display_is_2x(self):
        decision = device_scale(None, None, (3840, 2160))
        self.assertEqual(decision, 2)
        self.assertEqual(decision.source, SOURCE_RESOLUTION)
        self.assertFalse(decision.log_required)

    def test_3200_wide_is_2x_boundary(self):
        self.assertEqual(device_scale(None, None, (RES_WIDTH_2X, 1800)), 2)

    def test_3199_wide_is_1x(self):
        decision = device_scale(None, None, (RES_WIDTH_2X - 1, 1800))
        self.assertEqual(decision, 1)
        self.assertFalse(decision.log_required)

    def test_5120_wide_is_3x(self):
        self.assertEqual(device_scale(None, None, UHD_5K), 3)
        self.assertEqual(device_scale(None, None, (5119, 2880)), 2)

    def test_invalid_resolution_with_no_other_info_is_fallback(self):
        decision = device_scale(None, None, "3840x2160")
        self.assertEqual(decision, 1)
        self.assertEqual(decision.source, SOURCE_FALLBACK)
        self.assertTrue(decision.log_required)


class Level4NoInfoTest(unittest.TestCase):
    """④ 都没有 → 1x，并返回「必须记日志」的信号（不静默）。"""

    def test_no_information_at_all(self):
        decision = device_scale(None, None, None)
        self.assertEqual(decision, 1)
        self.assertEqual(decision.source, SOURCE_FALLBACK)
        self.assertTrue(decision.log_required)
        self.assertTrue(decision.reason)
        self.assertTrue(decision.notes)

    def test_no_arguments_at_all_uses_defaults(self):
        decision = device_scale()
        self.assertEqual(decision, 1)
        self.assertTrue(decision.log_required)

    def test_log_required_is_false_for_every_well_formed_decision(self):
        for args in ((3, None, None), (None, UHD_156IN, UHD), (None, None, UHD)):
            with self.subTest(args=args):
                decision = device_scale(*args)
                self.assertFalse(
                    decision.log_required,
                    f"{args} 是有信息可用的判定，不该要求记日志：{decision.reason}",
                )


class DeviceScaleValueTest(unittest.TestCase):
    """返回值既是 int 又带判定依据 —— 这是「不静默」的载体。"""

    def test_is_an_int_that_prints_as_the_number(self):
        decision = device_scale(None, None, (3840, 2160))
        self.assertIsInstance(decision, int)
        self.assertEqual(str(decision), "2")
        self.assertEqual(f"{decision}", "2")
        self.assertEqual(decision + 1, 3)
        self.assertIn(decision, (1, 2, 3))
        for value, expected in ((3, "3"), (1, "1")):
            self.assertEqual(str(DeviceScale(value, source="test", reason="t")), expected)

    def test_carries_decision_context(self):
        decision = device_scale(None, None, None)
        self.assertIsInstance(decision.reason, str)
        self.assertIsInstance(decision.source, str)
        self.assertIsInstance(decision.notes, tuple)

    def test_rejects_out_of_contract_value(self):
        with self.assertRaises(ValueError):
            DeviceScale(4, source="test", reason="t")
        with self.assertRaises(ValueError):
            DeviceScale(0, source="test", reason="t")


if __name__ == "__main__":
    unittest.main()


class RecommendUiScaleTest(unittest.TestCase):
    """界面层缩放档位推荐（维护者 2026-10-04 给的目标：2560×1600 → 167%）。"""

    def test_维护者给的例子(self):
        self.assertEqual(recommend_ui_scale_percent(2560, 1600), 167)

    def test_常见分辨率(self):
        cases = {
            (1920, 1080): 100,
            (2560, 1440): 167,
            (3840, 2160): 200,
            (1366, 768): 100,
            (1024, 768): 100,
        }
        for (width, height), want in cases.items():
            with self.subTest(resolution=f"{width}x{height}"):
                self.assertEqual(recommend_ui_scale_percent(width, height), want)

    def test_拿不到宽度就落最保守的一档(self):
        for value in (None, 0, -1):
            self.assertEqual(recommend_ui_scale_percent(value), 100)

    def test_超宽屏按逻辑高度降一档(self):
        # 5120 宽按 1536 目标本该 200%，但 1440 高在 200% 下只剩 720 逻辑高 —— 降一档
        self.assertEqual(recommend_ui_scale_percent(5120, 1440), 167)
        # 同样是 5120 宽，高度够（2880 → 1440 逻辑高）就不降
        self.assertEqual(recommend_ui_scale_percent(5120, 2880), 200)
        # 已是最低档时不再降（1024×768 逻辑高 768 < 800，但没有更低的档）
        self.assertEqual(recommend_ui_scale_percent(1024, 768), 100)

    def test_只返回白名单里的档位(self):
        for width in range(800, 6000, 137):
            self.assertIn(recommend_ui_scale_percent(width, 1080), UI_SCALE_PERCENTS)
