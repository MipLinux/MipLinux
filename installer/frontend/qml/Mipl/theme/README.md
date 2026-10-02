# theme/ —— 主题解析与设备缩放（纯函数）

本目录是 `qml/README.md` §0 里 **theme 线**的实现：只放**不依赖 Qt** 的 Python 纯函数与单测。
接口名以 [../../README.md](../../README.md) §2 / §3.7 为准；本文件只讲怎么用与判定口径，**不是接口准据**。

## 两个模块

| 模块 | 函数 | 返回值 |
|---|---|---|
| `theme_mode.py` | `resolve_theme(now, source="auto", manual_dark=False)` | `"light"` / `"dark"`（与 `MiplLaunch.theme` 同型） |
| `device_scale.py` | `device_scale(output_scale=None, physical_size=None, resolution=None)` | `DeviceScale`（`int` 子类，值 ∈ {1,2,3}） |

- `now` **由调用方注入**（`datetime.datetime` 或 `datetime.time`）。函数体内没有 `datetime.now()` /
  `time.time()` —— 本模块不读系统时钟。传给 `manual` 模式也照样校验，参数顺序写错会直接报错。
- `physical_size` = `(宽 mm, 高 mm)`，`resolution` = `(宽 px, 高 px)`。拿不到就传 `None`，
  **不要编一个值** —— 「拿不到」本身是要被上报的状态。

## `device_scale` 的返回值怎么用

`DeviceScale` 既是那个整数，又带判定依据。启动器（整合步）应当这样接：

```python
decision = device_scale(output_scale, physical_size, resolution)
if decision.log_required:                      # 08 §3.10 ④ 的硬要求：必须记日志
    log.warning("device scale 落到 %sx：%s", int(decision), decision.reason)
os.environ["QT_SCALE_FACTOR"] = str(int(decision))
```

`print(decision)` 打印 `2`，`decision == 2` 为真，可直接写进 `QT_SCALE_FACTOR`。
`log_required` 为真只有两类情形：**四级次序走到 ④（什么信息都没有）**，
或者**输入的合成器值 / 物理尺寸不在契约内被归一**（`notes` 里有原委）。
「拿不到任何信息」因此不可能被静默忽略 —— 只要有人接了返回值，就必然看得到这个标志。

判定次序（维护者 2026-10-01 裁决版）：① 合成器 `scale > 1` 优先；② 物理尺寸 → 对角线 DPI
`≥288→3x`、`≥192→2x`（DPI 用 `√(w_px²+h_px²) / (√(w_mm²+h_mm²)/25.4)`，文档未指定口径，此处取对角线）；
③ **无物理尺寸，或 ② 的 DPI < 192** → 分辨率兜底 `≥5120→3x`、`≥3200→2x`、否则 1x；
④ 都没有 → 1x + 记日志（`log_required=True`）。
**注意 `scale == 1` 不短路**（Wayland 没配置缩放时也报 1），必须继续走 ②③。

> 口径留痕（维护者裁决 2026-10-01）：08 §3.10 原文把 ③ 的适用条件写成「**拿不到**物理尺寸」，
> 按字面 163 DPI 的 27" 4K 会停在 1x —— 那正是「高分屏不能用 1x，否则画面过小」要避免的结果。
> 裁决：**② 只在 `DPI ≥ 192` 时终局；`DPI < 192` 时不落 1x，继续走 ③ 分辨率兜底**
> （此时 `resolution` 必然可得，算 DPI 就用了它）。`docs/` 里 §3.10 的文字由 Lead/维护者补记。
>
> 「② 因 DPI < 192 改走 ③」是**正常的确定路线**，不是异常 —— `reason`/`notes` 会写明，
> 但 `log_required` 仍为 `False`（`log_required` 只留给 ④「什么信息都没有」与非法输入被归一两类）。

**注意 `resolution` 缺失时 ② 算不出 DPI**（`physical_size` 单独给没用）→ 直接落 ④：
1x 且 `log_required=True`。

本目录**不做**：写 `QT_SCALE_FACTOR`、打日志、`--scale=<n>` 手动覆盖、注册 `MiplLaunch`、30s 定时器 ——
全是启动器接线（整合步）的事。

## 怎么跑

```bash
python3 -m unittest discover -s installer/frontend/qml/Mipl/theme/tests \
    -t installer/frontend/qml/Mipl/theme
# 等价写法（qml/README.md §6 的 V6 入口）：
python3 -m unittest discover -s installer/frontend/qml/Mipl/theme
```

## 现状

- 51 条单测本机全过（2026-10-01，`python3` 3.14.7）—— 纯函数层**已实测**。
- 「直接调用 `device_scale(None, None, (3840,2160))` 打印 2」**已实测**。
- 但**界面上真实的高分屏观感、`QT_SCALE_FACTOR` 是否生效（V7）、首帧主题是否正确**：
  **未实测** —— 这些要等启动器接线与真机 / QEMU 里的 cage 会话。
