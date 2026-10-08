"""多显示器镜像布局的纯函数：`wlr-randr --json` 的解析结果 → 命令行序列。

cage（wlroots）默认把多个输出**并排**摆：kiosk 的全屏窗口只盖住其中一块，实机表现是
「只有一块屏有画面、其余黑屏」（实机教训）。kiosk 要的是镜像 —— 每块屏同一画面。
wlroots 的输出布局允许重叠：把所有输出摆到 (0,0)、用同一模式与缩放，它们就互为镜像。

本模块只算「该跑哪几条 wlr-randr」；执行与重试在启动器（`frontend/mipl-installer`）里。
纯函数、无副作用、可单测 —— 与 theme/ 目录的其余模块同一条纪律。
"""

from __future__ import annotations


def plan_mirror_commands(outputs: list[dict]) -> list[list[str]]:
    """把点亮的输出统一到 (0,0) + 主输出当前模式的命令行序列。

    只有一个（或零个）点亮的输出时返回空列表 —— 单屏没什么可镜像的，
    少跑一条命令就少一个会坏的东西。主输出取名单里第一个点亮的：
    kiosk 的全屏窗口首帧落在哪块由合成器决定，这里不猜、只统一viewport。
    """
    enabled = [out for out in outputs
               if isinstance(out, dict) and out.get("enabled") and out.get("name")]
    if len(enabled) < 2:
        return []

    modes = enabled[0].get("modes") or []
    current = next((m for m in modes if isinstance(m, dict) and m.get("current")), None)
    if current is None and modes:
        current = modes[0]
    if not isinstance(current, dict) or not current.get("width") or not current.get("height"):
        return []
    spec = f"{current['width']}x{current['height']}"
    refresh = current.get("refresh")
    if refresh:
        # wlr-randr 的 refresh 是 mHz；--mode 要 Hz（三位小数够对齐刷新率了）
        spec += f"@{refresh / 1000:.3f}"

    return [
        ["wlr-randr", "--output", str(out["name"]), "--pos", "0,0", "--scale", "1", "--mode", spec]
        for out in enabled
    ]
