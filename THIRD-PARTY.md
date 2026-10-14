# 第三方组件与许可

MipLinux 自己的代码与配置以 **GPL-3.0-or-later** 授权（[README 的「许可」小节](README.md#许可)）；
品牌素材按 **CC BY-SA 4.0** 单独授权（[assets/README.md](assets/README.md)）。

## 每一类的清单在哪

| 类别 | 权威清单 |
|---|---|
| 前端 vendored 资源 | [vendor/README.md](installer/frontend/app/vendor/README.md) —— 版本、来源 URL、sha256、许可原件逐个列在一起 |
| `profile/`：派生自上游的构建源 | [profile/PROFILE.md](profile/PROFILE.md) —— 上游是 archiso 的 releng profile（GPL-3.0-or-later），版本、拷贝日期与有意差异都登记在那里 |
| 产物里再分发的软件包 | [Live 清单](profile/packages.x86_64) · [装后清单](installer/backend/mipl_installer/data/target-packages.x86_64) —— 包来自 Arch 官方仓库与 `[archlinuxcn]`，各包保留自己的许可，由 `pacman` 装到 `/usr/share/licenses/`；源码在 Arch 官方仓库与 ABS |

## 我们改过的第三方程序

| 程序 | 许可 | 我们做了什么 |
|---|---|---|
| cage v0.3.1 | MIT（Copyright (c) 2018-2020 Jente Hidskes；Copyright (c) 2019 The Sway authors） | Live 的 kiosk 合成器：套 [cage-0.3.1-enable-tap.patch](scripts/patches/cage-0.3.1-enable-tap.patch) 打开触摸板轻点，编译成 `mipl-cage` 装进 ISO |

## 相容性

随附的第三方许可都与主许可 GPL-3.0-or-later 相容：MIT 是宽松许可；
OFL 允许字体随任意软件分发，字体自身仍受 OFL 约束。产物里的 Arch 软件包属聚合分发，各包许可互不影响。
