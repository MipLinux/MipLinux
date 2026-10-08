<div align="center">

**MipLinux**

基于 Arch Linux 的滚动发行版 · 中文开箱即用 · NVIDIA 驱动预装

[![平台](https://img.shields.io/badge/平台-x86__64-4a5568?style=flat-square)](https://github.com/MipLinux/MipLinux)

</div>

MipLinux 解决两个 Arch 系发行版的常见麻烦：

- **NVIDIA 驱动开箱可用** —— 多数 Arch 系发行版不预装 N 卡驱动，装完还得自己折腾。
- **对中文用户友好** —— 目标是国内镜像源、`zh_CN.UTF-8`、CJK 字体、`fcitx5` 输入法全部默认配好，装完不用手动折腾（做到哪一步见下面的进度表）。

交付形态是装到硬盘的滚动发行版（D7）。ISO 采用**在线安装**：Live 环境极简、开机直进安装器，包在安装时从国内源拉取（D11 / D12）。

---

## 当前进度

> 截至 **2026-10-04**。正在做的工作在 [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask)（一条工作 = 一个 issue），实测记录在 [`docs/work/`](docs/work/)。

<!-- BEGIN:progress-table -->
| 阶段 | 状态 |
|---|---|
| 构建环境与基线 | ✅ 未修改的 `releng` 构建出 ISO，QEMU（UEFI）引导到 `[root@archiso ~]#` |
| 自有 profile | ✅ `profile/` 进仓库并改名 MipLinux，产物 `miplinux-<日期>-x86_64.iso`（1.5 GiB，构建 2 分 08 秒） |
| 装系统链路 | ✅ 安装器 M0、M1 实测：空盘装出能启动的系统（检查点 4），装后 `pacman -Syu` 成功（检查点 6）；检查点 5 到配置层 |
| 国内源与中文本地化 | 🚧 国内源、`zh_CN.UTF-8`、CJK fallback、终端字体已并主线；装后系统的源继承、用户 / sudo、输入法环境变量已实测生效。清单现为 Live 保留 Noto CJK，装后系统列入 CJK 字体、Maple Mono 与 `fcitx5`；这次仅调整清单，安装后效果尚未重测（[P10](docs/knowledge/06-待定事项.md)）；`reflector` 防线随 M4（[Issue #23](https://github.com/MipLinux/MipLinux/issues/23)） |
| NVIDIA 驱动 | 🚧 Live 清单已加 `nvidia-open` / `nvidia-utils`；真机第一次验证 ✅（09-22，RTX 5060 Max-Q，独显模式）：驱动加载、`nvidia-smi`、内屏点亮、`nmcli` 联网；装完重启后能用未做，由 M3 带 |
| 安装程序 | 🚧 M0 / M1 完成、后端单测 239 全绿；M2 曾于 2026-09-26 用**当时的** Qt 前端实测通过。界面层此后两度重建，2026-10-04 定为 **Electron**（D14）：12 个页面（普通 8 + 高级 4）已能在 QEMU 的 Live 里走通（维护者 10-04 实机逐屏点过并提了 7 批反馈，已全部修完），ISO 体积 +104.5 MiB 实测；**键盘全流程 / 首帧预算 / 真机 NVIDIA 硬件渲染仍未实测**（[tech/11](docs/work/tech/11-安装器前端实测.md)） |
| 桌面环境 / 品牌化 | ⬜ 未开始。P5 已定不做 DE，niri / Hyprland 待真机各跑一轮 |
<!-- END:progress-table -->

**「✅」= 本机实测过**，不代表下载到的成品已具备该能力。每阶段验到第几个检查点，以[测试方法](docs/knowledge/05-测试方法.md)的六个检查点为准。

> **还没做：** 安装器界面层（Electron，D14 2026-10-04 改定）· 桌面环境 / 品牌化 · 装后系统的 CJK 字体、Maple Mono 与 `fcitx5` 安装效果验证（P10）· NVIDIA 装后系统半段（M3）· 键盘目前只有 `us` 生效（[Issue #64](https://github.com/MipLinux/MipLinux/issues/64)）。

---

## 上手

命令一律需要 root；`mipl.sh` 不自己提权，非 root 时只打印该敲的命令然后退出。

```bash
sudo ./scripts/mipl.sh doctor        # 环境自检，换机器第一件事
sudo ./scripts/mipl.sh build         # 用仓库里的 profile/ 构建 ISO
sudo ./scripts/mipl.sh qemu          # 启动 QEMU，只测 Live
sudo ./scripts/mipl.sh stop          # 关闭构建容器，用完别忘了

sudo ./scripts/mipl.sh target                              # 建虚拟目标盘 out/target.qcow2
sudo ./scripts/mipl.sh qemu --disk target.qcow2            # 装系统：ISO 优先 + 挂盘
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c   # 装完：从盘启动
```

完整说明见 `sudo ./scripts/mipl.sh --help`。

### 构建与测试环境

| 环节 | 是什么 | 为什么是它 |
|---|---|---|
| 源码 | `profile/` —— 发行版的「源代码」就是配置文件 | 构建是**装配**不是编译，改配置即改行为 |
| 构建 | `systemd-nspawn` 容器里的纯 Arch，跑 `mkarchiso` | 需要 `pacman` / `pacstrap` / `mkinitcpio` |
| 测试 | 宿主机的 QEMU（KVM），终验真机 | nspawn 不能引导；NVIDIA 驱动与分区行为只能在真机终验 |

宿主发行版与项目无关（三位开发者使用不同的宿主发行版），容器只读挂载仓库里的 `profile/`，唯一必须保持一致的接口是包清单 [`profile/packages.x86_64`](profile/packages.x86_64)。

## 四条贯穿原则

- **构建是装配不是编译**：`mkarchiso` 先装出一个完整的 Arch 系统，再把系统压扁成只读镜像。
- **逻辑先于外壳**：安装链先在无界面状态下跑通，界面只是它的第二个调用者。
- **不做无损 resize**：分区只在虚拟盘 `out/target.qcow2` 上测，真机用独立硬盘。
- **命令一律走脚本**，不手抄 `mkarchiso` / `pacstrap` / `qemu`；**安装器直到它装出来的系统能启动，才算被测过**。

---

## 文档导航

结论在 `docs/knowledge/`，进行中的工作在 `docs/work/`，已解决的问题记录在 `docs/archive/`。

| 想知道什么 | 去哪看 |
|---|---|
| 怎么构建出一个发行版（新手先读） | [01-概念模型](docs/knowledge/01-概念模型.md) → [02-环境与工具链](docs/knowledge/02-环境与工具链.md) → [03-项目结构](docs/knowledge/03-项目结构.md) |
| 安装器接下来做什么 | [installer-roadmap.md](docs/work/installer-roadmap.md)：里程碑 M0–M5、验收标准、失败模式 |
| 怎么验证 ISO 和装后系统 | [05-测试方法.md](docs/knowledge/05-测试方法.md)：六个检查点 |
| D1–D14 为什么这么定 | [04-架构决策.md](docs/knowledge/04-架构决策.md) |
| 还没定的事、已否决的选项 | [06-待定事项.md](docs/knowledge/06-待定事项.md)：P 表 |
| 正在做的工作（唯一来源） | [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask)：一条工作 = 一个 issue |
| 工作规范与 ROADMAP / 已归档问题 | [work/README](docs/work/README.md) · [archive/](docs/archive/README.md) |

## 脚本 `scripts/`

| 脚本 | 作用 |
|---|---|
| [mipl.sh](scripts/mipl.sh) | 项目操作台：环境自检、构建、QEMU 测试、进出构建容器（需要 root） |
| [mipl.fish](scripts/mipl.fish) | 同一操作台的 fish 入口，薄封装 |
| [baseline-build.sh](scripts/baseline-build.sh) | 构建本体，由 `mipl build` 调用；`--baseline` 改用原版 `releng` 做对照 |
| [check-identity.sh](scripts/check-identity.sh) | 品牌一致性检查（**不需要 root**）；`--iso` 扫产物 |
| [check-doc-sync.sh](scripts/check-doc-sync.sh) | 文档同步守卫：本 README 的进度口径与组织主页是否一致（**不需要 root、只读**） |
| [sync-profile-progress.sh](scripts/sync-profile-progress.sh) | 把本 README 的进度表同步进组织主页，写完自跑守卫，不通过就回滚 |
| [check-doc-sync.test.sh](scripts/check-doc-sync.test.sh) | 上面两个脚本的回归测试：塞进各种漂移，验证抓得住也不误报 |
| [check-readme-links.sh](scripts/check-readme-links.sh) | README 可点性检查：仓库内死链、跨仓库死链、死锚点、进度表标记（**不需要 root**） |
| [check-work-issue.sh](scripts/check-work-issue.sh) | 工作 issue 草案守卫：`out/issue-drafts/` 里的草案是否符合[工作 issue 规范](docs/work/README.md)（字段齐备、验收含命令与期望、≤60 行），并比对骨架与表单的字段是否漂移（**不需要 root、只读**） |
| [check-work-issue.test.sh](scripts/check-work-issue.test.sh) | 上面那个守卫的回归测试：九个用例塞进字段缺失 / 过时的受理人正文段 / 验收没命令 / 超行数 / 骨架或表单漂移，验证抓得住也不误报（**不需要 root**） |

---

## 怎么参与

- 长期维护者三位（CachyOS / Arch / Arch），三台机器的宿主发行版各不相同 —— 这正是脚本「路径从自身位置推导、固件路径运行时探测」的由来；**分工在 [Issues](https://github.com/MipLinux/MipLinux/issues?q=label%3Atask) 里**（一条工作 = 一个 issue，assignee 就是受理人），怎么写见[工作 issue 规范](docs/work/README.md)。
- `main` 受保护，PR 必须含 code owner（[@LaT-SKY](https://github.com/LaT-SKY)）的审核，见 [CODEOWNERS](.github/CODEOWNERS)。
- 一个 PR 只做一件事；出界的改动先按 [Issue 模板](.github/ISSUE_TEMPLATE/) 提 issue，不夹带进 PR。
- 现状边界：v0.1 只做 UEFI + 整盘擦除 + ext4 单根；没有 LICENSE、没有 CI；`archlinuxcn` 第三方仓库目前以 `SigLevel = Optional TrustAll` 启用，对外发布前怎么收紧是 [P11](docs/knowledge/06-待定事项.md)，不新增第三方仓库、不改 `SigLevel`。
