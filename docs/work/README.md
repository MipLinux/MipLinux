# docs/work · 工作计划

按阶段组织的工作任务与技术细节。

> `docs/knowledge/` 存放**已经确定的结论**（概念、决策、原理）。
> `docs/work/` 存放**待执行与正在执行的工作**。

---

## 目录结构

```
docs/work/
├── README.md                本文件，索引
├── 2026-09-18.md            当日任务清单
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
└── baseline-build.sh        基线构建（被 mipl build 调用）
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
| `sudo ./scripts/mipl.sh build` | 下载 bootstrap → 解压 → 构建 ISO |
| `sudo ./scripts/mipl.sh qemu` | 刷新 `OVMF_VARS` 并启动 QEMU |
| `sudo ./scripts/mipl.sh shell` | 进入 nspawn 构建容器 |
| `sudo ./scripts/mipl.sh stop` | 关闭容器（**用完别忘了**，见 Issue #4） |
| `sudo ./scripts/mipl.sh -n <命令>` | 只打印将执行的命令，不做任何改动 |

三个设计约束：**一律 root 且不隐式提权**、**路径全部从脚本自身位置推导**
（两台机器的仓库路径不同）、**固件路径靠探测**（Arch 与 Fedora 不一样）。
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

## 当前阶段：基线构建

**目标：** 用未修改的 `releng` profile 构建出一个 ISO，并在 QEMU 中引导成功。

**为什么先做这个：** 见 [01-概念模型.md](../knowledge/01-概念模型.md) 第 7.1 节「产物决定一切」。

没有这条基线，后续每一次失败都无法区分是「环境问题」还是「自己改坏了」。

**详细步骤：**

1. [tech/01-容器环境搭建.md](tech/01-容器环境搭建.md) —— 建立纯净 Arch 构建环境
2. [tech/02-构建与QEMU测试.md](tech/02-构建与QEMU测试.md) —— 构建 ISO 并验证引导

**背景知识（若对工具不熟悉）：** [tech/03-术语表.md](tech/03-术语表.md)

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
