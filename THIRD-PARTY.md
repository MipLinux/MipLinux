# 第三方组件与许可

> 本文记录 MipLinux 随仓库、ISO 与装后系统分发的第三方组件的许可边界。
> 它是工程合规清单，不是法律意见；对外发布前的法务确认按 [D10](docs/knowledge/07-决策表.md) 执行。

MipLinux 自己的代码与配置以 **GPL-3.0-or-later** 授权（[README 的「许可」小节](README.md#许可)）；
品牌素材按 **CC BY-SA 4.0** 单独授权（[assets/README.md](assets/README.md)）。

## 先分清三种关系

| 关系 | 含义 | 例子 |
|---|---|---|
| 可合并 / 链接 | 许可与 GPL-3.0 兼容，可以组成同一作品 | MIT、BSD、Apache-2.0、OFL、LGPL-3.0、GPL-3.0 |
| 聚合分发 | 独立作品，只放在同一介质上，不合并、不链接 | NVIDIA `nvidia-utils`、可选的 Spotify / Todoist |
| 构建输入 | 只参与构建，不随产物分发 | 构建工具、测试依赖 |

**聚合不是合并。** GPLv3 §5 允许把 GPL 作品与独立作品放在同一介质上；一旦把它们合并成一个二进制 / 包，
或者让 GPL 代码直接链接专有库，就不再是聚合。NVIDIA EULA 2.9 也禁止让 NVIDIA 软件
“become subject to an open source license”（EULA 自身列出的其他许可组件除外）。所以 `nvidia-utils` 必须保持独立包、独立文件，
不能塞进 `caelestia-*` 或 MipLinux 的 GPL 包。

## 每一类的清单在哪

| 类别 | 权威清单 |
|---|---|
| 前端 vendored 资源 | [vendor/README.md](installer/frontend/app/vendor/README.md) —— 版本、来源 URL、sha256、许可原件逐个列在一起 |
| `profile/`：派生自上游的构建源 | [profile/PROFILE.md](profile/PROFILE.md) —— 上游是 archiso 的 releng profile（GPL-3.0-or-later），版本、拷贝日期与有意差异都登记在那里 |
| 产物里再分发的软件包 | [Live 清单](profile/packages.x86_64) · [装后清单](installer/backend/mipl_installer/data/target-packages.x86_64) —— 包来自 Arch 官方仓库与 `[archlinuxcn]`，各包保留自己的许可，由 `pacman` 装到 `/usr/share/licenses/`；源码在 Arch 官方仓库与 ABS |
| Caelestia 桌面组件 | [MipLinux/Caelestia-dotfiles](https://github.com/MipLinux/Caelestia-dotfiles)、[MipLinux/Caelestia-shell](https://github.com/MipLinux/Caelestia-shell)、[MipLinux/Caelestia-cli](https://github.com/MipLinux/Caelestia-cli) 的 `NOTICE.md` 与上游仓库 |
| 许可证据 | [2026-10-17-第三方许可核对.md](docs/archive/2026-10-17-第三方许可核对.md) —— libqalculate / lm_sensors 的版本、commit、源码头与 SPDX 判断 |
| 源码提供 | 本文[「源码提供」](#源码提供)一节 |

## 与 GPL 兼容的组件

这些组件可以按各自许可与 GPL 作品合并 / 链接；仍要保留版权、许可与 NOTICE。
MipLinux 自有代码是 GPL-3.0-or-later，Caelestia 是 GPL-3.0-only；两者兼容，组合分发按 GPLv3 履行。
MipLinux 的 “or later” 不改变 Caelestia 的 “only”。

| 组件 | 许可 | 备注 |
|---|---|---|
| Caelestia dots（[MipLinux/Caelestia-dotfiles](https://github.com/MipLinux/Caelestia-dotfiles)） | GPL-3.0-only | 上游 Caelestia；见 fork 的 NOTICE |
| Caelestia shell / CLI（[MipLinux/Caelestia-shell](https://github.com/MipLinux/Caelestia-shell) / [Caelestia-cli](https://github.com/MipLinux/Caelestia-cli)） | GPL-3.0-only | 上游 AUR 元数据；三个 fork 的版本需对齐 |
| Quickshell | LGPL-3.0 | Caelestia shell 动态链接；LGPLv3 §3 允许转 GPLv3 |
| Qt6 | LGPL-3.0（部分 GPL-3.0） | 动态链接；Arch 包 |
| [`libqalculate`](https://archlinux.org/packages/extra/x86_64/libqalculate/) | GPL-2.0-or-later（上游头文件） | Arch 元数据写 `GPL-2.0-only`；见下方「依赖审计」 |
| [`lm_sensors`](https://archlinux.org/packages/extra/x86_64/lm_sensors/) | LGPL-2.1-or-later（上游头文件） | Arch 元数据写 `GPL-2.0-only OR LGPL-2.1-only`；选 LGPL 分支 |
| `qt6-m3shapes-git` | Apache-2.0 | 与 GPLv3 兼容 |
| 字体（Material Symbols） | Apache-2.0 | 与 GPLv3 兼容 |
| 字体（Rubik、Cascadia） | OFL | 随软件分发，字体自身仍受 OFL |
| `cage`（Live kiosk） | MIT | 已打触摸补丁，见下表 |

本表只列与当前桌面 / 许可判断直接相关的组件；其余包按[「每一类的清单在哪」](#每一类的清单在哪)
与 Arch 元数据各自保留许可。

### 依赖审计：`libqalculate` 与 `lm_sensors`

Caelestia shell 是 GPL-3.0-only，并直接链接 `libqalculate`（见
[plugin/CMakeLists.txt](https://github.com/caelestia-dots/shell/blob/main/plugin/CMakeLists.txt)）。
Arch 的 `libqalculate` 元数据写 **GPL-2.0-only**；如果按字面理解，它会和 GPL-3.0-only 冲突。
上游源码头文件写的是 “either version 2 of the License, or (at your option) any later version”，
即 **GPL-2.0-or-later**，可以升级到 GPLv3。Fedora 的 spec 与 Homebrew 的 formula 也标注
`GPL-2.0-or-later`；版本、commit 与文件路径见[许可证据](docs/archive/2026-10-17-第三方许可核对.md)。
`lm_sensors` 同理：Arch 元数据写 only，上游头文件是 **LGPL-2.1-or-later**，选 LGPL 分支即可与 GPLv3 兼容。

处置：继续使用 Arch 官方二进制包，不自行重建；在
[docs/archive/2026-10-17-第三方许可核对.md](docs/archive/2026-10-17-第三方许可核对.md)
留存对应版本、commit、文件路径与 SPDX 判断依据。
**不能只信 Arch 元数据；也不为了修元数据去维护一份自己的构建。**

## 独立专有组件（只聚合）

| 组件 | 许可 | 分发条件 |
|---|---|---|
| [`nvidia-utils`](https://archlinux.org/packages/extra/x86_64/nvidia-utils/)（用户态驱动、GSP 固件、EGL / GL / Vulkan 库） | NVIDIA Driver License Agreement（`LicenseRef-NVIDIA-Driver-License-Agreement`） | EULA 1.1(d)：随 OSI 许可的 Linux 内核分发；二进制不得修改；协议随附。NVIDIA 专有部分无源码义务；包内其他许可组件按各自许可。 |
| Spotify / Todoist 等可选应用 | 各自专有许可 | 只在用户选择安装时分发；不与 GPL 包合并。 |

本次核对的 EULA 版本是 **2025-02-25**；版本、路径与 sha256 见
[许可证据](docs/archive/2026-10-17-第三方许可核对.md)。

**NVIDIA 用户态组件的边界：**

- 优先使用 Arch 官方 `nvidia-utils` / `nvidia-open` 二进制包；[`nvidia-utils` 的 PKGBUILD](https://gitlab.archlinux.org/archlinux/packaging/packages/nvidia-utils/-/blob/main/PKGBUILD) 明确 `options=('!strip')`，不 strip 用户态二进制。自建包 / 重打包时保持 `!strip`，不 patch、不重打包。
- 保留 `/usr/share/licenses/nvidia-utils/LICENSE`，不要为了缩小 ISO 剥离许可文件；发布时记录包版本、许可证文件 sha256，确保接收者可取得 EULA。
- 不修改二进制；不逆向 / 反编译；保留版权与专有通知。
- 不把 `nvidia-utils` 放进 `caelestia-*`、`mipl-*` 等 GPL 包，不静态链接，不把 ISO 整体标成 GPL-3.0。
- 安装器不把“接受 NVIDIA EULA”设为使用 Caelestia 的前提；NVIDIA 组件可移除、可替换（核显 / nouveau）。
- EULA 2.8：GeForce / TITAN 软件仅授权用于用户自有的相应硬件，不授权数据中心；这条不扩大到所有企业级 GPU。
- EULA 2.11：indemnity / 抗辩义务不限于故意违反；正常使用引发的特定争议也可能涉及，具体看合同主体、因果与适用法律。
- EULA 11 / 12：NVIDIA 累计责任上限为 5 美元（以适用法律允许为前提）；许可证接受者没有对等上限，不能把 5 美元当作 MipLinux 的最高责任。
- 正式公开发行前，建议向 NVIDIA `driver-licensing@nvidia.com` 书面确认再分发 / ISO 集成方案。

## NVIDIA 内核模块（不是专有组件）

[`nvidia-open`](https://archlinux.org/packages/extra/x86_64/nvidia-open/) 是 **MIT AND GPL-2.0-only**，不是 `nvidia-utils` 那种专有用户态组件：

- 内核模块与 Linux 内核（GPL-2.0-only）兼容；与 GPL-3.0 的用户态 Caelestia 分处内核 / 用户态，不构成同一作品。
- 预装 `nvidia-open` 不等于整栈开源：内核模块是 MIT/GPL-2.0，用户态 `nvidia-utils` 仍是专有。
- 分发二进制时保留 MIT 通知；GPL-2.0 部分按 GPLv2 §3 提供源码或书面 offer。
- ISO / 装后系统保留 `/usr/share/licenses/nvidia-open/LICENSE`。
- 源码对应 ISO 中 `nvidia-open` 的版本；上游：<https://github.com/NVIDIA/open-gpu-kernel-modules>。
  发布时把精确 tag / commit 写进[「源码提供」](#源码提供)。

## Caelestia 组件

Caelestia 由三部分组成：MipLinux/Caelestia-dotfiles 的 dotfiles fork、MipLinux/Caelestia-shell、MipLinux/Caelestia-cli。
三个 fork 均以 GPL-3.0-only 分发；Quickshell 是 LGPL-3.0；Qt6 是 LGPL-3.0。它们与 GPL 兼容，但仍有源码与通知义务：

- 三个 fork 的 `main` 跟踪上游，只保留最小的 MipLinux 文档 / 许可声明；功能改动放 `mip` 分支 / tag，发布时记录上游 base commit。
  dots / shell / cli 与 Quickshell 的 pin 一起对齐，不单独升级其中一个。
- 保留各仓库的 `LICENSE`、版权声明与 `NOTICE`；修改过的文件标明 MipLinux 的改动。
- 发布 ISO / 二进制包时，提供对应 commit / tag 的源码与构建脚本（CMake、PKGBUILD、QML 资源）。
- 品牌化改动中的代码 / 配置按 GPL-3.0-only 发布；品牌素材本身按 CC BY-SA 4.0，不与代码许可混写。
- `caelestia-cli` 的打包要确认 GPL 全文随包安装；`caelestia-shell` 的 PKGBUILD 已安装 `LICENSE`，
  CLI 的 wheel 安装路径要单独核对。
- Caelestia 名称 / 标识不随 GPL 授予；对外产品名用 MipLinux，保留 “based on Caelestia” 的 attribution。

## 源码提供

GPL / LGPL 的义务不因“包来自 Arch 仓库”而消失。发布 ISO 或二进制包时，按下面的方式提供对应源码：

| 组件 | 源码 | 方式 |
|---|---|---|
| MipLinux 自有代码 / 配置 | 本仓库对应 commit / tag | 随发布页提供；ISO 构建脚本在 `scripts/`、`profile/`、`installer/` |
| Caelestia forks | [Caelestia-dotfiles](https://github.com/MipLinux/Caelestia-dotfiles)、[Caelestia-shell](https://github.com/MipLinux/Caelestia-shell)、[Caelestia-cli](https://github.com/MipLinux/Caelestia-cli) 对应 commit | 发布页链接 + 构建时记录 commit / 上游 base |
| Quickshell / Qt6 | 上游 / Arch 源码 | 动态链接；LGPL 源码与可重链接条件 |
| `nvidia-open` | NVIDIA 上游对应 tag / commit | GPLv2 §3(b) 书面 offer，有效期 3 年；或随附源码 |
| `nvidia-utils` | 无（专有部分） | 不提供专有部分源码；提供 EULA；包内其他许可组件按各自许可 |
| 其他 GPL / LGPL 包 | Arch ABS / 上游 | 发布页给源码入口；GPLv2 包按 §3 提供 offer |

**做法：** 在发布页放一份 `SOURCE-OFFER`（或本文的固定锚点），写清每个 GPL / LGPL 组件的名称、版本、
源码 URL / commit、构建脚本；ISO 内保留 `/usr/share/licenses/`。GPLv2 组件（如 `nvidia-open`）
的书面 offer 自分发之日起 3 年内有效。

## 我们改过的第三方程序

| 程序 | 许可 | 我们做了什么 |
|---|---|---|
| cage v0.3.1 | MIT（Copyright (c) 2018-2020 Jente Hidskes；Copyright (c) 2019 The Sway authors） | Live 的 kiosk 合成器：套 [cage-0.3.1-enable-tap.patch](scripts/patches/cage-0.3.1-enable-tap.patch) 打开触摸板轻点，编译成 `mipl-cage` 装进 ISO |
| Caelestia（fork） | GPL-3.0-only | CI、文档与后续品牌化改动；代码改动在 fork 中公开，按 GPL-3.0-only 发布 |

## 依据

- GNU GPL v3：<https://www.gnu.org/licenses/gpl-3.0.html>
- GNU GPL v2：<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>
- GNU LGPL v3：<https://www.gnu.org/licenses/lgpl-3.0.html>
- GPL 兼容性列表：<https://www.gnu.org/licenses/license-list.html>
- NVIDIA Driver License Agreement：ISO 内 `/usr/share/licenses/nvidia-utils/LICENSE`，发布时随包提供；
  官方英文 <https://www.nvidia.com/en-us/drivers/geforce-license/>，中文
  <https://www.nvidia.cn/drivers/nvidia-license/>。

## 发布前检查

- [ ] ISO 与装后系统都保留 `/usr/share/licenses/`（尤其 `nvidia-utils`、`nvidia-open`）。
- [ ] `SOURCE-OFFER` 覆盖所有 GPL / LGPL 组件；`nvidia-open` 有 GPLv2 书面 offer。
- [ ] Caelestia fork 的 `NOTICE` 与 `CONTRIBUTING` 许可段一致（GPL-3.0-only）。
- [ ] `nvidia-utils` 未被合并进 GPL 包；安装器未把 EULA 接受设为使用 Caelestia 的前提。
- [ ] NVIDIA 二进制未 strip / patch；包版本与许可证文件 sha256 已记录。
- [ ] EULA 2.8 / 2.9 / 2.11 / 11–12 已由法务确认；正式发布前向 `driver-licensing@nvidia.com` 书面确认。
- [ ] `libqalculate` / `lm_sensors` 的 or-later 证据已留档（[docs/archive/2026-10-17-第三方许可核对.md](docs/archive/2026-10-17-第三方许可核对.md)）；继续使用 Arch 官方二进制包，不自行重建。
- [ ] 可选专有应用（Spotify / Todoist 等）在清单中标注，不与 GPL 包合并。
- [ ] 对外发布前完成 D10 要求的法务确认（Secure Boot §6、商标）。
