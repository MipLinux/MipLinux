"""设备层缩放判定 —— 纯函数（V7 的纯函数侧）。

准据：
- `docs/work/tech/08-界面设计方向.md` §3.10（缩放与高分屏）
- `installer/frontend/qml/README.md` §2（`MiplLaunch.deviceScale` = 实际写进 `QT_SCALE_FACTOR` 的值）

四级判定次序（08 §3.10 的「目标值怎么算」行 + 维护者 2026-10-01 裁决）
--------------------------------------------------------------------
① 合成器给了 `scale > 1` → **以它为准**；
② 有物理尺寸 → 算 DPI：`≥288 → 3x`、`≥192 → 2x`（**只有 ≥192 才在此终局**）；
   若 `DPI < 192`，**不落 1x**，继续走 ③（见下「② 的下界」）；
③ 无物理尺寸（虚拟显示 / QEMU / EDID 缺失）**或** ② 的 DPI 低于 192 →
   按分辨率兜底：宽 `≥5120 → 3x`、`≥3200 → 2x`、否则 `1x`；
④ 以上都拿不到 → `1x`，**并必须记一条日志（不静默）**。

注意 ① 的边界：Wayland 下 `wl_output::scale` 默认就是 `1`，**`scale == 1` 不是信息，不短路**，
必须继续走 ②③ —— 这正是「高分屏不得停在 1x」那条硬要求在代码里的落点。

② 的下界（维护者裁决 2026-10-01）
----------------------------------
08 §3.10 原文把 ③ 的条件写成「拿不到物理尺寸」。按字面，163 DPI 的 27" 4K 会停在 1x ——
那恰好是「高分屏不能用 1x，否则画面过小」要避免的结果。维护者裁决：
**② 只在 `DPI ≥ 192` 时终局；`DPI < 192` 时不在此落 1x，继续走 ③ 分辨率兜底**
（此时 resolution 必然可得 —— 算 DPI 就用了它）。`docs/work/tech/08-界面设计方向.md` §3.10
由维护者/Lead 补记这条口径；本模块与 `README.md` 与之同步。

「不静默」怎么保证
------------------
返回值是 :class:`DeviceScale` —— 一个 `int` 子类。它

- 就等于 `1` / `2` / `3`：`print(decision)` 打印 `2`，`decision == 2` 为真，
  可直接塞进 `QT_SCALE_FACTOR`，**不需要调用方 `.value` 解包**；
- 又带 ``log_required`` / ``source`` / ``reason`` / ``notes`` 四个属性，说明这条判定从哪来。

`log_required` 为真**只有两类情形**：(a) 四级次序走到 ④（什么信息都没有）；
(b) 输入不在契约内（合成器值 > 1 却被归一、`physical_size` / `resolution` 非法到不可解析）。
「② 因 DPI < 192 改走 ③」是**正常的确定路线**，不是异常：它写进 `reason` 与 `notes` 供排查，
但**不**要求调用方记日志 —— 别把「必须记日志」稀释成每台 27" 4K 都刷一条。

调用方（启动器，整合步）在 ``log_required`` 为真时**必须**写一条日志，内容至少含 ``reason``：
这是 §3.10 ④ 的硬要求，不是可选的调试输出。把标志放在返回值里，是为了让「拿不到任何信息」
这件事**不可能被静默忽略** —— 只要有人接了返回值，就必然看得到这个标志。


纪律
----
- 纯函数：不读环境变量、不读系统时钟、不产生副作用、不 import Qt / PySide6，只用标准库。
  真正写 `QT_SCALE_FACTOR`、真正打日志、`--scale=<n>` 手动覆盖，都是启动器的事（本任务不做）。
- 整数档 `1 / 2 / 3`：Wayland 的 `wl_output::scale` 是整数，不做 1.25 / 1.5（08 §3.10）。
"""

from __future__ import annotations

import math
from typing import Sequence

SCALE_MIN = 1
SCALE_MAX = 3

DPI_2X = 192
DPI_3X = 288

RES_WIDTH_2X = 3200
RES_WIDTH_3X = 5120

MM_PER_INCH = 25.4

SOURCE_COMPOSITOR = "compositor"
SOURCE_PHYSICAL_DPI = "physical-dpi"
SOURCE_RESOLUTION = "resolution"
SOURCE_FALLBACK = "fallback"


class DeviceScale(int):
    """判定的返回值：**是** `1` / `2` / `3` 本身，另外附带判定依据。

    用法::

        decision = device_scale(output_scale, physical_size, resolution)
        if decision.log_required:
            log.warning("device scale 落到 %sx：%s", int(decision), decision.reason)
        os.environ["QT_SCALE_FACTOR"] = str(int(decision))
    """

    # 注意：`int` 是变长类型，非空 `__slots__` 不被支持（Python 3.11+ 直接报 TypeError），
    # 所以判定依据放在实例 `__dict__` 里。对象很小，这点开销无所谓。
    def __new__(cls, value, *, source, reason, log_required=False, notes=()):
        if value not in (1, 2, 3):
            raise ValueError(f"设备层缩放只能是 1/2/3，实际 {value!r}")
        obj = super().__new__(cls, value)
        obj.source = source
        obj.reason = reason
        obj.log_required = bool(log_required)
        obj.notes = tuple(notes)
        return obj

    def __str__(self):  # print(decision) → "2"，必须覆盖：int.__str__ 会走 __repr__
        return str(int(self))

    def __repr__(self):
        return (
            f"DeviceScale({int(self)}, source={self.source!r}, "
            f"log_required={self.log_required!r})"
        )


def _as_pair(value):
    """把 `value` 归一成 (正数, 正数)；不可用则返回 None（不抛异常，交给调用方记 note）。"""
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    if len(value) != 2:
        return None
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        if not math.isfinite(item) or item <= 0:
            return None
        out.append(float(item))
    return (out[0], out[1])


def physical_dpi(physical_size, resolution):
    """按对角线算物理 DPI：`√(w_px²+h_px²) / (√(w_mm²+h_mm²)/25.4)`。

    08 §3.10 只写了「按 DPI：≥288 → 3x，≥192 → 2x」，没写用横向还是对角。
    这里取**对角线**（与显示器「PPI」口径一致，且不受宽高比误差的单轴放大影响）。

    Args:
        physical_size: `(宽 mm, 高 mm)`，两者都 > 0。
        resolution: `(宽 px, 高 px)`，两者都 > 0。

    Returns:
        float DPI；任一参数缺失 / 非法时返回 `None`（**不猜、不兜底**）。
    """
    size = _as_pair(physical_size)
    res = _as_pair(resolution)
    if size is None or res is None:
        return None
    diag_px = math.hypot(res[0], res[1])
    diag_mm = math.hypot(size[0], size[1])
    return diag_px / (diag_mm / MM_PER_INCH)


def device_scale(output_scale=None, physical_size=None, resolution=None) -> DeviceScale:
    """按 08 §3.10 的四级次序算出设备层缩放。

    ② 只在 `DPI ≥ 192` 时终局；`DPI < 192` 时继续走 ③ 分辨率兜底（维护者裁决 2026-10-01）——
    所以 `source` 也可能是 ``"resolution"``，即使 `physical_size` 给全了。

    Args:
        output_scale: 合成器给的 `wl_output::scale`（数字）。`None` = 拿不到；
            `<= 1` 视为「没有缩放信息」，**不短路**，继续往下判。
        physical_size: 物理尺寸 `(宽 mm, 高 mm)`。`None` / 非法 = 拿不到（虚拟显示、QEMU、EDID 缺失）。
        resolution: 分辨率 `(宽 px, 高 px)`。`None` / 非法 = 拿不到。算 DPI 也用它，
            所以 `physical_size` 有效而它为 `None` 时算不出 DPI，会落到 ④。

    Returns:
        :class:`DeviceScale`（`int` 子类，值 ∈ {1, 2, 3}）。``log_required`` 为真时
        调用方**必须**记日志。
    """
    notes = []
    must_log = False

    # ---- ① 合成器：只有 > 1 才算「给了意见」 ----
    if output_scale is not None:
        if isinstance(output_scale, bool) or not isinstance(output_scale, (int, float)):
            raise TypeError(f"output_scale 必须是数字或 None，实际拿到 {output_scale!r}")
        if not math.isfinite(output_scale):
            raise ValueError(f"output_scale 必须是有限数，实际拿到 {output_scale!r}")
        if output_scale > 1:
            rounded = int(round(float(output_scale)))
            clamped = min(max(rounded, SCALE_MIN), SCALE_MAX)
            if clamped != output_scale:
                must_log = True
                notes.append(
                    f"合成器 scale={output_scale!r} 不在 1/2/3 契约内，已归一为 {clamped}x"
                    "（Wayland 的 wl_output::scale 是整数，这里本不该出现小数或 >3）"
                )
            return DeviceScale(
                clamped,
                source=SOURCE_COMPOSITOR,
                reason=f"合成器给了 scale={output_scale}（> 1 以它为准）",
                log_required=must_log,
                notes=notes,
            )
        if output_scale < 1:
            must_log = True
            notes.append(
                f"合成器 scale={output_scale!r} < 1，不是合法档位，按「无缩放信息」处理并继续判定"
            )

    # ---- ② 物理尺寸 → DPI（只有 DPI ≥ 192 才在此终局） ----
    phys_dpi = None
    if physical_size is not None:
        phys_dpi = physical_dpi(physical_size, resolution)
        if phys_dpi is None:
            must_log = True
            notes.append(
                "给了 physical_size 但算不出 DPI（需要同时给出有效的 physical_size 与 resolution），"
                "按「拿不到物理尺寸」继续判定"
            )
        elif phys_dpi >= DPI_3X:
            return DeviceScale(
                3,
                source=SOURCE_PHYSICAL_DPI,
                reason=(
                    f"物理尺寸 DPI={phys_dpi:.1f}（对角线口径）≥ {DPI_3X} → 3x（② 终局）"
                ),
                log_required=must_log,
                notes=notes,
            )
        elif phys_dpi >= DPI_2X:
            return DeviceScale(
                2,
                source=SOURCE_PHYSICAL_DPI,
                reason=(
                    f"物理尺寸 DPI={phys_dpi:.1f}（对角线口径）≥ {DPI_2X} → 2x（② 终局）"
                ),
                log_required=must_log,
                notes=notes,
            )
        else:
            # 维护者裁决 2026-10-01：② 不在此落 1x，继续走 ③（正常路线，不要求记日志）。
            notes.append(
                f"物理尺寸 DPI={phys_dpi:.1f}（对角线口径）< {DPI_2X}：按维护者裁决 ② 不在此终局，"
                "继续走 ③ 分辨率兜底（高分屏不得停在 1x）"
            )

    # ---- ③ 分辨率兜底（虚拟显示 / QEMU / EDID 缺失，或 ② 的 DPI 低于 192） ----
    if resolution is not None:
        res = _as_pair(resolution)
        if res is None:
            must_log = True
            notes.append(f"resolution={resolution!r} 无法解析为 (宽 px, 高 px)，按「拿不到」处理")
        else:
            width = res[0]
            if width >= RES_WIDTH_3X:
                value = 3
            elif width >= RES_WIDTH_2X:
                value = 2
            else:
                value = 1
            if phys_dpi is not None:
                reason_lead = f"物理尺寸 DPI={phys_dpi:.1f} < {DPI_2X}，按维护者裁决改走分辨率兜底"
            else:
                reason_lead = "无物理尺寸，按分辨率兜底"
            return DeviceScale(
                value,
                source=SOURCE_RESOLUTION,
                reason=(
                    f"{reason_lead}：宽 {width:g}px → {value}x"
                    f"（阈值：≥{RES_WIDTH_3X}→3x，≥{RES_WIDTH_2X}→2x，否则 1x）"
                ),
                log_required=must_log,
                notes=notes,
            )

    # ---- ④ 都没有：1x，必须记日志 ----
    notes.append("合成器未给 >1 的 scale，物理尺寸与分辨率都拿不到")
    return DeviceScale(
        1,
        source=SOURCE_FALLBACK,
        reason="没有任何可用的缩放信息（08 §3.10 ④）→ 落到 1x，调用方必须记一条日志",
        log_required=True,
        notes=notes,
    )


__all__ = [
    "DeviceScale",
    "device_scale",
    "physical_dpi",
    "SCALE_MIN",
    "SCALE_MAX",
    "DPI_2X",
    "DPI_3X",
    "RES_WIDTH_2X",
    "RES_WIDTH_3X",
    "SOURCE_COMPOSITOR",
    "SOURCE_PHYSICAL_DPI",
    "SOURCE_RESOLUTION",
    "SOURCE_FALLBACK",
]
