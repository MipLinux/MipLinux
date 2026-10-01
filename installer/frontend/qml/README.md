# Mipl QML · 接口冻结 v1（阶段 0）

> **状态**：冻结于 2026-10-01。依据 [08-界面设计方向.md](../../../docs/work/tech/08-界面设计方向.md) §3 / §6。
> **已实测到哪一步**：色板、token 单例、theme 纯函数与组件都在**本机**跑过 —— 色板 35×2 与 08 附录 A.2 逐项相等；
> V1（335 项）/ V2（28 组）/ V6（51 条单测）全绿；18 个组件在 offscreen + PySide6 6.11.2 下加载 Ready。
> **仍未实测**：V3（键盘全流程）/ V4（首帧预算）/ V5（视觉基线）/ V7（真机缩放）/ V8（界面层四档），
> 以及真 ISO / cage 里的一切 —— **离屏不等于笼子**。组件级键盘行为有人离屏点过
> （`Return` / 小键盘 `Enter` / `Space` 都能触发 `clicked`），但**没有落成仓内脚本**，所以只当旁证、不当 V3。

这份文件是阶段 0 的**唯一接口准据**：三条并行线（tokens / theme / components）各自只写自己的目录，
**跨目录的名字以本文件为准**。改本文件 = 改接口，要先过维护者。

---

## 0. 路径与所有权

| 路径 | 归谁 | 内容 |
|---|---|---|
| `installer/frontend/qml/README.md` | 接口（本文件） | 冻结的 token 名、注入契约、纪律 |
| `installer/frontend/qml/Mipl/qmldir` | tokens 线 + 整合步 | 模块清单（组件的 18 行登记由整合步补） |
| `installer/frontend/qml/Mipl/tokens/**` | tokens 线 | 七个 QML 单例 + 一个值类型（`MiplTypeScale`）+ `color.json` + 断言脚本 |
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

> ✅ **主方案本机已验证（2026-10-01）**，回退方案**不需要**。取证方式可随时复跑、不依赖任何临时目录：
> 用 PySide6 6.11.2 建 `QQmlEngine` → `engine.addImportPath("installer/frontend/qml")` → 加载一个
> `import Mipl 1.0` 的探针，读回 `MiplColor.primary == "#adc6ff"`、`MiplColor.surface == "#111318"`、
> `component.status == Ready`。反证也在：不传 import path 时 `qml6` 报 `Did not load any objects`（退出码 2）。
> 注意 `qml6` 的 `console.log` 在本机不出现在输出里 —— **别拿「没打印」当通过**，要用 Python 读回值。
> （首次 spike 用的临时目录后来被别的工作覆盖了，所以上面改成「对最终产物复跑同口径探针」——
> 复核时发现「取证不能只留在 `/tmp`」。）

## 2. 启动注入契约（首帧之前）

启动器在**创建窗口之前**算好主题与设备缩放，注册单例实例（`engine.load()` 之前）：

```python
# PySide6 6.11：**第一个位置实参是类型对象**，不是 uri。
# （C++ 的模板形态是 qmlRegisterSingletonInstance<T>(uri, major, minor, name, obj)；
#  照那个顺序写 Python 会直接 TypeError —— 以本行为准，签名已在运行时核对过。）
qmlRegisterSingletonInstance(MiplLaunch, "Mipl", 1, 0, "MiplLaunch", launch)
```

| 属性 | 类型 | 含义 |
|---|---|---|
| `MiplLaunch.theme` | `str` | `"light"` / `"dark"` —— 启动瞬间解析出的主题（P5：首帧之前必须定） |
| `MiplLaunch.themeSource` | `str` | `"auto"` / `"manual"` —— 初值来自时间还是 `--theme` 覆盖 |
| `MiplLaunch.deviceScale` | `float` | 实际写进 `QT_SCALE_FACTOR` 的值（1 / 2 / 3） |

**运行期**：`auto` 下启动器每 30s 用同一纯函数重算并更新 `MiplLaunch.theme`；界面锁定后绑定不再理会它。

**设备层四级判定**（维护者 2026-10-01 裁决，实现见 `theme/device_scale.py`）：
① 合成器 `scale > 1` → 以它为准；② 有物理尺寸且 DPI `≥288 → 3x`、`≥192 → 2x`，**`DPI < 192` 继续走 ③**；
③ 按分辨率兜底：宽 `≥5120 → 3x`、`≥3200 → 2x`；④ 都没有 → `1x` **且必须记一条日志**（不静默）。
DPI 取**对角线**口径（08 §3.10 没指定横向还是对角）；`wl_output::scale == 1` 不算信息、**不短路**，
否则 27" 4K（163 DPI）会停在 1x —— 那是「高分屏不得停在 1x」要拦的事。

`MiplLaunch` 的纯函数由 theme 线提供，启动器文件由本阶段的「启动器接线」一并落地
（`installer/frontend/mipl-installer` 与 `mipl-kiosk`）。

## 3. token 单例（七个 + 一个值类型，全在 `Mipl/tokens/`）

命名：`MiplXxx.<camelCase>`。MD3 官方角色名是 kebab-case，落到 QML 一律转小驼峰
（`surface-container-high` → `MiplColor.surfaceContainerHigh`）。
**不做** `Mipl.color.*` 那层嵌套 —— 08 §3 里那行是示意；08 §6 点了五个名字
（`MiplColor` / `MiplType` / `MiplShape` / `MiplSpace` / `MiplMotion`），落地时按 §3.6 / §3.7 又加了
`MiplScale` 与 `MiplTheme`，所以 `Mipl/qmldir` 里一共 **7 个单例**，外带一个**值类型** `MiplTypeScale`（非单例）。

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

### 3.8 落地时踩到的 QML 行为（改这些文件前先读）

`Mipl/` 这一层有几处不直观、**静态检查抓不到**的行为，都是 2026-10-01 落地时实测出来的：

- **那 10 个 `on-*` 角色只能是 alias。** 同一对象里带初值的 `onXxx` 会被 QML 当成「信号 Xxx 的处理器」；
  同对象只要有同名的小写兄弟（`on-primary` 对 `primary`…），编译就报
  `Cannot assign a value to a signal (expecting a script to be run)`，**整个 `MiplColor` 类型不可用**。
  落地做法：把 on-* 放进一个只声明 on-* 的嵌套对象，再用 `readonly property alias onPrimary: …` 平铺 ——
  消费方 API 与冻结完全一致（名字 / 类型 / readonly / 响应主题）。
  **`qmllint` 对这条完全静默（退出码 0）**，只有真加载才暴露，所以改完 `MiplColor` 必须跑 §6 的加载探针。
- **`MiplTheme.qml` 必须自导入 `import Mipl 1.0`**，否则 `typeof MiplLaunch` 恒为 `"undefined"`、自动主题永远走兜底。
- **`MiplLaunch` 未注册时 `MiplTheme.dark` 回落 `true`（暗色）** —— 只影响 token-only 探针与单测；
  真启动器一定在 `engine.load()` 之前注册。
- **嵌套 holder 用 `property var`，不要 `property QtObject`**：Qt 6.11 下若用 `property QtObject child: QtObject {}`，
  **「先建引擎 → 再 `qmlRegisterSingletonInstance` → 再 load」这个顺序**会报假类型错
  `Cannot assign object of type "QtObject" to property of type "QObject*"`（实测：`register→engine` = Ready、
  `engine→register` = Error；用 `property var` 则两种顺序都 Ready）。启动器仍按「注册 → 建引擎 → load」最稳。
- **`MiplTypeScale` 是普通类型**（`qmldir` 里没有 `singleton`），组件才能写 `property MiplTypeScale x`。
- `MiplShape.none`（`0 * factor`）与 `full`（`9999 * factor`）也乘 `factor`，形状档位统一、不开例外。
- **动画时长只能用 `MiplMotion.<档>`，不要再乘 `motionScale`。** `MiplMotion.short2` 本身已是
  `100 * motionScale`，再乘一次就是 `基准 × motionScale²` —— 在 0 与 1 两个端点上看不出来，中间值全错。
  复核线第一轮就在 12 个组件里抓到 17 处这个写法（`motionScale=0.5` 时 25 而不是 50）。
- **`qmllint` 只是语法检查**：`MiplColor.noSuchRole`、`Button { noSuchProperty: 1 }` 它都判 exit 0，
  只有语法错才非 0。所以「qmllint 全绿」**不能**当语义证据 —— 语义靠 §6 的加载探针。
- **注册时机**：`qmlRegisterSingletonInstance(..., "Mipl", ...)` 必须在本进程**第一次编译任何 Mipl 类型之前**
  完成；否则后面所有 engine 解析 qmldir 里的复合类型都会失败，且报的是误导性错误。

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
| 色板 = 08 附录 A.2 | 离线复现见 08 A.4（**必须显式传种子**）；库内一致性由 V1 的 `check-tokens.py` 三方比对覆盖 | **已验**：`#2576E9` 生成的 70 个值与 A.2 逐项相等。⚠️ **别用 `/tmp/mip-md3/gen.mjs` 验 A.2** —— 它第 14 行是 `ranked[0]`、**忽略 argv**，会落到打分首选（`#3c93fb` / `#3d93fb` —— WSMeans 有 ±1 阶随机，见 08 A.1），于是 `on-surface/surface` 算出 14.38 而不是 14.41（复核线已独立复现这条差异的来源） |
| V1 token 一致 | `python3 installer/frontend/qml/Mipl/tokens/tools/check-tokens.py` | **本机已跑绿**（2026-10-01）：335 个比对项全一致 |
| V2 对比度 ≥4.5 / ≥3 | `python3 installer/frontend/qml/Mipl/tokens/tools/check-contrast.py` | **本机已跑绿**：28 组全过，与 A.3 两位小数一致（最大差 0.005） |
| V6 主题解析 | `python3 -m unittest discover -s installer/frontend/qml/Mipl/theme/tests -t installer/frontend/qml/Mipl/theme` | **本机已跑绿**：51 条，含 06:59 / 07:00 / 18:59 / 19:00 四个边界 |
| 组件层（离屏旁证） | `QT_QPA_PLATFORM=offscreen python3 installer/frontend/qml/Mipl/components/tools/probe-components.py` | **本机已跑绿**：101 项全过（19 个组件 Ready + `Return`/小键盘 `Enter`/`Space` 触发 + 动画时长 0.5/1.0/2.0 等于 token）。**旁证，不是 V3** |
| 模块能加载 | `python3 installer/frontend/qml/Mipl/tokens/tools/probe-tokens.py`（`addImportPath` + `import Mipl 1.0` 读回值） | 同口径探针**本机已验**（2026-10-01，对最终产物复跑）；见 §1 |
