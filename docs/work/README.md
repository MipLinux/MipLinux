# docs/work · 工作计划

按阶段组织的工作任务与技术细节。

> `docs/knowledge/` 存放**已经确定的结论**（概念、决策、原理）。
> `docs/work/` 存放**待执行与正在执行的工作**。

---

## 目录结构

```
docs/work/
├── README.md                本文件，索引
├── 2026-09-18.md            当日任务清单：基线构建
├── 2026-09-19.md            当日任务清单：自有 profile 落地
└── tech/                    技术细节（可复现的操作步骤）
    ├── 01-容器环境搭建.md
    ├── 02-构建与QEMU测试.md
    └── 03-术语表.md
```

脚本在仓库根目录的 `scripts/`，不在 `docs/` 下：

```
scripts/
├── mipl.sh                  项目操作台（doctor / build / qemu / shell / stop …）
├── mipl.fish                同上的 fish 入口，只是转发
├── baseline-build.sh        构建本体（被 mipl build 调用）
└── check-identity.sh        品牌一致性检查（**不需要 root**：profile 与产物两种模式）
```

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
| `sudo ./scripts/mipl.sh clean` | 删 `OVMF_VARS*`；`--iso` 连 ISO 一起删；`--disk` 删目标盘及其 NVRAM（都不可逆，会先问一句） |
| `./scripts/check-identity.sh` | **不需要 sudo**：扫 `profile/` 里有没有没改干净的旧品牌名；加 `--iso out/miplinux-*.iso` 扫产物（卷标 / publisher / application / 引导菜单文本） |

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
| ③ 国内源与中文本地化 | 见 9.19 线 C | 🚧 `airootfs` 的配置已并入主线；字体与输入法的**包**待补，装后系统的源继承待解（Issue #23） |
| ④ NVIDIA 驱动 | — | 未开始。**真机验证是最高风险项，应尽早做** |
| ⑤ 安装程序 | — | 未开始（P6 待定，见 [06-待定事项](../knowledge/06-待定事项.md)） |

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
| 项目概览与决策记录 | [README.md](../../README.md) |
| 概念模型 | [knowledge/01-概念模型.md](../knowledge/01-概念模型.md) |
| 环境与工具链 | [knowledge/02-环境与工具链.md](../knowledge/02-环境与工具链.md) |
| 项目结构 | [knowledge/03-项目结构.md](../knowledge/03-项目结构.md) |
| 架构决策 | [knowledge/04-架构决策.md](../knowledge/04-架构决策.md) |
| 测试方法 | [knowledge/05-测试方法.md](../knowledge/05-测试方法.md) |
| 待定事项 | [knowledge/06-待定事项.md](../knowledge/06-待定事项.md) |
