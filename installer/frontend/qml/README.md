# Mipl QML · 接口冻结 v1（阶段 0）

> **状态**：冻结于 2026-10-01。依据 [08-界面设计方向.md](../../../docs/work/tech/08-界面设计方向.md) §3 / §6。
> **本目录的界面代码一条都没实测**。唯一有实测支撑的是色板数据：`tokens/color.json` 的 35×2 个值
> 由官方算法在本机重生成，与 08 附录 A.2 逐项相等（2026-10-01）。其余一律记「未实测 / 仅静态检查」。

这份文件是阶段 0 的**唯一接口准据**：三条并行线（tokens / theme / components）各自只写自己的目录，
**跨目录的名字以本文件为准**。改本文件 = 改接口，要先过维护者。

---

## 0. 路径与所有权

| 路径 | 归谁 | 内容 |
|---|---|---|
| `installer/frontend/qml/README.md` | 接口（本文件） | 冻结的 token 名、注入契约、纪律 |
| `installer/frontend/qml/Mipl/qmldir` | tokens 线 | 模块清单 |
| `installer/frontend/qml/Mipl/tokens/**` | tokens 线 | 六个 QML 单例 + `color.json` + 断言脚本 |
| `installer/frontend/qml/Mipl/theme/**` | theme 线 | 主题解析与设备缩放的**纯函数**（Python）+ 单测 |
| `installer/frontend/qml/Mipl/components/**` | components 线 | 08 §4.1 的 17 项 + 示例页 |
| `installer/frontend/mipl-installer`（尚未创建） | **本阶段不做** | 启动器接线留到整合步 |

`Mipl/` 这一层是 QML 模块目录 —— `import Mipl 1.0` 要求模块目录与 URI 同名。
启动器把 `installer/frontend/qml` 加进 QML import path。

## 1. 导入与模块

- URI `Mipl`，版本 `1.0`；消费方一律 `import Mipl 1.0`。
- 模块目录 `installer/frontend/qml/Mipl/`，清单 `Mipl/qmldir`；单例在 `qmldir` 里声明
  （`singleton MiplColor 1.0 tokens/MiplColor.qml`）。
- **禁止**跨目录相对导入（`import "../tokens"`）取 token —— 只走 `import Mipl 1.0`。
- **回退方案**：若「qmldir 指向子目录」跑不通，改由启动器
  `qmlRegisterSingletonType(QUrl.fromLocalFile(...), "Mipl", 1, 0, "<名>")` 显式注册。
  回退必须留下实测记录，且**不许**改本文件的路径与名字。

> ✅ **主方案本机已验证（2026-10-01）**，回退方案**不需要**：spike 里 `Mipl/qmldir` 写
> `singleton MiplColor 1.0 tokens/MiplColor.qml` 与 `MiplCard 1.0 components/MiplCard.qml`，
> PySide6 6.11.2 用 `engine.addImportPath("<qml 根>")` + `import Mipl 1.0` 读出
> `MiplColor.primary = #adc6ff`、`MiplColor.surface = #111318`，`component.status = Ready`。
> 反证也在：去掉 `-I` 后 `qml6` 报 `Did not load any objects`（退出码 2）。
> 注意 `qml6` 的 `console.log` 在本机不出现在输出里 —— **别拿「没打印」当通过**，要用 Python 读回值。

## 2. 启动注入契约（首帧之前）

启动器在**创建窗口之前**算好主题与设备缩放，注册单例实例（`engine.load()` 之前）：

```python
qmlRegisterSingletonInstance("Mipl", 1, 0, "MiplLaunch", launch)
```

| 属性 | 类型 | 含义 |
|---|---|---|
| `MiplLaunch.theme` | `str` | `"light"` / `"dark"` —— 启动瞬间解析出的主题（P5：首帧之前必须定） |
| `MiplLaunch.themeSource` | `str` | `"auto"` / `"manual"` —— 初值来自时间还是 `--theme` 覆盖 |
| `MiplLaunch.deviceScale` | `float` | 实际写进 `QT_SCALE_FACTOR` 的值（1 / 2 / 3） |

**运行期**：`auto` 下启动器每 30s 用同一纯函数重算并更新 `MiplLaunch.theme`；界面锁定后绑定不再理会它。
`MiplLaunch` 由 theme 线提供纯函数、由整合步接线 —— **本阶段不写启动器文件**。

## 3. token 单例（六个，全在 `Mipl/tokens/`）

命名：`MiplXxx.<camelCase>`。MD3 官方角色名是 kebab-case，落到 QML 一律转小驼峰
（`surface-container-high` → `MiplColor.surfaceContainerHigh`）。
**不做** `Mipl.color.*` 那层嵌套 —— 08 §3 里那行是示意，§6 定的是五个独立单例名。

### 3.1 `MiplColor` —— 35 个角色

- 属性 = `tokens/color.json` 的 35 个键（kebab → camel），亮 / 暗各一套值；值只来自 `color.json`。
- 每个属性是绑定：`readonly property color surface: MiplTheme.dark ? "#111318" : "#f9f9ff"`。
- `color.json` 是**快照与断言输入**，不是运行期输入 —— QML 里写字面值，运行期不读 JSON。

### 3.2 `MiplType` —— 15 档字形

- 每档一组：`MiplType.<role>.size / lineHeight / tracking / weight`；值类型 `MiplTypeScale.qml`。
- role（15）：`displayLarge displayMedium displaySmall headlineLarge headlineMedium headlineSmall titleLarge titleMedium titleSmall bodyLarge bodyMedium bodySmall labelLarge labelMedium labelSmall`
- 家族：`family`（`Noto Sans`）· `familyCjk`（`Noto Sans CJK SC`）· `familyMono`（`Noto Sans Mono`）。
- CJK：渲染中文串时 `tracking: 0`；常量 `MiplType.cjkTracking`。

### 3.3 `MiplShape`（7）

`none 0` · `extraSmall 4` · `small 8` · `medium 12` · `large 16` · `extraLarge 28` · `full 9999`（哨兵；组件要真胶囊 / 正圆时写 `height / 2`）。

### 3.4 `MiplSpace`（7）

`xs 4` · `s 8` · `m 12` · `l 16` · `xl 24` · `xxl 32` · `page 48`。

### 3.5 `MiplMotion`

- 时长（ms）：`short1 50 short2 100 short3 150 short4 200 medium1 250 medium2 300 medium3 350 medium4 400 long1 450 long2 500 long3 550 long4 600 extraLong1 700 extraLong2 800 extraLong3 900 extraLong4 1000`。
- 缓动（`(x1, y1, x2, y2)` 四元组）：`easingStandard` = `easingEmphasized` = `(0.2, 0, 0, 1)`；`easingStandardAccelerate (0.3, 0, 1, 1)`；`easingStandardDecelerate (0, 0, 0, 1)`；`easingEmphasizedAccelerate (0.3, 0, 0.8, 0.15)`；`easingEmphasizedDecelerate (0.05, 0.7, 0.1, 1)`；`easingLinear (0, 0, 1, 1)`。
- `motionScale`（real，默认 1；**0 = 关闭动效**）。时长 = 基准 × `motionScale`。
- **首帧零动效**：首屏不挂动画；进度条循环动效在第一帧之后启动。

### 3.6 `MiplScale` —— 界面层缩放

- `factor`（real，可写，默认 `1.0`）；`steps = [0.85, 1.0, 1.15, 1.3]`；`labels` 四档中文名 + 百分比。
- **纪律**：`MiplType` / `MiplShape` 的 `size`、`lineHeight`、间距、圆角、图标尺寸 = 基准值 × `MiplScale.factor`，
  **在单例内部乘一次**；组件绝不再乘，也**绝不**碰 `devicePixelRatio` / `Screen.devicePixelRatio`（双重缩放）。
- `MiplMotion` 的时长**不**乘 `factor`，只乘 `motionScale`。
- 版式断点只看屏幕**逻辑宽**，不受 `factor` 影响。

### 3.7 `MiplTheme`

- `dark`（readonly 绑定 `MiplLaunch.theme`）· `locked`（bool，可写）· `manualDark`（bool）· `source`（str）。
- 顶部 app bar 的主题按钮：`locked = true; manualDark = !dark`；tooltip 显示「跟随时间」/「已手动锁定为暗色」。
- **不做**「恢复自动」入口（08 §4.2）。

## 4. 语言边界

- QML：`tokens/**`、`components/**`。
- Python：`theme/**` 的纯函数与单测（`python3 -m unittest`，注入固定时钟，不依赖 Qt）。
- **红线**：`installer/backend/**` 不许出现 Qt / PySide6 import（[installer/AGENTS.md](../../AGENTS.md)）。
  本轮不许改 `installer/backend/**`、`installer/tests/**`、`profile/**`、任何 `AGENTS.md`。

## 5. 本阶段不做

08 §4.2 的全表（bottom sheet / side sheet / navigation rail / navigation drawer / FAB / carousel /
date picker / time picker / search bar / data table / slider / tabs / bottom app bar）·
主题三态菜单（恢复自动）· 高对比度方案 · 第三档版式 · `Mipl.color.*` 嵌套名 · 运行期读 JSON ·
启动器接线 · 写盘记忆。

## 6. 验证入口

| 判据 | 命令 | 现状 |
|---|---|---|
| 色板 = 08 附录 A.2 | `cd /tmp/mip-md3 && node gen.mjs '#2576E9'` 与 `tokens/color.json` 逐项比 | **本机已验**（2026-10-01 重生成，35×2 全等） |
| V1 token 一致 | `python3 Mipl/tokens/tools/check-tokens.py` | 未实测 |
| V2 对比度 ≥4.5 / ≥3 | `python3 Mipl/tokens/tools/check-contrast.py` | 08 附录 A.3 的 28 组**设计阶段已过**；脚本落地后未跑 |
| V6 主题解析 | `python3 -m unittest discover -s installer/frontend/qml/Mipl/theme` | 未实测 |
| 模块能加载 | `python3 <spike>/probe.py`（`addImportPath` + `import Mipl 1.0`） | **模块机制本机已验**（2026-10-01 spike）；组件与单例本身未实现 |
