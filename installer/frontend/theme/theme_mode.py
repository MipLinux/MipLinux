"""主题解析（亮 / 暗）—— 纯函数，时钟由调用方注入。

准据：
- `docs/work/tech/08-界面设计方向.md` §3.9（主题模式：亮 / 暗 / 跟随时间）
- `installer/frontend/qml/README.md` §2（`MiplLaunch.theme` 是 `str`）与 §3.7（`MiplTheme`）

纪律
----
1. **本模块不读系统时钟。** `now` 一律由调用方传入（`datetime.datetime` 或 `datetime.time`）。
   函数体内没有 `datetime.now()` / `time.time()` / `date.today()` ——
   否则「跨过 19:00 自动切换」这件事根本没法用固定时钟断言，V6 也就无从谈起。
2. 返回值是 `"light"` / `"dark"` 字符串，与 `MiplLaunch.theme`（README §2，`str`）同型。
3. 只依赖 Python 标准库，**不 import Qt / PySide6**。
4. 本模块只做「给定时刻与模式 → 用哪套色板」这一件事：不碰界面、不写盘、不注册单例。
   首帧之前怎么调用、30s 定时器怎么摆，是整合步（启动器）的事，见 README §2。
"""

from __future__ import annotations

THEME_LIGHT = "light"
THEME_DARK = "dark"

SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"

SOURCES = (SOURCE_AUTO, SOURCE_MANUAL)

#: 自动规则：本地时间 [07:00, 19:00) → 亮色；[19:00, 07:00) 次日 → 暗色（08 §3.9）。
LIGHT_START_HOUR = 7
DARK_START_HOUR = 19


def _validate_now(now):
    """取出 `now` 的小时数；拿不到就报错，绝不退化成「读系统时钟」。"""
    hour = getattr(now, "hour", None)
    if not isinstance(hour, int) or isinstance(hour, bool) or not 0 <= hour <= 23:
        raise TypeError(
            "now 必须是 datetime.datetime 或 datetime.time（需有整数 .hour），"
            f"实际拿到 {now!r}。本模块不读系统时钟，请由调用方注入。"
        )
    return hour


def resolve_theme(now, source=SOURCE_AUTO, manual_dark=False):
    """解析当前该用哪套色板。

    Args:
        now: 注入的本地时间，`datetime.datetime` 或 `datetime.time`（只要有整数 `.hour`）。
            `source == "manual"` 时它不参与判定，但**仍会被校验** —— 免得调用方把参数顺序搞错。
        source: `"auto"`（跟随时间）或 `"manual"`（会话内已锁定）。其它值报 `ValueError`。
        manual_dark: `source == "manual"` 时以它为准：`True` → 暗色，`False` → 亮色。
            `source == "auto"` 时忽略。

    Returns:
        `"light"` 或 `"dark"`。

    Raises:
        TypeError: `now` 没有可用的整数 `.hour`。
        ValueError: `source` 不是 `"auto"` / `"manual"`。
    """
    hour = _validate_now(now)

    if source not in SOURCES:
        raise ValueError(f"source 必须是 {SOURCES} 之一，实际拿到 {source!r}")

    if source == SOURCE_MANUAL:
        # 手动锁定：只认 manual_dark，不再随时钟变（08 §3.9「手动」行）。
        return THEME_DARK if manual_dark else THEME_LIGHT

    return THEME_LIGHT if LIGHT_START_HOUR <= hour < DARK_START_HOUR else THEME_DARK
