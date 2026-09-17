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
├── tech/                    技术细节（可复现的操作步骤）
│   ├── 01-容器环境搭建.md
│   ├── 02-构建与QEMU测试.md
│   └── 03-术语表.md
└── scripts/
    └── baseline-build.sh    基线构建脚本（备选：手工执行）
```

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
