# docs/work · 工作计划

按阶段组织的工作任务与技术细节。

> `docs/knowledge/` 存放**已经确定的结论**（概念、决策、原理），是给新手读的：
> 只写结论 —— 不写「待解决」「以后再说」，改动也不留「某日修订」这类痕迹。
> 没定的东西一律放 `docs/work/` 或 [06-待定事项](../knowledge/06-待定事项.md)。
>
> **提到人时用角色称呼**（维护者、贡献者），不写「朋友」「某某的分支」；人数会变，别把人数写进流程描述 ——
> 长期维护者之外，还有预备维护者在参与。
>
> `docs/work/` 存放**待执行与正在执行的工作**：工作 issue 的规范与草案骨架、ROADMAP、实测步骤。

---

## 工作在哪里

| 想知道什么 | 去哪看 |
|---|---|
| 现在有哪几条工作在跑、谁在做 | **GitHub Issues**：按 label `task` 筛，**assignee 就是受理人** |
| 一条工作要写成什么样 | 本文件的[「工作 issue 规范」](#工作-issue-规范) |
| 照着填的骨架 | [TEMPLATE.md](TEMPLATE.md)（正文骨架）· [.github/ISSUE_TEMPLATE/task.yml](../../.github/ISSUE_TEMPLATE/task.yml)（网页表单） |
| 安装器接下来做什么 | [installer-roadmap.md](installer-roadmap.md) |
| 已经跑过什么、怎么复现 | [tech/](tech/) |

**分工不写在仓库文档里了。** `docs/work/YYYY-MM-DD.md` 那种当日文档已退役：分工的载体是 issue 本身，
仓库里只留**规范**（本文件）、**骨架**（`TEMPLATE.md`）与**实测步骤**（`tech/`）。
2026-10-01 之前的四份当日文档**保持原样**（历史不改写），但它们的分工早已失效，不要照抄。

---

## 目录结构

```
docs/work/
├── README.md                本文件，索引 + 工作 issue 规范
├── TEMPLATE.md              工作 issue 的正文骨架（复制到 out/issue-drafts/ 再填）
├── installer-roadmap.md     安装器 ROADMAP：里程碑、验收标准、失败模式
├── 2026-09-18.md            历史：当日分配（旧版式），保持原样
├── 2026-09-19.md            历史：当日分配（旧版式），保持原样
├── 2026-09-21.md            历史：当日分配（旧版式），保持原样
├── 2026-09-23.md            历史：当日分配（旧版式），保持原样
└── tech/                    技术细节（可复现的操作步骤）
    ├── 01-容器环境搭建.md
    ├── 02-构建与QEMU测试.md
    ├── 03-术语表.md
    ├── 04-安装逻辑与实测.md
    ├── 05-装后系统验证.md
    ├── 06-镜像源与联网.md   （规划中，尚未建立）
    ├── 08-界面设计方向.md   安装器 MD3 设计方向（2026-10-04 起为历史参考）
    ├── 09-安装器界面文案.md 104 条界面文案 + 34 条时区名的审核记录（唯一源）
    ├── 10-安装器界面视觉方向.md  当前 UI 准据；接口冻结在 `installer/frontend/app/README.md`
    └── 11-安装器前端实测.md  Electron 前端的实测记录与未实测清单
```

脚本在仓库根目录的 `scripts/`，不在 `docs/` 下；清单见[根 README 的脚本表](../../README.md)。
与本目录直接相关的是 `scripts/check-work-issue.sh`：校验 `out/issue-drafts/` 里的草案。

---

## 工作 issue 规范

一条工作 = 一个 issue。**草案**照 [TEMPLATE.md](TEMPLATE.md) 的骨架写，**网页表单**照
[task.yml](../../.github/ISSUE_TEMPLATE/task.yml) 填 —— 两边字段逐字相同，守卫会比对，改一边必须改另一边。
这一节是判据：模板与表单里没写清楚的地方以这里为准。

### 受理人写角色，不写人名

项目里人会用角色称呼（见 [docs/AGENTS.md](../AGENTS.md)）：人名会变，角色不变。
角色到人的对应**只在本表维护**，每日文档不许再抄一遍：

| 角色 | 是谁 | 宿主机 | 能碰的范围 |
|---|---|---|---|
| 维护者 | [@LaT-SKY](https://github.com/LaT-SKY) | CachyOS | 全部；`main` 受保护，PR 必须有其审核；真机、`root` 操作与公开发布由其本人执行 |
| 协作者 A | [@ieer040126](https://github.com/ieer040126) | Arch Linux | 按 issue 指派的范围改；跨线改动先提 issue |
| 协作者 B | [@yks0630](https://github.com/yks0630) | Arch Linux | 同上 |

人够三条线并行，所以同一轮**通常同时开三个 issue**（每个都要写明文件路径，见下）。
角色名是稳定的外壳，handle 只在这张表里出现 —— 账号改名只改一处。
**GitHub 上的 assignee 是 handle**：issue 正文写角色，assignee 用人名；两者对不上时以正文为准，并当场问维护者。

### 编号：用 issue 号

**「线编号」（A–Z、AA…）已退役** —— issue 号天然唯一、不会被跨天重用，`scripts/mipl-work-lines.sh` 因此删除。
要说另一条工作，就写**它的 issue 号或文件路径**。旧的线编号出过事故：09-18 的「线 B」是 Fedora 测试环境，
09-19 的「线 B」是安装器 —— 历史文档里的 A–I **只属于那几天**，任何地方都不许跨文档引用。

### 每个 issue 必须有验收标准

「合入了」「跑起来了」「安装器提示成功」都不是验收标准。验收要写成**能在本机跑出来的判据**：
命令 + 期望结果。没有实测证据不许写「已验证」——只能写 未实测 / 仅静态检查 / 仅 dry-run
（仓库口径见 [根 AGENTS.md](../../AGENTS.md) 与 [05-测试方法](../knowledge/05-测试方法.md)）。

### 草案 ≤ 60 行

一个 issue 只留**目标、实现、验收、回报、依赖**。实测输出、踩坑过程、可复现的操作步骤一律进
[tech/](tech/)，事后复盘进 [archive/](../archive/)。旧版当日文档最长的一份 314 行，就是因为把过程
写进了分配里 —— 后来没人愿意读，也就没人照着做。

### 怎么发布

草案存 `out/issue-drafts/<主题>.md`（`out/` 已 gitignore，草案不是仓库资产），填好之后三条路：

| 路 | 谁来做 | 怎么做 |
|---|---|---|
| 网页表单 | 维护者 | New issue →「工作分配」（不依赖 `gh`，任何环境都能走） |
| `gh` | 维护者（本机已装 `gh` 并登录维护者账号） | `gh issue create --title "[工作] <主题>" --body-file out/issue-drafts/<主题>.md --label task` |
| REST + token | 有 token 的机器 | `POST /repos/MipLinux/MipLinux/issues`，正文经 `jq -Rs` 塞进 JSON 的 `body` |

**红线：** issue 会以**维护者账号公开发布**，发布前必须给人过目；AI 只产草案，不自己建 issue、
不自己建 label、不自己开 PR。表单里的「受理人」只是候选，**维护者确认后才生效**。

标签用 `task`（**已于 2026-10-01 建好**）。表单里写了 `labels: ["task"]`，但**标签不存在时 GitHub 是静默忽略**
（不报错）—— 换仓库或换标签时要先建，否则新 issue 身上不会带标签。

### 守卫查到哪、查不到哪

`./scripts/check-work-issue.sh`（不需要 root、只读）校验 `out/issue-drafts/*.md`：字段齐备且顺序正确、
受理人是三个角色之一、验收段含命令与期望、实现段写出文件路径、没把 YAML frontmatter 或 HTML 注释
抄进 issue 正文、≤60 行；外加**骨架与表单的字段是否漂移**（`TEMPLATE.md` ↔ `task.yml`）。

**它查不到发出去之后的 issue** —— 仓库没有 CI，issue 正文是 GitHub 上的数据，本地没有副本。
所以「字段齐、有验收」这件事只在草案阶段拦得住，发布之后靠人看。

守卫自己也有回归测试：`./scripts/check-work-issue.test.sh` 用临时夹具塞进字段缺失、受理人写人名、
验收没命令、超行数、骨架/表单漂移等九种情形，验证抓得住也不误报（夹具不碰真实仓库）。

### 表单里每个字段的来历

| 字段 | 为什么有 |
|---|---|
| 受理人 | 所有权按文件切，受理人必须明确到角色（handle 只在上面那张表里维护） |
| 目标 | 一句话说清「什么从不能变成能」，避免把做法当成目标 |
| 实现 | **逐个写文件路径** —— 两条工作撞在同一批文件上就没法并行，写出来才拦得住 |
| 验收 | 命令 + 期望结果；「跑起来了」不是判据（见上） |
| 回报 | 完成时要交的证据：命令输出、文件路径、实测截图 |
| 依赖 | 被哪个 issue / P 编号 / 里程碑卡住；不写「无」会让人以为漏了一行 |
| 开工前请执行 | 把 `git switch main && git pull` 与分支命名钉成命令，避免「在别人分支上顺手加东西」 |

---

## 常用命令

日常操作都走 `scripts/mipl.sh`。**不要手抄长命令** —— 仓库里的 Issue #7、#8
都是手抄抄出来的，而且都出现在最不该花时间的地方。

**所有命令都要 `sudo`**：脚本一律要求 root，普通用户运行会被直接拒绝。
它不自己提权 —— 隐式提权会让「谁改了 `out/`」变得说不清。
环境变量也要写在 `sudo` 后面（`sudo` 默认会清掉你 shell 里的变量）。

| 命令 | 作用 |
|---|---|
| `sudo ./scripts/mipl.sh doctor` | 环境自检（换机器第一件事）；`--report` 输出可粘进文档的表格 |
| `sudo ./scripts/mipl.sh build` | 下载 bootstrap → 解压 → 用仓库 `profile/` 构建 ISO。工作目录默认容器内 `/var/tmp/mipl-work`，**构建前自动清空**（`--keep-work` 保留）；**别用 `/tmp`** —— 容器里它是内存盘。`--baseline` 改用容器内原版 releng |
| `sudo ./scripts/mipl.sh qemu` | 启动 QEMU。默认刷新 `OVMF_VARS` 并只测 Live 环境 |
| `sudo ./scripts/mipl.sh target` | 建一块空的目标盘（默认 `out/target.qcow2`，40G 虚拟）。已存在就拒绝 —— 它上面可能装着系统；`--force` 覆盖（连同它的 NVRAM） |
| `sudo ./scripts/mipl.sh qemu --disk target.qcow2` | 装系统：ISO 优先启动 + 挂上这块盘。**盘的 NVRAM 是 `out/target.vars.fd`，保留**，不会被 ISO 测试的变量文件刷掉 |
| `sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c` | 装完重启进新系统：不挂 ISO、保留 NVRAM。盘上没引导项时会明确报 `no bootable device`，不会悄悄回到 Live |
| `sudo ./scripts/mipl.sh shell` | 进入 nspawn 构建容器（`/out` 与只读的 `/profile` 都挂好） |
| `sudo ./scripts/mipl.sh stop` | 关闭容器（**用完别忘了**，见 Issue #4） |
| `sudo ./scripts/mipl.sh -n <命令>` | 只打印将执行的命令，不做任何改动 |
| `sudo ./scripts/mipl.sh clean` | 删 `OVMF_VARS*`；`--iso` 连 ISO 一起删；`--disk` 删目标盘及其 NVRAM；`--bootstrap` 删 bootstrap 缓存（下载的 126 MB 那个）。都不可逆，会先问一句 |
| `./scripts/check-identity.sh` | **不需要 sudo**：扫 `profile/` 里有没有没改干净的旧品牌名；加 `--iso out/miplinux-*.iso` 扫产物（卷标 / publisher / application / 引导菜单文本） |

`build` 现在会在下载前后校验 bootstrap（`sha256` + `zstd` 完整性），缓存坏了直接删掉重下；
解压前后各查一次容器是否真的能用（能执行的 shell / 动态链接器 / `pacman`），而不是只看
`etc/os-release` 在不在 —— 它在归档里排第 630 条，`usr/bin/bash` 排第 5815 条，
半途而废的解压恰好能骗过「文件在不在」式的检查（Issue #32）。

进容器时还会挂两份宿主机生成的配置（容器里的原文件不动）：
`<out>/mirrorlist` → `/etc/pacman.d/mirrorlist.mipl`（默认清华源），
`<out>/resolv.conf` → `/etc/resolv.conf`（bootstrap 自带的那两份都不可用，
是 `pacman` 静默失败、`archiso` / `mkinitcpio` 装不上的根源）。
容器里装的是 `archiso + mkinitcpio + arch-install-scripts` ——
**`archiso` 不依赖 `mkinitcpio`**，只装 `archiso` 永远不会带上它。

三个设计约束：**一律 root 且不隐式提权**、**路径全部从脚本自身位置推导**
（两台机器的仓库路径不同）、**固件路径靠探测**（不同发行版的 OVMF 路径不一样）。
完整说明见 `sudo ./scripts/mipl.sh --help`。

fish 用户（fish 函数不能直接 `sudo`，所以函数体里是「先 sudo、再带脚本路径」）：

```fish
# ~/.config/fish/functions/mipl.fish
function mipl --description 'MipLinux 项目操作台'
    sudo /绝对路径/scripts/mipl.sh $argv
end
```

之后敲 `mipl qemu` 即可。

---

## 当前阶段

| 阶段 | 文档 | 状态 |
|---|---|---|
| ① 构建环境与基线 | [2026-09-18.md](2026-09-18.md) | ✅ 未修改的 `releng` 构建出 ISO，QEMU（UEFI）引导到 `[root@archiso ~]#` |
| ② 自有 profile 落地 | [2026-09-19.md](2026-09-19.md) | ✅ `profile/` 进仓库、构建管线、目标盘挂载、改名 MipLinux |
| ③ 国内源与中文本地化 | [2026-09-19.md](2026-09-19.md) | 🚧 `airootfs` 的配置已并入主线；字体与输入法的**包**待补，装后系统的源继承待解（Issue #23） |
| ④ NVIDIA 驱动 | [tech/05](tech/05-装后系统验证.md) | ✅ **Live 半段真机实测通过**（09-22，独显模式下 RTX 5060 Max-Q：驱动加载、`nvidia-smi` 正常、内屏点亮、`nmcli` 联网）；🚧 **装后系统半段未做**，随安装器 M3 一起验 |
| ⑤ 安装程序（M0–M2） | [installer-roadmap.md](installer-roadmap.md) · [tech/04](tech/04-安装逻辑与实测.md) · tech/07（已移出仓库） | ✅ M0 启动链与检查点 1 / 2 实测通过（含 tty1 兜底）；✅ M1 检查点 4 由 PR #42 验过；✅ **M2 验收通过**（2026-09-26：无头驱动 `tools/gui-install.py` 在真 ISO 上点完整条链、**检查点 3 与 4 都实测过**；单测 239 全绿、接线烟测 44 项、15 个流程页一屏放得下）。真跑抓到两个缺陷并已修；**检查点 5 / 6 归装后系统一侧（M3）**。技术栈见 D14 |
| ⑥ 装后系统（M3 前半） | [tech/05](tech/05-装后系统验证.md) | 🚧 检查点 5 / 6 与源继承属 M3；真机半段（N 卡 / 桌面 / 中文输入法）随维护者 |

**新手从这里开始：** [tech/01-容器环境搭建.md](tech/01-容器环境搭建.md) → [tech/02-构建与QEMU测试.md](tech/02-构建与QEMU测试.md)。
工具不熟先看 [tech/03-术语表.md](tech/03-术语表.md)。

**基线不是一次性动作，是常备的诊断工具。** `sudo ./scripts/mipl.sh build --baseline`
改用容器内原版 `releng` 构建；以后某次构建挂了，跑一次就能分开「环境坏了」和
「自己改坏了」——理由见 [01-概念模型.md](../knowledge/01-概念模型.md) 第 7.1 节「产物决定一切」。

---

## 术语速查

| 名字 | 一句话 |
|---|---|
| **Arch bootstrap** | 一包 Arch 的文件系统，是容器的「食材」 |
| **systemd-nspawn** | 把那个文件系统跑成容器的工具，用来**构建** |
| **容器** | nspawn 跑起来后的运行环境，里面是纯 Arch |
| **releng** | archiso 自带的官方参考 profile，基线构建的起点 |
| **QEMU** | 虚拟机，用来**引导和测试**产物 |
| **OVMF** | QEMU 使用的 UEFI 固件实现 |

完整解释见 [tech/03-术语表.md](tech/03-术语表.md)。

---

## 相关文档

| 文档 | 位置 |
|---|---|
| **正在做的工作（唯一来源）** | [GitHub Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask) |
| 项目概览与决策记录 | [README.md](../../README.md) |
| 概念模型 | [knowledge/01-概念模型.md](../knowledge/01-概念模型.md) |
| 环境与工具链 | [knowledge/02-环境与工具链.md](../knowledge/02-环境与工具链.md) |
| 项目结构 | [knowledge/03-项目结构.md](../knowledge/03-项目结构.md) |
| 架构决策 | [knowledge/04-架构决策.md](../knowledge/04-架构决策.md) |
| 测试方法 | [knowledge/05-测试方法.md](../knowledge/05-测试方法.md) |
| 待定事项 | [knowledge/06-待定事项.md](../knowledge/06-待定事项.md) |
| 安装器 ROADMAP | [installer-roadmap.md](installer-roadmap.md) |
| 已经解决的问题 | [archive/](../archive/) |
