# NVIDIA 专有组件

> 本文只摘录 EULA 与分发条件，不推断文本未写明的义务；具体适用由法务确认。

## 分发状态

| 组件 | 许可 | 状态 |
|---|---|---|
| `nvidia-utils` | NVIDIA Driver License Agreement | Live 与装后系统；用户态专有 |
| `nvidia-open` | MIT AND GPL-2.0-only | Live 与装后系统；内核模块，不是专有组件 |

本次核对对象：2026-10-17 ISO。

| 项 | 值 |
|---|---|
| `nvidia-utils` | `615.78.08-1` |
| EULA 路径 | `/usr/share/licenses/nvidia-utils/LICENSE` |
| EULA 版本 | `(v. February 25, 2025)` |
| EULA sha256 | `c692fb14ad4f499c6aee1b9e144e6905148c420e6225b17cb2937366c1e507ad` |
| `nvidia-open` | `615.78.08-2` |
| `nvidia-open` 许可 | `MIT AND GPL-2.0-only`；`/usr/share/licenses/nvidia-open/LICENSE`，sha256 `d8e96d29bc323000e7ba56102d77c88226a7a3d0d94e2081cb4b071ae9de4a06` |

版本与 hash 逐版本重新核对，不作为永久值。

## EULA 条款摘要

- **1.1(d)**：可以把 SOFTWARE 随采用 OSI 认可许可证的操作系统内核分发；条件是两个：
  二进制不得修改（解压缩除外），且必须向每位接收者提供本协议。
- **2.8**：GeForce / TITAN 软件仅授权用于用户自有的相应硬件；不授权数据中心部署。
- **2.9**：不得以导致 SOFTWARE 受开源许可证约束的方式使用它；EULA 自身的
  “Components Under Other Licenses” 例外不受此限。
- **2.11**：因使用 SOFTWARE 开发或部署的产品 / 服务、超出授权范围的使用、或违反 EULA
  产生的索赔，可能触发抗辩、赔偿与免责义务；具体适用由法务判断。
- **11 / 12**：SOFTWARE 按现状提供；NVIDIA 的累计责任上限为 5 美元（以适用法律允许为前提）。

以上是条款摘要；EULA 还有其他条款，未写明的义务不做推断。

## 分发处置

- 优先使用 Arch 官方 `nvidia-utils` / `nvidia-open` 二进制包；`nvidia-utils` 的 PKGBUILD
  明确 `options=('!strip')`，`package_nvidia-utils()` 用 `install` 原样安装用户态库。
- 不 strip、不 patch、不重打包用户态二进制；保留版权与专有通知。
- 保留 `/usr/share/licenses/nvidia-utils/LICENSE`，确保接收者能取得 EULA。
- `nvidia-utils` 保持独立包，不合并进 GPL 包，不静态链接，不把 ISO 整体标成 GPL。
- 记录包版本与许可证 / 包文件 / 关键库的 sha256，作为二进制完整性证据。
- `nvidia-open` 的源码义务按 GPLv2 走 [SOURCE-OFFER.md](SOURCE-OFFER.md)，不走本 EULA。

`nvidia-open` 不等于整栈开源：内核模块是 MIT / GPLv2，用户态 `nvidia-utils` 仍是专有。

正式公开发行前，建议向 `driver-licensing@nvidia.com` 书面确认再分发 / ISO 集成方案。

## 依据

- EULA 原文：ISO 内 `/usr/share/licenses/nvidia-utils/LICENSE`；
  官方英文 <https://www.nvidia.com/en-us/drivers/geforce-license/>，
  中文 <https://www.nvidia.cn/drivers/nvidia-license/>。
- `nvidia-utils` PKGBUILD：<https://gitlab.archlinux.org/archlinux/packaging/packages/nvidia-utils/-/blob/main/PKGBUILD>。
- `nvidia-open` 上游：<https://github.com/NVIDIA/open-gpu-kernel-modules>。
