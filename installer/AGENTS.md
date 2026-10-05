---
description: MipLinux 安装器约定：backend 与 frontend 的职责切分、无界面优先的推进顺序、包清单唯一来源、测试怎么跑。
tags: [installer, python, electron, partitioning, uefi]
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
│   └── mipl_installer/   后端：不依赖界面技术栈，可被 CLI 与测试直接驱动
│       ├── pipeline.py   编排（`Plan` + 四个阶段 + 失败收尾）—— CLI 与前端共用
│       ├── events.py     进度事件流（文本 / JSON 行两种 reporter）
│       ├── queries.py    只读出口（`--print-*` 要的那份 JSON）—— 前后端唯一字段名来源
│       ├── options.py    语言 / 键盘 / 时区的名单与校验
│       ├── keymap_view.py 键位映射的解析与 include 展开（键盘页那张图的数据源）
│       ├── disk.py       分区、候选盘枚举、动手前的守卫
│       ├── network.py    Live 的网络状态与连网（`nmcli`）
│       └── data/         随包走的数据（M1 的临时目标包清单）
├── frontend/             Electron 前端：只画界面，不实现逻辑
│   ├── mipl-installer    Live 侧入口（Python 启动器），由 cage 拉起
│   ├── mipl-kiosk        kiosk 启动脚本（见 #79）
│   ├── theme/            主题解析与设备缩放的纯函数（Python）+ 单测
│   └── app/              Electron 应用（HTML/CSS/JS）；接口准据见 app/README.md
│       ├── main.js / preload.js   kiosk 窗口、启动参数、后端通道；不实现安装逻辑
│       ├── renderer/             12 个页面 + i18n + backend.js（真数据）/ mock.js（离屏自检）+ 时区名表
│       ├── design/color.json      唯一色源（断言脚本拿它与 08 对齐）
│       └── tools/                 check-tokens.py / check-contrast.py / probe-*.js
├── tests/                单测（test_*.py）+ Live 内排练脚本（*.sh）
```

（以 [installer-roadmap](../docs/work/installer-roadmap.md) 第 3 节为准，那里还写着构建集成。）

**包名不跟目录名走**：目录按角色分（backend / frontend / tests），Python 侧 import 名一律是
`mipl_installer`；前端是 HTML/CSS/JS，不走 Python import。这样「往哪放」和「怎么 import」互不牵连。

## 四条约定

- **逻辑先于外壳。** 先让「分区 → 装包 → 配置 → 写引导」在没有界面的情况下跑通，再套界面 ——
  这样界面方案的变更不会导致返工。`core` 必须能被 CLI 与测试直接驱动。
- **后端不依赖界面技术栈。** `backend/mipl_installer/` 里出现 `PySide6`/`Qt`，或反向去 import 前端模块（`renderer/`、Node 产物），都算破线；
  前端只订阅 `events.py` 的事件流、不实现逻辑。**新的前后端耦合层已随 #97 落地**（旧 `frontend/bridge/` 已随 #74 移出）：
  后端一侧是 `--print-*` 只读出口 + `events.JsonReporter` 的 JSON 行，前端一侧是 `main.js` 的 `child_process` 通道与
  `renderer/js/backend.js` 的数据适配；界面侧的接口准据是 [frontend/app/README.md](frontend/app/README.md) §7。
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

# 只读出口：看一眼运行环境，不动盘、不需要 root，stdout 上恰好一份 JSON
PYTHONPATH=installer/backend python3 -m mipl_installer --print-disks
PYTHONPATH=installer/backend python3 -m mipl_installer --print-keymap de    # 键位预览的数据源

# 界面侧验收：**不需要 root、不需要 Live**（Node 单测 + Electron 离屏 + Python 标准库）
node --test installer/frontend/app/tests/                              # 步骤表 / 状态机 / i18n 键 / token / 后端适配层
python3 installer/frontend/app/tools/check-tokens.py                   # V1：token ↔ color.json ↔ 08
python3 installer/frontend/app/tools/check-contrast.py                 # V2：对比度 46 组
python3 -m unittest discover -s installer/frontend/theme/tests -t installer/frontend/theme
MIPL_ELECTRON_BIN=electron node installer/frontend/app/tools/probe-render.js   # 8/12 步渲染 + 截图
```

（`MIPL_ELECTRON_BIN` 是给宿主机准备的：Live / 构建容器里 `electron` 在 PATH 上，宿主机上可以指向解包出来的 `electron44` 二进制。）

## 测试

分区逻辑**只在 `out/target.qcow2` 上跑**（根文件的安全红线）。端到端三段：

```bash
sudo ./scripts/mipl.sh target --force                     # 1. 建空目标盘
sudo ./scripts/mipl.sh qemu --disk target.qcow2           # 2. 进 Live，跑安装
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c  # 3. 检查点 4：从盘启动
```

**要看界面就走 `installer`，别用上面的 `qemu`** —— `installer` 自带 `-vga virtio`
（cage 要 KMS，`qemu` 的默认显卡不一定起得来），而且目标盘缺了才建、已有就复用：

```bash
sudo ./scripts/mipl.sh installer --serial console        # Live + 界面（串口可交互）
sudo ./scripts/mipl.sh installer --boot c                # 从盘启动验安装结果
```

**安装器直到它装出来的系统能启动之前，都不算被测过。**

## 两块的边界

`backend/mipl_installer/` 与 `tests/` 是安装器核心；`frontend/mipl-installer` 是 Live 侧入口（由 `cage` 拉起、由构建脚本拷进 `airootfs`）。
两块常由不同的人同时推进 —— 动手前先确认这两块各归哪个 issue（见根文件的「开工前置」）。
