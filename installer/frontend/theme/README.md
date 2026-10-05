# theme/ —— 纯函数：主题与缩放

**这里没有任何界面框架依赖**（不 import Qt、不 import Node、不碰 DOM），所以：
- 启动器（`../mipl-installer`，Python）用它算**首帧**的主题与界面缩放；
- 单测可以在宿主机上直接跑，不需要 Live、不需要 Electron。

| 文件 | 对外函数 | 返回 |
|---|---|---|
| `theme_mode.py` | `resolve_theme(now, source, manual_dark=False)` | `"light"` / `"dark"` |
| `device_scale.py` | `recommend_ui_scale_percent(width, height)` | `100` / `167` / `200` |

## 口径（改之前先读）

- **主题默认 auto**：07:00–18:59 亮、其余暗；用户可以在顶栏锁定亮或暗（锁了就不再跟时间走）。
  渲染层的 30s 重算是 `renderer/js/theme.js` 的事，本目录只回答「某个时刻该是什么主题」。
- **缩放只有一层**（维护者 2026-10-04）：`recommend_ui_scale_percent` 给的是**界面层**档位，
  判据是「逻辑宽度落在 1536 附近」（2560×1600 → 167%、3840×2160 → 200%、1920×1080 → 100%），
  另有逻辑高度兜底（`高 / 档位 < 800` 时降一档，治 5120×1440 这类超宽矮屏）。
  设备层 `device_scale()`（1x/2x/3x）**不再单独生效** —— 两层相乘会把 4K 屏推到 4x；
  它只作为历史判定与日志依据保留。
- 时间一律由调用方注入（`now`），**本目录不读系统时钟** —— 否则「跨过 19:00 自动切换」没法用固定时钟断言。

## 不做

写 `QT_SCALE_FACTOR` / `--force-device-scale-factor`、打日志、解析命令行、跑定时器 ——
那些是启动器（`../mipl-installer`）与渲染层的事。

## 怎么跑

```bash
python3 -m unittest discover -s installer/frontend/theme/tests -t installer/frontend/theme
```
