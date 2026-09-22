---
description: MipLinux 安装器约定：mipl_installer 与 Qt 前端的职责切分、无界面优先的推进顺序、包清单唯一来源。
tags: [installer, python, pyside6, partitioning, milestones]
---

# AGENTS.md — installer/ 安装器

v0.1 目标：**插上 U 盘、连着网，装出一个开箱能用（中文 + N 卡）、能长期滚动升级的系统。**
本文只写 `installer/` 特有的规矩；通用红线在[根文件](../AGENTS.md)。里程碑与验收见 [installer-roadmap](../docs/work/installer-roadmap.md)。

## 目录布局

```
installer/
├── mipl_installer/      核心逻辑：不依赖 Qt，可被 CLI 与测试直接驱动
├── mipl_installer_qt/   PySide6 前端：只画界面，不实现逻辑
├── bin/mipl-installer   入口，由 cage 拉起
└── tests/               无头测试：在 out/target.qcow2 上驱动 core
```

## 四条约定

- **逻辑先于外壳。** 先让「分区 → 装包 → 配置 → 写引导」在没有界面的情况下跑通，再套界面 ——
  这样界面方案的变更不会导致返工。M1 的 `core` 必须能被 CLI 与测试直接驱动。
- **`mipl_installer/` 不依赖 Qt。** 前端只订阅 `events.py` 的事件流，不实现逻辑；两边一起改就等于没有分层。
- **包清单唯一来源。** 不得在代码里另写一份「装什么包」的列表（D6）—— 两边各写各的，就会出现
  「Live 里中文能打字、装完不能」这类难以定位的问题。装后系统的清单放哪还挂在 P10，定案前先问。
- **源码与镜像内容分开放。** 构建脚本把 `installer/` 拷进 `airootfs`，`profile/` 里只放 systemd unit 与入口 ——
  改界面不需要动 `profile/`。

## 技术栈（D14）

Python 3 + PySide6/Qt6；Live 用 `cage` 做 kiosk 合成器；分区用 `python-pyparted`；
联网用 NetworkManager + `nmcli`；装后系统用 systemd-boot。选型全部落在官方源，不引入第三方仓库（D5）。

**v0.1 只做** UEFI + 整盘擦除 + GPT（ESP + ext4 单根）。
**不做**双系统、LUKS、BIOS 引导、btrfs 子卷、LVM、离线安装。

## 测试

分区逻辑**只在 `out/target.qcow2` 上跑**（根文件的安全红线）。端到端三段：

```bash
sudo ./scripts/mipl.sh target --force                     # 1. 建空目标盘
sudo ./scripts/mipl.sh qemu --disk target.qcow2           # 2. 进 Live，跑安装
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c  # 3. 检查点 4：从盘启动
```

**安装器直到它装出来的系统能启动之前，都不算被测过。**

## 两块的边界

`mipl_installer/` 与 `tests/` 是安装器核心；`bin/mipl-installer` 是 Live 侧入口（由 `cage` 拉起、由构建脚本拷进 `airootfs`）。
两块常由不同的人同时推进 —— 动手前先确认当日的分工（见根文件的「开工前置」）。
