"""多显示器镜像布局的纯函数测试（cage 默认并排 → kiosk 要镜像）。

跑法（任务验收命令）::

    python3 -m unittest discover -s installer/frontend/theme/tests \
        -t installer/frontend/theme
"""

import unittest

from display_layout import plan_mirror_commands


def output(name, enabled=True, width=1920, height=1080, refresh=60000, current=True):
    return {
        "name": name,
        "enabled": enabled,
        "modes": [{"width": width, "height": height, "refresh": refresh, "current": current}],
    }


class TestPlanMirrorCommands(unittest.TestCase):
    def test_single_output_needs_nothing(self):
        self.assertEqual(plan_mirror_commands([output("DP-1")]), [])

    def test_no_outputs_needs_nothing(self):
        self.assertEqual(plan_mirror_commands([]), [])

    def test_two_outputs_share_position_and_mode(self):
        commands = plan_mirror_commands([output("DP-1"), output("HDMI-A-1", width=2560, height=1440)])
        self.assertEqual(len(commands), 2)
        for argv, name in zip(commands, ("DP-1", "HDMI-A-1")):
            self.assertEqual(argv[0], "wlr-randr")
            self.assertEqual(argv[1:3], ["--output", name])
            self.assertEqual(argv[3:5], ["--pos", "0,0"])
            self.assertEqual(argv[5:7], ["--scale", "1"])
            # 模式取**主输出**（第一个点亮的）的当前模式：viewport 统一才互为镜像
            self.assertEqual(argv[7:], ["--mode", "1920x1080@60.000"])

    def test_disabled_outputs_are_ignored(self):
        commands = plan_mirror_commands([output("DP-1"), output("HDMI-A-1", enabled=False)])
        self.assertEqual(commands, [])

    def test_falls_back_to_first_mode_when_none_is_current(self):
        out = output("DP-1", current=False)
        commands = plan_mirror_commands([out, output("HDMI-A-1")])
        self.assertEqual(commands[0][-1], "1920x1080@60.000")

    def test_output_without_modes_is_not_mirrored(self):
        commands = plan_mirror_commands([{"name": "DP-1", "enabled": True, "modes": []}, output("HDMI-A-1")])
        self.assertEqual(commands, [])


if __name__ == "__main__":
    unittest.main()
