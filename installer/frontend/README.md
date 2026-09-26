# installer/frontend · 安装器前端（M2）

这里放 PySide6 的图形界面。

> **状态：** G3 完成设计语言 + 全部页面 + 流程接线（2026-09-25）；
> **M2 真接线已完成**（2026-09-26）—— 界面吃的是真实后端数据与事件流，不是 mock。
> 设计规格与逐条实测状态见 [docs/work/tech/07-M2界面设计.md](../../docs/work/tech/07-M2界面设计.md)。
>
> 流程与状态在 `qml/Main.qml`（唯一的 Window，页面是它里面换进换出的 Item）：
>
> ```
> 加载 → 欢迎 → 网络 → 系统磁盘 → 磁盘分区 → 确认擦除 → 账户 → 安装详情 → 安装 → 结束
> 分支：欢迎「高级安装」→ 语言 / 键盘 / 时区 / 主机名
> ```
>
> **数据全部来自后端**：`Backend`（候选盘 / 分区预告 / 就绪检查 / 网络 / 四份名单 /
> 校验）与 `Install`（安装控制器：工作线程 + 事件信号）。这两个对象由
> [mipl-installer](mipl-installer) 挂进来，形状见 [bridge/README.md](bridge/README.md)。
> 页面自身仍保留一份默认值，那只在**没有后端**时生效（取图与流程烟测要可复现的图）；
> `Main.qml` 里那段 `rehearsalSteps` 假安装同理，真身永远轮不到它。
> 另有 `GalleryPage.qml`（控件与状态总览）。

## 怎么把流程跑起来

```bash
# 在开发机上直接看（有显示环境）
python3 installer/frontend/mipl-installer

# 无显示环境 / CI：把整条链走一遍并断言每一跳（不需要后端、约 2 秒；
# 加 --demo 会等假安装演完，约 12 秒）
python3 installer/frontend/tools/flow-check.py --demo

# **接线**的端到端烟测：挂上真 Backend + Install，走真数据、真事件流，
# 安装那一段走 dry-run（只打印命令，不碰盘，**不需要 root**）
python3 installer/frontend/tools/wiring-check.py

# **M2 验收**：真 ISO 上无头点完整条链，再从盘启动验检查点 4
# （要 root；按仓库规矩走 pkexec。不需要显示器 —— 见该脚本头部）
pkexec /usr/bin/python3 installer/frontend/tools/gui-install.py

# 取图（每屏一张 PNG，落 out/m2-prototype/）
python3 installer/frontend/tools/shots.py --page flow --set page=welcome
```

`flow-check.py` 与 `wiring-check.py` 的分工：前者验**离线**那条路（路由与状态传递，
页面默认值 + 排练假安装），后者验**真身**那条路（候选盘来自后端、事件流真的在报、
参数守卫在动盘之前、擦盘守卫拦得住、排练开关在 Live 的形状下是 `false`）。
`wiring-check.py` 最后还会**照 ISO 的目录布局把入口真跑一遍** —— 后端包在产物里不在
`sys.path` 上，这类「仓库全绿、ISO 里起不来」的坑（Issue #50）不能靠推理蒙过去。
两条都要绿。

## 一条规则

**前端只订阅事件，不实现逻辑。** 唯一允许的依赖是后端的事件流：

```python
from mipl_installer.events import Event, Reporter
```

- `backend/mipl_installer/` 里**不许**出现 `PySide6` / `Qt` 的 import；
- `frontend/` 里**不许**出现分区、`pacstrap`、chroot 配置、写引导 —— 那些全在后端。
  界面要做进度条，就实现一个 `Reporter`（真身在 [bridge/reporter.py](bridge/reporter.py)）：

```python
class QtReporter:                       # 前端侧
    def emit(self, event: Event) -> None: ...
```

事件名（后端 `events.PHASES`）是**稳定接口**：`start / disk / packages / configure / boot / done`。
改名字等于改接口，先和后端对齐。

**同一条规则管住三件事，别在 QML 里另起炉灶：**

| 不许在界面里做 | 该调谁 |
|---|---|
| 解析 `nmcli` / `lsblk` 之类的命令输出 | `Backend.network()` / `candidates()` |
| 读 sysfs、数分区、算容量比例 | `Backend.candidates()` / `partitionPlan()` |
| 自己写校验正则 | `Backend.validateUser()` / `validateHostname()` / `validateTimezone()` / `validateKeymap()` |

最后一条尤其要紧：**用户名的合法性来自后端 `configure.validate_user`，前端调用它，
不重写一份正则** —— 重写就是「唯一来源」约定在验证逻辑上的翻版
（这条规则原来写在 `AccountPage.qml` 里，2026-09-26 已改成调用）。

## 目录

```
frontend/
├── mipl-installer          Live 侧入口（cage 拉起；只负责起引擎，不含逻辑）
├── mipl-kiosk              kiosk 启动脚本（过 seatd-launch 起 cage）
├── assets/                 LOGO 资产（PNG 进仓库，理由见 assets/README.md）
├── icons/lucide/           Lucide 图标，**只放界面用到的那些**（见 icons/README.md）
├── qml/
│   ├── Main.qml            流程壳：唯一的 Window、路由、状态、后端接线
│   ├── theme/              设计令牌（Tokens.qml）—— 全项目唯一的视觉真相
│   ├── components/         控件：PageShell / Button / Card / Field / Alert / Badge / …
│   ├── pages/              流程各页（欢迎 → … → 结束，见上）+ 高级安装 + 失败态
│   └── GalleryPage.qml     控件与状态同屏总览（评审看它）
├── bridge/                 前后端接线层（**唯一允许的耦合**，见 bridge/README.md）
│   ├── paths.py            把 backend/ 挂上 sys.path（漏了只在 ISO 里发作）
│   ├── reporter.py         QtReporter：事件流的唯一通路
│   ├── install.py          InstallController：pipeline.run 跑在工作线程里
│   ├── backend.py          Backend：探测 / 名单 / 校验 / 重启
│   ├── records.py          后端事实 → 界面记录（纯函数，能单测）
│   ├── actions.py          重启（Backend.reboot 落到这里）
│   └── icons.py            Lucide 图标 provider
└── tools/
    ├── shots.py            把页面渲染成 PNG + 量高（--measure / --set 取交互态）
    ├── flow-check.py       离线流程烟测：走一遍整条链并断言每一跳
    ├── wiring-check.py     接线烟测：真 Backend + 真事件流，安装走 dry-run
    ├── gui-install.py      **M2 验收**：真 ISO 上无头点完整条链 + 验从盘启动
    └── build-assets.sh     从 LOGO 源图生成界面用的小图
```

**包名不跟目录名走**（[installer/AGENTS.md](../AGENTS.md)）：目录按角色分，
import 名一律是 `mipl_installer`；前端的 Python 侧沿用这个约定。

## 怎么跑原型

**不要用 `qmlscene` / `qml`** —— 本机实测这两个 Qt 工具连纯 QML 文件都加载不了
（`Library import requires a version`，成因见 [tech/07 §1](../../docs/work/tech/07-M2界面设计.md)）。

```bash
# 取图（默认全部页面 → out/m2-prototype/）
python3 installer/frontend/tools/shots.py
python3 installer/frontend/tools/shots.py --page welcome        # 只看一页
python3 installer/frontend/tools/shots.py --list                # 有哪些页面
python3 installer/frontend/tools/shots.py --size 1024x600       # 验小屏降级
python3 installer/frontend/tools/shots.py --out /tmp/m2-shots   # out/ 属 root 时用它

# 流程壳：某一屏 / 某个交互态
python3 installer/frontend/tools/shots.py --page flow --set page=welcome
python3 installer/frontend/tools/shots.py --page account --set submitted=true

# 在真实 kiosk 里看（要重建 ISO）
sudo ./scripts/mipl.sh build
sudo ./scripts/mipl.sh installer --serial console
```

`shots.py` 走 PySide6 的 `QQmlApplicationEngine`，**与 `mipl-installer` 是同一条路** ——
所以它不是临时脚手架，而是本机迭代的标准姿势。

## 界面怎么被拉起来

`cage` kiosk 那条链属线 E 的活，见 [installer/AGENTS.md](../AGENTS.md) 与
[installer-roadmap.md](../../docs/work/installer-roadmap.md) §4 的 M0 / M2；
启动链的逐步拆解在 [tech/04](../../docs/work/tech/04-安装逻辑与实测.md) §1。
