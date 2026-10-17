# 第三方组件与许可

> 合规总入口。逐包许可证不在这里手工维护：构建时由 `scripts/gen-sbom.py` 从包元数据生成 SPDX SBOM。
> 本文只回答：哪些组件在分发、哪些是计划、专有组件在哪里、源码怎么交付。

## 范围与状态

| 状态 | 组件 | 处理 |
|---|---|---|
| 已分发 | Live / 装后清单里的 Arch 包；`nvidia-utils`；`nvidia-open` | 许可证由 SBOM 生成；专有 / 源码例外见下文 |
| 计划引入 | Caelestia-dotfiles / shell / cli；Quickshell / Qt6 | 尚未进入 ISO；接入时补 SBOM 与源码安排 |
| 可选 | Spotify / Todoist 等 | 只在用户选择安装时分发；不默认进入镜像 |

## 专有与源码

- **`nvidia-utils`**：NVIDIA 用户态专有组件；EULA、再分发条件与二进制完整性见 [NVIDIA.md](docs/licensing/NVIDIA.md)。
- **`nvidia-open`**：内核模块，`MIT AND GPL-2.0-only`，不是专有组件；源码按 GPLv2 走 [SOURCE-OFFER.md](docs/licensing/SOURCE-OFFER.md)。
- **GPL / LGPL 的 Arch 包**：源码交付方式见 [SOURCE-OFFER.md](docs/licensing/SOURCE-OFFER.md)。SBOM 只是许可证清单，不是源码交付。
- **其他 `custom` 许可证**：只有带独立版权信息 / 自定义许可证的包才在 `/usr/share/licenses/<pkg>/` 下放文件；通用 SPDX 文本在 `licenses` 包的 `/usr/share/licenses/spdx/`。详见 [docs/licensing/README.md](docs/licensing/README.md)。

## 文件

| 文件 | 内容 |
|---|---|
| [docs/licensing/NVIDIA.md](docs/licensing/NVIDIA.md) | EULA 与分发限制 |
| [docs/licensing/SOURCE-OFFER.md](docs/licensing/SOURCE-OFFER.md) | GPLv2 / GPLv3 / LGPL 的源码交付 |
| [docs/licensing/README.md](docs/licensing/README.md) | SBOM 生成、Arch 许可证路径、分发状态 |
| `docs/licensing/sbom.spdx.json` | 构建时生成；不手工维护 |
| [docs/archive/2026-10-17-第三方许可核对.md](docs/archive/2026-10-17-第三方许可核对.md) | `libqalculate` / `lm_sensors` 的版本、commit 与 SPDX 证据 |

## 生成

```sh
python3 scripts/gen-sbom.py --pkglist profile/packages.x86_64 \
  --output docs/licensing/sbom.spdx.json
```

装后系统在目标 rootfs 里加 `--installed`。逐版本重新生成；不要手工编辑生成物。

## 我们改过的第三方程序

| 程序 | 许可 | 我们做了什么 |
|---|---|---|
| cage v0.3.1 | MIT（Copyright (c) 2018-2020 Jente Hidskes；Copyright (c) 2019 The Sway authors） | Live 的 kiosk 合成器：套 [cage-0.3.1-enable-tap.patch](scripts/patches/cage-0.3.1-enable-tap.patch) 打开触摸板轻点，编译成 `mipl-cage` 装进 ISO |
| Caelestia（fork） | GPL-3.0-only | 当前为文档 / NOTICE；后续中文、品牌与 NVIDIA 改动在 [Caelestia-dotfiles](https://github.com/MipLinux/Caelestia-dotfiles)、[Caelestia-shell](https://github.com/MipLinux/Caelestia-shell)、[Caelestia-cli](https://github.com/MipLinux/Caelestia-cli) 公开 |

## 发布前

- SBOM 与包清单一致；`custom` 许可证的包有对应通知。
- NVIDIA 的 EULA 随包；二进制未修改。
- GPLv2 / GPLv3 的源码交付按 [SOURCE-OFFER.md](docs/licensing/SOURCE-OFFER.md) 落实。
- 可选专有应用不与 GPL 包合并。
