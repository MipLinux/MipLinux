---
description: MipLinux 安装器约定：backend 与 frontend 的职责切分、无界面优先的推进顺序、包清单唯一来源、测试怎么跑。
tags: [installer, python, pyside6, partitioning, uefi]
---

# AGENTS.md — installer/ 安装器

一句话目标：**插上 U 盘、连着网，装出一个开箱能用（中文 + N 卡）、能长期滚动升级的系统。**

本文只写 `installer/` 特有的规矩；通用红线在[根文件](../AGENTS.md)。

> **范围、技术栈、里程碑都不在这里** —— 它们是计划，随版本走，写进代码目录第二天就可能过期。
> 唯一来源是 [installer-roadmap](../docs/work/installer-roadmap.md)：当前版本的边界见第 1 节，
> 技术栈（D14）见第 2 节，里程碑与验收见第 4 节。本文只记**不随版本变**的约定。

## 目录布局

```
installer/
├── backend/
│   └── mipl_installer/   后端：不依赖 Qt，可被 CLI 与测试直接驱动
│       └── data/         随包走的数据（M1 的临时目标包清单）
├── frontend/             PySide6 前端：只画界面，不实现逻辑（M2 起有代码）
├── bin/mipl-installer    Live 侧入口，由 cage 拉起（线 E）
└── tests/                单测（test_*.py）+ Live 内排练脚本（*.sh）
```

（以 [installer-roadmap](../docs/work/installer-roadmap.md) 第 3 节为准，那里还写着构建集成。）

**包名不跟目录名走**：目录按角色分（backend / frontend / tests），import 名一律是
`mipl_installer`（前端将来是 `mipl_installer_qt`）—— 这样「往哪放」和「怎么 import」互不牵连。

## 四条约定

- **逻辑先于外壳。** 先让「分区 → 装包 → 配置 → 写引导」在没有界面的情况下跑通，再套界面 ——
  这样界面方案的变更不会导致返工。`core` 必须能被 CLI 与测试直接驱动。
- **后端不依赖 Qt。** `backend/mipl_installer/` 里出现 `PySide6`/`Qt` 的 import 就算破线；
  前端只订阅 `events.py` 的事件流、不实现逻辑（接口见 [frontend/README.md](frontend/README.md)）。
- **包清单唯一来源。** 不得在代码里另写一份「装什么包」的列表（D6）—— 两边各写各的，就会出现
  「Live 里中文能打字、装完不能」这类难以定位的问题。装后系统的清单放哪见 [P10](../docs/knowledge/06-待定事项.md)。
- **源码与镜像内容分开放。** 构建脚本把 `installer/` 拷进 `airootfs`，`profile/` 里只放 systemd unit 与入口 ——
  改界面不需要动 `profile/`。

## 怎么跑

```bash
# 单测：不需要 root、不需要 Live（后端在 sys.path 上由 tests/__init__.py 自己接好）
python3 -m unittest discover -s installer/tests -t installer

# 直接驱动 CLI（Live 里由 tests/live-rehearsal.sh 代劳）
PYTHONPATH=installer/backend python3 -m mipl_installer --disk /dev/vda --dry-run
```

## 测试

分区逻辑**只在 `out/target.qcow2` 上跑**（根文件的安全红线）。端到端三段：

```bash
sudo ./scripts/mipl.sh target --force                     # 1. 建空目标盘
sudo ./scripts/mipl.sh qemu --disk target.qcow2           # 2. 进 Live，跑安装
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c  # 3. 检查点 4：从盘启动
```

**安装器直到它装出来的系统能启动之前，都不算被测过。**

## 两块的边界

`backend/mipl_installer/` 与 `tests/` 是安装器核心；`bin/mipl-installer` 是 Live 侧入口（由 `cage` 拉起、由构建脚本拷进 `airootfs`）。
两块常由不同的人同时推进 —— 动手前先确认当日的分工（见根文件的「开工前置」）。
