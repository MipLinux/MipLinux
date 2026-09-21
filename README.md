# MipLinux

一个基于 Arch Linux 的可变（滚动更新）发行版，目标是解决两个具体问题：

1. **NVIDIA 显卡驱动开箱可用** —— 大多数 Arch 系发行版不预装 N 卡驱动，装完还要自己折腾
2. **对中文用户友好** —— 参考 CachyOS 的短板：中文输入法、字体、国内镜像源、中文本地化都缺默认配置

> **文档范围说明**：本套文档覆盖到「制作安装程序之前」的全部内容。
> 安装程序部分单独成篇，见后续文档。

---

## 当前进度

> 截至 **2026-09-19**。逐日的任务与实测记录在 [`docs/work/`](docs/work/)。

| 阶段 | 状态 |
|---|---|
| 构建环境与基线 | ✅ 未修改的 `releng` 构建出 ISO，QEMU（UEFI）引导到 `[root@archiso ~]#` |
| 自有 profile | ✅ `profile/` 进仓库并改名 MipLinux，产物 `miplinux-<日期>-x86_64.iso`（1.5 GiB，构建 2 分 08 秒） |
| 装系统链路 | ✅ `mipl target` + `mipl qemu --disk … --boot c`：装完能从盘重启（[05-测试方法](docs/knowledge/05-测试方法.md) 检查点 4） |
| 国内源与中文本地化 | 🚧 已并入主线：国内源、`zh_CN.UTF-8`、CJK fallback 规则、终端字体；**字体与输入法的包**还没进 `packages.x86_64` |
| NVIDIA 驱动 | 未开始（`packages.x86_64` 里还没有 `nvidia-open`） |
| 安装程序 | 未开始（P6 未定，见 [06-待定事项.md](docs/knowledge/06-待定事项.md)） |
| 桌面环境 / 品牌化 | 未开始 |

**「✅」表示本机实测过**，不代表用户拿到的成品已经具备该能力。每一阶段验到了第几个检查点，
以 [05-测试方法.md](docs/knowledge/05-测试方法.md) 的六个检查点为准。

---

## 文档导航

### 知识文档 `docs/knowledge/`

| 文档 | 内容 | 读者 |
|---|---|---|
| [01-概念模型.md](docs/knowledge/01-概念模型.md) | 构建发行版到底在做什么，核心心智模型 | **先读这个** |
| [02-环境与工具链.md](docs/knowledge/02-环境与工具链.md) | 三个环境的分工、每样工具是什么、本机现状 | 所有人 |
| [03-项目结构.md](docs/knowledge/03-项目结构.md) | profile 的每个文件是什么、为什么必须这么组织 | 所有人 |
| [04-架构决策.md](docs/knowledge/04-架构决策.md) | NVIDIA 与中文方案的具体技术决策 | 所有人 |
| [05-测试方法.md](docs/knowledge/05-测试方法.md) | 怎么验证 ISO 和安装结果 | 所有人 |
| [06-待定事项.md](docs/knowledge/06-待定事项.md) | 尚未决定的问题 | 所有人 |

### 工作文档 `docs/work/`

| 文档 | 内容 |
|---|---|
| [工作计划索引](docs/work/README.md) | 当前阶段与任务导航 |
| [2026-09-18.md](docs/work/2026-09-18.md) | 基线构建：容器、构建、QEMU 引导 |
| [2026-09-19.md](docs/work/2026-09-19.md) | 自有 profile 落地：构建管线、目标盘、改名 |
| [tech/](docs/work/tech/) | 可复现的技术操作步骤 |
| [tech/03-术语表.md](docs/work/tech/03-术语表.md) | 各工具是什么、彼此什么关系 |

### 脚本 `scripts/`

| 脚本 | 内容 |
|---|---|
| [mipl.sh](scripts/mipl.sh) | 项目操作台：环境自检、构建、QEMU 测试、进出构建容器。`sudo ./scripts/mipl.sh --help` |
| [mipl.fish](scripts/mipl.fish) | 同一操作台的 fish 入口（薄封装，逻辑不重写） |
| [baseline-build.sh](scripts/baseline-build.sh) | 构建本体，由 `mipl build` 调用；`--baseline` 走容器内原版 releng，`--profile` 指定其它 profile |
| [check-identity.sh](scripts/check-identity.sh) | 品牌一致性检查（**不需要 root**）：`./scripts/check-identity.sh` 扫 profile，`--iso out/miplinux-*.iso` 扫产物 |

常用几条（**使用Root权限运行**）：

```bash
sudo ./scripts/mipl.sh doctor                     # 换机器第一件事：环境自检
sudo ./scripts/mipl.sh build                      # 用仓库里的 profile/ 构建 ISO
sudo ./scripts/mipl.sh qemu                       # 启动 QEMU（只测 Live）
sudo ./scripts/mipl.sh stop                       # 关闭构建容器（用完别忘了）

# 装系统 / 验装后系统
sudo ./scripts/mipl.sh target                     # 建 out/target.qcow2
sudo ./scripts/mipl.sh qemu --disk target.qcow2   # 装：ISO 优先 + 挂盘
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c   # 装完：从盘启动
```

> **盘的 NVRAM 是单独一份**（`out/target.vars.fd`）：装系统时安装器把引导项写进
> NVRAM，UEFI 下决定这块盘能不能起来的就是它。所以有 `--disk` 时变量文件默认
> **保留**，而 ISO 测试用的 `out/OVMF_VARS.fd` 照旧每次刷新 —— 两边互不干扰，
> 测 ISO 不会把装好系统的引导项刷掉。`--boot c` 还会**不挂 ISO**：盘起不来时
> 你会看到明确的 `no bootable device`，而不是安静地又回到 Live 环境。

> **构建用的是哪份 profile：** 仓库里的 `profile/` 只读挂进容器的 `/profile`，
> 容器不保存副本 —— 所以「构建用的」和「git 里改的」永远是同一份。
> 构建挂了时跑 `sudo ./scripts/mipl.sh build --baseline`（用原版 releng）做对照，
> 就能分开「环境坏了」和「自己改坏了」。

> **为什么要有个脚本：** 两个人、两台机器、两种发行版（CachyOS 与 Arch），仓库路径还不一样。
> 手抄带绝对路径的长命令必然出错 —— Issue #7（文档写死家目录）和 #8
> （`-file=` 被换行拆开）都是这么来的。
> 所以脚本里的路径一律**从自身位置推导**，固件路径一律**运行时探测**。
>
> **为什么一律要 root：** 它要动构建容器、OVMF 固件和 `out/` 里的产物。
> 不提供「部分命令自动 sudo」——同一件事一会儿降权一会儿提权，出问题时
> 分不清是谁的权限在起作用。所以非 root 会被直接拒绝，而不是隐式提权。

---

## 三十秒版本

```
【源码】profile/                    ← 两位长期开发者用 git 协作
           │
【构建】systemd-nspawn 里的纯 Arch   ← 必须是 Arch：需要 pacman / pacstrap / mkinitcpio
           │  跑 mkarchiso
           ▼
【产物】miplinux-<版本>-x86_64.iso
           │
【测试】宿主机的 QEMU（KVM）         ← 必须能「引导」，nspawn 做不到
           │
【终验】真机                         ← NVIDIA 驱动和畸形分区 QEMU 测不了
```

**三句话概括：**

- `mkarchiso` 不是「打包工具」，它**先装出一个完整的 Arch 系统，再把系统压扁成一个只读镜像**。
- 发行版的「源代码」就是一堆配置文件，构建过程是**装配**而不是编译。
- 安装器**直到它装出来的系统能启动之前，都不算被测过**。

---

## 关键决策记录

已决定：

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 构建基底用官方 `archiso` + `releng` profile | 不 fork CachyOS-Live-ISO，避免绑定他人仓库 |
| D2 | 构建必须在纯净 Arch 环境中进行 | 见 D3 |
| D3 | 不使用宿主机 `pacman.conf` 的 `Include` 隐式解析 | 否则会静默引入宿主发行版的源 |
| D4 | 内核使用官方 `linux` | `nvidia-open` 硬绑官方内核，可零额外工作拿到预编译模块 |
| D5 | 不使用 CachyOS 内核或其仓库 | 与项目目标冲突，且引入外部仓库依赖 |
| D6 | 同一份包清单供 Live 环境与装后系统共用 | 防止「Live 里能用、装完不能用」的不一致 |
| D7 | 「可变」指滚动更新，交付形态为装到硬盘的传统发行版 | 已确认；安装器是必需组件 |
| D8 | NVIDIA 只需覆盖 Turing 及更新架构（两位长期开发者的显卡 —— Blackwell / Ada Lovelace —— 都落在范围内） | `nvidia-open` 即可满足，无需 legacy 分支 |
| D9 | 发行版名称定为 **MipLinux**；`iso_name="miplinux"`、`iso_label="MIPLINUX_<YYYYMM>"`、`iso_publisher` 带组织 URL、`iso_application="MipLinux Live/Install Medium"` | A6 改名落地。**引导项用的是构建时生成的时间戳 UUID**（`archisosearchuuid`），不是卷标 —— 所以改卷标不需要同步改引导配置 |

待定：（详见 [06-待定事项.md](docs/knowledge/06-待定事项.md)）

| 编号 | 待定问题 |
|---|---|
| P2 | 目标范围：自用 / 还是对外发布 |
| P3 | ISO 形态：在线安装 / 离线全量安装 |
| P4 | Live 环境形态：全功能桌面 / 开机直弹安装器的极简形态 |
| P5 | 桌面环境选型 |
| P6 | 安装程序方案 |
| P9 | 发行版本号制度：产物名沿用构建日期，是否改用语义版本 |

---

## 开发团队

**两位长期开发者**，宿主机发行版不同 —— 这正是 `scripts/` 里「路径从脚本自身位置推导」
和「固件路径运行时探测」的由来：

| 开发者 | 宿主发行版 | 显卡（决定 D8 的覆盖范围） |
|---|---|---|
| 望向天脉（[@LaT-SKY](https://github.com/LaT-SKY)） | CachyOS | Blackwell · RTX 50 系 |
| ieer040126（[@ieer040126](https://github.com/ieer040126)） | Arch Linux | Ada Lovelace · RTX 40 系 |

**宿主发行版与项目无关**：构建环境由 `systemd-nspawn` 提供，容器内是纯 Arch；
测试环境是宿主机的 QEMU。两人唯一必须保持一致的接口是包清单
[`profile/packages.x86_64`](profile/packages.x86_64)（见 [03-项目结构.md](docs/knowledge/03-项目结构.md)）。

**合并权限是单点**：`main` 受保护，PR 必须包含 code owner
（[@LaT-SKY](https://github.com/LaT-SKY)）的审核，见 [`.github/CODEOWNERS`](.github/CODEOWNERS)。

---

## 本仓库文档的取材来源

文档中的技术细节来自本次调研中的**实测验证**，而非记忆：

- 软件包版本与依赖关系：查询 Arch 官方仓库 API 实时数据
- `mkarchiso` 的行为：逐段阅读其源码
- 本机环境能力：在本机实际执行命令确认

验证时的快照数据集中在 [02-环境与工具链.md](docs/knowledge/02-环境与工具链.md) 的附录。

---

构建与测试环境详见 [02-环境与工具链.md](docs/knowledge/02-环境与工具链.md)。
