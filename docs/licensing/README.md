# 许可与 SBOM

这个目录放三件事：NVIDIA 的专有边界、GPL / LGPL 的源码交付方式、构建时生成的逐包 SBOM。
逐包许可证不在这里手工维护；`sbom.spdx.json` 从包元数据生成。

## Arch 的许可证文件在哪

- `licenses` 包集中提供常见 SPDX 文本：`/usr/share/licenses/spdx/<SPDX>.txt`，以及
  `known_spdx_license_identifiers.txt` / `known_spdx_license_exceptions.txt`。
- `pacman -Qi <pkg>` 的 `Licenses` 字段是包声明的 SPDX 表达式，或 `custom`。
- 只有带独立版权信息 / 自定义许可证的包，才在自己的 `/usr/share/licenses/<pkg>/` 下放文件
  （例如 `nvidia-utils`）。**不要假设每个包都有 `/usr/share/licenses/<pkg>/`。**
- 通用文本去 `licenses` 包找；`custom` 包才去看自己的目录。

## SBOM

- 生成器：`scripts/gen-sbom.py`。
- Live 构建环境：`python3 scripts/gen-sbom.py --pkglist profile/packages.x86_64 --output docs/licensing/sbom.spdx.json`
- 装后 rootfs：`python3 scripts/gen-sbom.py --installed --pkglist <目标清单> --output <json>`
- 输出是 package-level SPDX 2.3：`licenseDeclared` 来自 pacman；`custom` / `unknown` 用
  `NOASSERTION`，原值保留在 `licenseComments`。
- 逐版本重新生成，不手工编辑；生成物只是许可证清单，**不是源码交付**（见 [SOURCE-OFFER.md](SOURCE-OFFER.md)）。

## 分发状态

| 状态 | 组件 | 说明 |
|---|---|---|
| 已分发 | Live / 装后清单里的 Arch 包；`nvidia-utils`；`nvidia-open` | SBOM 覆盖；专有与源码例外见下文 |
| 计划引入 | Caelestia-dotfiles / shell / cli；Quickshell / Qt6 | 尚未进入 ISO；接入时补 SBOM 与源码安排 |
| 可选 | Spotify / Todoist 等 | 只在用户选择安装时分发；不默认进入镜像 |

## 文件

| 文件 | 内容 |
|---|---|
| [NVIDIA.md](NVIDIA.md) | EULA 与分发限制 |
| [SOURCE-OFFER.md](SOURCE-OFFER.md) | GPLv2 / GPLv3 / LGPL 的源码交付 |
| `sbom.spdx.json` | 生成物；不手工维护 |

## 审查

- 包清单、Arch 包元数据、上游 tag / commit 变化时重新生成并核对。
- 正式发布前由法务确认 EULA 与源码交付方式。
