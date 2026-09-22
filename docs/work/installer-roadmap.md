# MipLinux 安装器 · ROADMAP

> 最后更新：2026-09-21 · 技术栈定案见 [README](../../README.md) 决策表 **D14**
>
> 本文是**计划**：写「接下来做什么、怎么算做完」。已定案的结论在 `docs/knowledge/`，这里不重复推导。

---

## 1. 目标与边界

**一句话目标：插上 U 盘、连着网，装出一个开箱能用（中文 + N 卡）、能长期滚动升级的系统。**

| | 内容 |
|---|---|
| **v0.1 做** | UEFI 引导 · 整盘擦除 · GPT（ESP + ext4 单根）· Qt6 图形界面 · NetworkManager 联网 · systemd-boot |
| **v0.1 不做** | 双系统（保留已有系统）· LUKS · BIOS(legacy) · btrfs 子卷/快照 · LVM · 离线安装 · 多桌面选择 |

**三条不变的约束**（来自 [01-概念模型](../knowledge/01-概念模型.md) 与 [05-测试方法](../knowledge/05-测试方法.md)）：

1. **逻辑先于外壳** —— 「分区 → 装包 → 配置 → 写引导」这条链先在无界面状态下跑通，界面只是它的第二个调用者。
2. **不做无损 resize** —— 这是数据丢失风险最高的一类操作。v0.1 干脆不动已有分区表（整盘擦除）。
3. **分区测试只在虚拟盘上做** —— `out/target.qcow2`；真机用独立硬盘。

---

## 2. 技术栈（D14）

| 层 | 选型 | 一句话理由 |
|---|---|---|
| 语言 | Python 3 | Live 里本来就有（`reflector` 依赖它，与 `archinstall` 无关）；测试与迭代最省事 |
| 界面 | Qt6 + PySide6 | `qt6-base` 已因 `fcitx5-qt` 在 Live 里，`pyside6` 在官方仓库 |
| kiosk 合成器 | `cage` | 单窗口全屏的 Wayland 合成器，专为这种场景而生；与 P5 的用户桌面（niri / Hyprland）不冲突 |
| 分区 | `python-pyparted` | 官方 Python 绑定（`archinstall` 同栈）；后续做双系统沿用同一条路 |
| 联网 | NetworkManager + `nmcli` | Issue #30；安装器直接调命令行，不用自己写 D-Bus |
| 引导（装后系统） | systemd-boot | UEFI-only 下与 ISO 自身的 `uefi.systemd-boot` 一致，少维护一套 |

**明确排除：** C++/Qt6 + kpmcore（要编译、迭代慢，而它的强项「缩小已有分区」v0.1 用不上）、Rust / Go（静态二进制要自建仓库分发，撞 D5 与 P2 的成本）、纯 TUI（放弃图形体验）。

---

## 3. 代码布局与构建集成

```
installer/
├── backend/mipl_installer/  核心逻辑：不依赖 Qt，可被 CLI 与测试直接驱动
│   ├── disk.py              擦盘、建 GPT、ESP + root（pyparted）
│   ├── packages.py          pacstrap 驱动 + 读目标包清单
│   ├── configure.py         chroot 配置：locale / 用户 / fstab / keyring / mirrorlist
│   ├── boot.py              bootctl install + loader entry + efibootmgr
│   ├── events.py            进度事件流（前端只订阅它）
│   ├── util.py              外部命令与写文件的唯一出口（Runner，可注入替身）
│   ├── cli.py / __main__.py 无界面入口：`python3 -m mipl_installer`
│   └── data/                M1 的临时目标包清单（P10 定案后删）
├── frontend/                PySide6 前端：只画界面，不实现逻辑（M2 起有代码）
├── bin/mipl-installer       入口，由 cage 拉起
└── tests/                   单测 test_*.py + Live 内排练脚本（*.sh）
```

**包名不跟目录名走**：目录按角色分，import 名一律是 `mipl_installer`。

**构建集成：** 构建脚本把 `installer/` 拷进 Live 镜像的 `airootfs`，`airootfs` 里只放 systemd unit 与入口。**源码与镜像内容分开放** —— 改界面不需要动 `profile/`。

**为什么源码不拆去独立仓库：** ISO 构建要跨仓库取源码，就破坏了「产物 ⇄ commit 一一对应」。触发迁出的条件写在 §7。

---

## 4. 里程碑

**正在跑的线（2026-09-21 布置）：** 线 E → M0、线 D → M1、线 F → 真机与桌面；
分工与文件所有权见 [2026-09-21.md](2026-09-21.md)。

| # | 里程碑 | 目标 | 验收 | 依赖 |
|---|---|---|---|---|
| **M0** | 骨架与可测环境 | QEMU 里开机直进安装器界面（还没有真功能） | 界面能起来；安装器崩了能落回 TTY | 无 |
| **M1** | 逻辑闭环（无界面） | core 单独跑通「空盘 → 能启动的系统」 | 检查点 4 + 检查点 6 | 无 |
| **M2** | Qt6 前端最小可用 | 五个页面把 M1 的流程包起来 | QEMU 里全程图形化装完一次 | M1 |
| **M3** | 装后系统完整 | 中文、输入法、N 卡、国内源、桌面 | 检查点 5 + 真机 NVIDIA（两次） | P10、P5 |
| **M4** | 联网与镜像 | 安装器里选网、测速、写源 | QEMU 用户网络 + 真机 Wi-Fi | M2、P11 |
| **M5** | 发布准备 | 签名、校验和、Release、中文文档 | 一条命令产出可发布产物 | D10、D13 |

### M0 · 骨架与可测环境

先把「能起来、能测」这条路铺平，**不写任何真功能**。

- 建 `installer/`（§3 的布局）与入口 `bin/mipl-installer`
- Live 包清单加 `networkmanager`、`cage`、`qt6-wayland`、`pyside6`、`python-pyparted`
- `airootfs`：kiosk unit（`cage` + 安装器，`Restart=on-failure`）、NetworkManager 的无 GUI 配置；`getty` autologin **保留为兜底**
- `baseline-build.sh` 把 `installer/` 拷进 airootfs；`mipl.sh` 加 `installer` 子命令（建盘 + 启动 + 串口日志落 `out/`）

**验收：** 开机看到安装器窗口；`systemctl kill` 掉安装器后能落回 root TTY；`journalctl -u` 有日志。
**产出：** `docs/work/tech/04-安装逻辑与实测.md`（开篇先记启动链与渲染兜底）

### M1 · 逻辑闭环（无界面，最高优先）

最高风险的一段，且**与界面无关** —— 先做完它，界面才是「套壳」而不是「猜」。

- `disk.py`：`wipefs` 擦盘 → GPT → ESP 512 MiB + root 剩余（**盘尾留 1 MiB 给 GPT 备份表头**，压上去内核会丢分区）
- `packages.py`：`pacstrap` 到 `/mnt`；清单先读 `backend/mipl_installer/data/target-packages.x86_64`（临时，P10 落定后改指向唯一来源）
- `configure.py`：`fstab`（按 UUID）、locale、时区、用户 + sudo、`pacman-key --init/--populate`、mirrorlist 写死国内源、chroot 内 `mkinitcpio -P`
- `boot.py`：`bootctl install` + loader entry（只写需要显式覆盖的内核参数）+ `efibootmgr`

**验收：** `mipl qemu --disk target.qcow2 --boot c` 能从盘启动（检查点 4），进系统后确认 `cat /sys/module/nvidia_drm/parameters/modeset` 输出 `Y`，并使 `pacman -Syu` 成功（检查点 6）；全程只在 `out/target.qcow2` 上做。
**产出：** `docs/work/tech/04-安装逻辑与实测.md`

### M2 · Qt6 前端最小可用

页面流：欢迎（语言 / 键盘）→ 磁盘选择 + 擦盘二次确认 → 用户与密码 → 进度与日志 → 完成重启。

**进度来自 `core/events.py` 的事件流** —— Qt 层不许出现分区或装包逻辑，否则 M1 的测试就白做了。

**验收：** QEMU 里全程图形化装完一次。
**可后置：** Issue #22（等待界面小游戏）挂在进度页。

### M3 · 装后系统完整

目标包清单落位（P10）、`fcitx5` + CJK 字体、`nvidia-open` / `nvidia-utils`、国内源继承、桌面（P5 定案后）。

**验收：** 检查点 5，**真机 NVIDIA 验两次**（Live 能亮 / 装完能用）—— 09-19 就写下的纪律，别把第一次通过当成目标达成。
**产出：** `docs/work/tech/05-装后系统验证.md`

### M4 · 联网与镜像

`nmcli` 选网（有线自动、无线选择）、镜像测速与写入、`reflector` 策略（#18 / #23：**装后系统的 mirrorlist 不能被 reflector 覆盖**）、`archlinuxcn` 政策落定（P11）。

**验收：** QEMU 用户网络 + 真机 Wi-Fi；装后系统 `pacman -Syu` 仍走国内源。

### M5 · 发布准备

ISO 签名 + SHA256 + Release 说明模板 + 中文安装文档 + `v0.x.y` tag 流程（D10 / D13）。

**验收：** 一条命令产出「ISO + 校验和 + Release notes」。

---

## 5. 验证方法

跑法用现成的命令，逐条对应 [05-测试方法](../knowledge/05-测试方法.md) 的检查点：

| # | 验什么 | 怎么验 |
|---|---|---|
| S1 | 分区 | `pyparted` 在 `out/target.qcow2` 上擦盘 + 建 GPT/ESP/root，重复执行结果一致 |
| S2 | 界面能起来 | QEMU（无 GPU）里 `cage` + Qt6 全屏可见；不亮时 `WLR_RENDERER=pixman` 兜底 |
| S3 | 端到端 | `mipl.sh target --force` → `qemu --disk` → 安装 → `qemu --disk … --boot c` |
| S4 | 联网 | QEMU 用户网络（有线）+ 真机 Wi-Fi，都走 `nmcli` |
| S5 | 装后系统 | `guestmount` 静态检查 + 检查点 5 + 真机 NVIDIA |
| S6 | 发布 | 签名与校验和可复算；Release notes 里写明 ISO 日期与语义号对应关系（D13） |

每一步的实测结果写进 `docs/work/tech/`，**不要把「跑过一次」当成「验过」**。

---

## 6. 失败模式清单

写在这里，是为了让每条都有对应的兜底或验收，而不是等它发生。

| 失败模式 | 兜底 / 验收 |
|---|---|
| NVRAM 写不进（主板满 / 只读） | 复制到 `\EFI\BOOT\BOOTX64.EFI`（可移除介质路径），并在界面上说明 |
| 装包中途断网 | 重试；失败不留半成品（重来一遍，而不是在残骸上继续） |
| `pacman-key` 没初始化 | 检查点 6 会暴露 —— M1 的 `configure.py` 必须做 `--init` / `--populate` |
| `reflector` 覆盖 mirrorlist | 装后系统不启用它的 timer（#23 已经踩过） |
| 安装器崩溃 | `Restart=on-failure` + `getty` 兜底；日志看 `journalctl -u mipl-installer` |
| QEMU 无 GPU，Qt6 起不来 | `WLR_RENDERER=pixman` 软件渲染（M0 先验） |
| 中文 SSID / 密码 | `nmcli` 走 UTF-8；界面 CJK 字体已在 Live 清单里 |
| 4K 扇区 / NVMe | 用 `pyparted` 的对齐参数；QEMU 里挂一块 4K 盘验一次 |

---

## 7. 仓库与发布

- **源码在主仓库** `installer/`（理由见 §3）。
- **`MipLinux-Installer`**（org 下那个空仓库）改为**发布与用户文档仓库**：放 Release、nightly ISO 链接、中文安装文档。
- **触发迁出为独立源码仓库的条件**（到了再说）：安装器要独立分发（给任意 Arch 用的工具）／出现 MipLinux 之外的贡献者／需要与 ISO 解耦的版本节奏。届时用 submodule 或打包，**不要复制源码**。

---

## 8. 开放问题（不阻塞 M0 / M1）

| 问题 | 影响 | 何时必须落 |
|---|---|---|
| [P10](../knowledge/06-待定事项.md) 目标包清单放哪 | M3 的装包输入 | M3 前 |
| [P5](../knowledge/06-待定事项.md) niri / Hyprland | M3 的桌面 | M3 前 |
| [P11](../knowledge/06-待定事项.md) `archlinuxcn` 政策 | 装后系统的 `pacman.conf` | M4 前 |
| Live 是否裁 `fcitx5*` / `archinstall` | ISO 体积 | M0 |

**协调：** 有一条正在移除 `iwd` 的分支尚未合入。等它落地后再改 `packages.x86_64` 与 `airootfs` 的网络配置，
避免同一批文件两边改重。

---

## 9. 与其它文档的关系

| 文档 | 关系 |
|---|---|
| [README 决策表](../../README.md) | D14 是本文的技术栈来源 |
| [knowledge/06-待定事项.md](../knowledge/06-待定事项.md) | P6 的推导过程与排除项 |
| [knowledge/05-测试方法.md](../knowledge/05-测试方法.md) | 六个检查点与安装器端到端验证 |
| [knowledge/03-项目结构.md](../knowledge/03-项目结构.md) | `installer/` 在仓库里的位置 |
| [knowledge/04-架构决策.md](../knowledge/04-架构决策.md) | NVIDIA 与中文两部分的实现依据 |
