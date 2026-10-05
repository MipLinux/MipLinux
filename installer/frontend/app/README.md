# 安装器前端（Electron）· 接口冻结

> 状态：**2026-10-05 冻结**（随技术栈由 Qt Quick/QML 改为 Electron；实机反馈七轮已收敛）。
> **2026-10-06 增补 §7 后端耦合层**（Issue #97：12 页从 Mock 改成吃真后端）。
> 视觉准据是 [tech/10](../../../docs/work/tech/10-安装器界面视觉方向.md)；文案准据是
> [tech/09](../../../docs/work/tech/09-安装器界面文案.md)；技术栈见 [D14](../../../docs/knowledge/06-待定事项.md)（P6）。
> 改本文件里冻结的**名字与结构** = 改接口，要先过维护者。

## 0. 谁负责什么

| 路径 | 内容 |
|---|---|
| `main.js` / `preload.js` | kiosk 窗口、`mipl://` 私有协议、启动参数注入、出口封死、**后端通道**（`child_process` 拉起 `python3 -m mipl_installer`）。**不实现安装逻辑** |
| `renderer/index.html` | 唯一的 HTML 入口（CSP 只允许本地资源） |
| `renderer/css/tokens.css` | 设计 token（双主题、字阶、圆角、动效）；`palette.css` 是生成物 |
| `renderer/css/{base,components,pages}.css` | 外壳版式 / 组件 / 页面编排 |
| `renderer/js/app.js` | 外壳：顶栏（语言 / 主题菜单 / 缩放菜单）、步骤轨道、动作区、页面生命周期、对话框 |
| `renderer/js/{setup,steps}.js` | 状态机 / 步骤表 |
| `renderer/js/{backend,mock}.js` | 候选数据：**真后端适配 / 离屏自检替身**。两者同形，页面只读 `ctx.backend` |
| `renderer/js/keymap-rows.js` | 键位图的主键区排布与键帽标签（纯函数，不碰 DOM） |
| `renderer/js/pages/*.js` | 12 个页面，一个页面一个文件 |
| `renderer/js/{i18n,tz-names}.js` | 文案与运行时语言 / 时区显示名 |
| `renderer/js/{motion,theme,scale,dom,components,icons}.js` | 动效、主题、缩放、DOM 帮助函数、组件、图标 |
| `renderer/i18n/*.json` | 生成物（`tools/i18n.py`），**不许手改** |
| `design/color.json` · `vendor/**` · `renderer/assets/logo/**` | 色板快照 · vendored 第三方资源 · 品牌位图 |
| `tools/*` | 生成器与守卫：i18n / tokens / icons / 对比度 / 探针 |

## 1. 启动注入（首帧之前）

启动器（`../mipl-installer`）算好三件事并通过命令行传给 `main.js`，`main.js` 再经
`webPreferences.additionalArguments` 交给 `preload.js`，渲染层只读 `window.mipl.config`：

| 键 | 取值 | 谁定的 |
|---|---|---|
| `theme` | `light` / `dark` | 启动器（**默认 light**；`auto` 才按本地时间） |
| `themeSource` | `light` / `dark` / `auto` | 启动器（**默认 auto**：07:00–18:59 亮；渲染层 30s 重算） |
| `lang` | `zh_CN` / `en_US` | 启动器 `--lang` |
| `uiScale` | `0` = 自动档但没推荐值，否则 100/167/200 | **界面层**缩放档位（启动器按分辨率推荐；自动档读它） |
| `renderer` | `gpu` / `software` | 启动器的 GPU 探测结果；`software` 时渲染层走低配模式（关掉极光/噪点/大模糊） |
| `probe` | `true` 时渲染层挂出 `window.__mipl` | 只在 `MIPL_PROBE=1` 时 |

`mipl://app/...` 是主进程注册的私有协议（根目录 = `app/`），静态端出 `renderer/`、`vendor/`、`design/`。
**不用 `file://`** —— 那样 ES module 与 `fetch()` 都会被 Chromium 拦掉。

## 2. 页面契约（每个 `pages/*.js` 都必须满足）

```js
export default {
  id: 'disk',                      // 必须与文件名、步骤表一致
  render(ctx) { /* 返回一个 DOM 节点 */ },
  isComplete(ctx) { return true; },        // 「下一步」是否放行
  blockedReason(ctx) { return ''; },       // 不放行时给用户看的原因（已翻译串）
  primaryLabel(ctx) { return ''; },        // '' = 用通用「下一步」
  primaryError: false,                     // true → 危险动作（danger 变体；只有擦除确认是 true）
  onPrimary(ctx) {},                       // 可选：主动作的自定义行为（默认 = 下一步）
  onLeave(ctx) {},                         // 可选：离开页面时收尾（进度页靠它停定时器）
  wantsWifiScan: false,                    // 可选：首帧后自动扫一次 Wi-Fi
}
```

- 页面**只渲染与校验**：不自己导航、不自己取数据、不读系统时钟。
- 状态一律写 `ctx.setup`（`setup.set(key, value)`），候选数据一律读 `ctx.backend`
  （**数据**；怎么问后端见 §7 —— `window.mipl.backend` 是**通道**，两者别混）。
- 文案一律 `ctx.t('key')`，**键必须存在于 `renderer/i18n/*.json`**（Node 单测会拦）。
- 页面内小状态变化用 `ctx.refresh()`（只刷动作区与轨道，不重画页面 → 不丢输入焦点）；
  整体重画才用 `ctx.rerender()`。
- **校验规则不许在页面里再写一份**：主机名那条原来是 `setup.js` 里的正则，
  现在改成问后端（§7）。判据只有一处，页面只缓存结论。

## 3. 步骤表

| 模式 | 步数 | 顺序 |
|---|---|---|
| 普通 | 8 | `welcome` `network` `disk` `account` `summary` `confirm` `progress` `finish` |
| 高级 | 12 | `welcome` `locale` `keymap` `timezone` `network` `disk` `account` `hostname` `summary` `confirm` `progress` `finish` |

步骤表在 `steps.js`，页面注册表在 `pages/index.js`；**两边必须一一对应**（单测会拦）。
「高级安装」开关在欢迎页，切换即时生效且停在当前页面。

## 4. i18n

- 唯一源：`docs/work/tech/09-安装器界面文案.md`（104 条界面文案 + 附 A 34 条时区名）。
- 生成物：`renderer/i18n/{zh_CN,en_US}.json`，由 `tools/i18n.py --write` 生成、`--check` 守卫。
- 时区显示名走 `timezone.name.<IANA>` 键；`tz-names.js` 只做**去重与拼装**（不撰写名字、不按日期算夏令时）。
- 顶栏「中 / EN」切换语言：重渲染即可，**不重启进程**。

## 5. 设计 token 与视觉

- 色板：`design/color.json`（35 角色 × 2 模式）→ `renderer/css/palette.css`（`tools/gen-tokens.py` 生成）。
- 设计 token：`renderer/css/tokens.css` 手写；**圆角只用五档**、动效只用四档时长、两条缓动。
- 图标：只用 vendored Phosphor（`vendor/icons/` → `renderer/js/icons.js`），不混家族、不手画路径。
- 动效：`motion.js` 包住 anime.js；只动 `transform` / `opacity`；`prefers-reduced-motion` 下不做位移。

## 5.1 版式与滚动的三条硬规则（实机定的，别改回去）

1. **一个 `--gutter` 管所有留白**：窗口四周、行列间距、面板内边距、动作区分隔线两侧 ——
   上下与左右必须同值。
2. **滚动的应该是列表，不是页面**：长列表页用 `panel({ fill: true })`，链条
   `panel--fill → .panel__core → .list-wrap → .list` 每一环都要 `flex: 1; min-height: 0`；
   页头、搜索框、扫描按钮、动作区固定不动。
3. **滚动渐隐按位置生效**：`dom.js: attachScrollFade()` 打 `data-scroll-fade`；
   不用滚的列表一律 `none`（固定遮罩会啃掉最后一项）。挂载点：可搜索列表、Wi-Fi 列表、
   磁盘卡列表、步骤轨道。

## 6. 验收怎么跑（都不需要 root / Live）

```bash
node --test "installer/frontend/app/tests/*.test.mjs"                     # 单测（含后端适配层与真键位对账）
python3 installer/frontend/app/tools/i18n.py --check                      # 文案 137 键
python3 installer/frontend/app/tools/gen-tokens.py --check                # 色板生成物
python3 installer/frontend/app/tools/gen-icons.py --check                 # 图标生成物
python3 installer/frontend/app/tools/check-tokens.py                      # 色板三方 + token 结构
python3 installer/frontend/app/tools/check-contrast.py                    # 对比度 46 组
python3 -m unittest discover -s installer/frontend/theme/tests -t installer/frontend/theme
MIPL_ELECTRON_BIN=<electron> node installer/frontend/app/tools/probe-render.js   # 离屏逐页渲染 + 断言 + 截图
```

`node --test` 里有一组会**真的起一次后端**（`--print-keymap` 跑 `us`/`de`/`fr`/`dvorak`）——
这是这一层唯一能防住「两侧各自绿、合起来错」的办法，所以它需要 `python3` 与 `kbd`
在位（都是安装器的硬依赖，缺了就该红）。

详细的实测结果与**未实测清单**见 [tech/11](../../../docs/work/tech/11-安装器前端实测.md)。

**口径：以上全是离屏旁证。** 真 ISO / `cage` 里的 V3（键盘全流程）、V5（视觉基线）、V7 / V8（缩放）
仍未实测 —— 要 `mipl build` + `qemu`，且需要 root。

## 7. 后端耦合层（Issue #97）

界面**不实现安装逻辑**，也不自己拼命令行。它只知道几个**出口名**，翻成命令行是主进程的事 ——
所以「界面上多一个出口」= 在 `main.js` 的 `QUERY_ARGV` 里加一行。

```
渲染层 backend.js ── window.mipl.backend ──▶ preload.js ── IPC ──▶ main.js ── spawn ──▶ python3 -m mipl_installer
   （数据适配）            （唯一对外通道）                      （通道 + 命令行白名单）        （后端）
```

### 7.1 通道：`window.mipl.backend`

| 方法 | 形态 | 说明 |
|---|---|---|
| `query(name, options?, stdinText?)` | 一问一答 | 只读出口。回 `{ok:true, data}` 或 `{ok:false, error}`，**不 reject** |
| `start(plan, secrets)` | 一次 | 开始装。回 `{ok}`；进度走 `onEvent`。同一时刻只允许一次 |
| `cancel()` | 一次 | 请求取消。真正生效在**阶段之间**，退出码 130 |
| `onEvent(listener)` | 订阅 | 每条后端记录；**回退订函数** |
| `onStderr(listener)` | 订阅 | 后端 stderr 的增量（失败排查用） |

**不 reject 是刻意的**：后端不在、输出坏了、参数不对，都是这一层正常要面对的结果，
渲染层看到 `ok:false` 就该显示「这个环境列不出名字」，而不是让整页崩掉。

### 7.2 出口名 → 命令行（白名单）

| 出口名 | 命令行 | 回什么 |
|---|---|---|
| `disks` | `--print-disks` | 候选盘（含不能装的，`usable` 标出来） |
| `network` | `--print-network` | `{online, wired, wired_interface, wired_ipv4, wifi_interface, wifi_ssid}` |
| `wifi` | `--print-wifi [--rescan]` | `{wifi:[{ssid, signal(0-100), secured}]}`，按信号降序 |
| `timezones` | `--print-timezones` | `{timezones:[{id, offset}]}`（偏移**不带** `UTC` 前缀） |
| `locales` | `--print-locales` | `{locales:[名字]}` |
| `keymaps` | `--print-keymaps` | `{keymaps:[名字]}` |
| `keymap` | `--print-keymap=<名字>` | `{name, source, lines, includes, keys}`；`lines` 是**原文逐字** |
| `plan` | `--print-plan` | `{filesystem, boot, esp, pacman_conf}` |
| `checkHostname` / `checkLocale` / `checkKeymap` / `checkTimezone` | `--check-<项>=<值>` | `{ok, reason, message}`；`reason` 是 `format` / `notInList` / `notFound` |
| `connectWifi` | `--connect-wifi=<SSID>`（密码走 stdin） | `{ok, reason, message}` —— **连不上也是 ok:true 的答案** |

一律用 `--开关=值` 而不是 `--开关 值`：值以 `-` 开头时（`-bad-` 这种主机名是测试用例里就有的），
分开写会被 argparse 当成另一个开关，然后报一句与事实无关的错。

`message` 是给人与日志的中文，**界面不许直接显示它**（英文模式会露馅）—— 用 `reason` 查文案表。

### 7.3 安装：`Plan` + 两条不进 argv 的东西

`backend.js` 的 `buildPlan(setup)` 把界面上的选择翻成 `pipeline.Plan`
（`disk` / `hostname` / `user` / `locale` / `timezone` / `keymap`，其余用后端默认值）。
界面不暴露的字段（`packages_file` / `steps` / `no_nvram` …）不替它们编值。

- **密码只走 stdin**（`secrets` → 子进程 stdin，用户在前、root 在后）。
  argv 会留在进程列表与日志里，所以它永远不进命令行，也永远不回显。
- **取消走 `SIGUSR1`**，不是 `SIGINT`/`SIGTERM`：后两个是「立刻去死」的语义，
  而装盘装到一半被杀，留下的是一个谁都说不清的半成品。收到 `SIGUSR1` 只是**举手**，
  真正的取消发生在**阶段之间**（`pipeline.run(should_cancel=…)`），退出码 130、
  并按与失败相同的路径卸载目标。页面上那句 `progress.cancelHint`（「只能在一个阶段结束后取消」）
  说的就是这件事。

`--yes` 由界面带上：擦除页那道逐字确认（`confirm.js`）就是那次二次确认，
**守卫没有减少，只是换了个人回答**。

### 7.4 事件流：一行一个 JSON 对象

后端 `events.JsonReporter` 写 stdout，判别字段是 `kind`：

| kind | 含义 |
|---|---|
| `hello` | 第一条。带 `protocol` 版本 |
| `event` | 阶段与进度。`phase` 取自 `events.PHASES`（`start`/`disk`/`packages`/`configure`/`boot`/`done`） |
| `note` | 给人看的旁白（目标盘、dry-run 之类） |
| `command` | 跑了哪条命令 |
| `error` | 失败：退出码 + 消息 + 提示。**之后一定跟一条 `end`** |
| `end` | 后端自己的收尾，带进程退出码 |
| `exit` | **主进程加的**：子进程真的退出了，带 `code` 与 `cancelled` |

`percent` 只有 `done` 那一条是 100，其余是 `null` —— 后端也不知道 `pacstrap` 装了百分之几。
**进度条的推进单位因此是「阶段」，不是百分比**（`pages/progress.js` 的 `PHASES` 表）。

### 7.5 `mock.js` 现在只做离线自检

`MIPL_PROBE=1` 时 `app.js` 装 `Mock`，其余一律装 `Backend`。两者**同形**：
页面读的每个键、调的每个方法都一样，探针跑的因此是同一份页面代码 ——
契约一旦漂移，探针会先红。产品路径上没有任何一处读 Mock。

## 8. 明确不做

写盘记忆 · 08 §4.2 的排除项 · 任何 npm 运行期依赖 ·
WebGL / three.js（QEMU 无 GPU，理由记在 `vendor/README.md`）·
把安装逻辑写进渲染层（分区 / 装包 / 配置 / 引导一律在后端）。
