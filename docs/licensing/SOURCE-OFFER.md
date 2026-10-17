# 源码提供

> 本文只写 GPL / LGPL 的源码交付方式；逐包许可见生成的 SBOM。
> 不是法律意见；正式发布前由法务确认。

## 分发状态

| 状态 | 组件 | 源码处理 |
|---|---|---|
| 已分发 | Live / 装后清单中的 Arch 包 | 按各包许可证版本交付 |
| 已分发 | `nvidia-open` | GPLv2；见下文 |
| 已分发（专有） | `nvidia-utils` | 无源码；EULA 见 [NVIDIA.md](NVIDIA.md) |
| 计划引入 | Caelestia-dotfiles / shell / cli | 尚未进入 ISO；接入时补 |
| 计划引入 | Quickshell / Qt6 | 随 shell 接入；LGPL |
| 可选 | Spotify / Todoist 等 | 只对选择安装的用户分发；单独说明 |

## GPLv2

GPLv2 §3 给了三种方式：

- **§3(a)**：随二进制一起提供完整对应源码，放在同一介质上。
- **§3(b)**：随二进制提供书面 offer，有效期至少 3 年，由分发者实际履行。
- **§3(c)**：只适用于非商业转交，且只能继承上游随二进制给出的 offer。

**只写一个上游源码 URL，不等于 §3(b) 的书面 offer。** 书面 offer 必须由分发者能够实际履行；
如果 MipLinux 承诺提供源码，就要能在这 3 年内交付，而不是把请求转给上游。

对 `nvidia-open`：发布时二选一——随 release 资产提供对应源码（§3(a)），或由 MipLinux
出具可履行的 3 年书面 offer（§3(b)）。只链接 NVIDIA 上游不满足 §3(b)。

对 ISO 内再分发的其他 GPLv2 包：同理。指向 Arch / ABS 的链接不能自动构成 MipLinux 的
§3(b) offer；要么随 release 提供源码，要么给出 MipLinux 自己能履行的书面 offer。

## GPLv3

GPLv3 §6 的交付方式：

- **§6(a)**：随物理产品提供固定在有形介质上的对应源码。
- **§6(b)**：书面 offer，至少 3 年，且在产品型号的备件 / 支持期内有效。
- **§6(c)**：单独分发目标代码时，附上书面 offer 的副本。
- **§6(d)**：从指定地点提供目标代码，并在同一地点以不额外收费的方式提供对应源码。
- **§6(e)**：P2P 分发时，告知其他 peer 目标代码与源码的公开位置。

ISO 下载 + 同一发布页的源码下载，适用 **§6(d)**：源码与目标代码在同一地点、不再收费。
如果源码只在别的站点或只给上游链接，改用 **§6(b)** 的书面 offer。

Caelestia 三个 fork 尚未进入 ISO；接入时按 GPLv3 §6(d) 或 §6(b) 交付，并发布修改。

## LGPL

Quickshell / Qt6 等 LGPL 组件：提供对应源码与可重链接条件；动态链接时保留
LGPL 要求的通知与源码获取方式。LGPLv3 允许按 GPLv3 组合，但 LGPL 部分仍要满足
源码与重链接要求。

## 结论

- SBOM 只列许可证，**不是源码交付**。
- `nvidia-utils` 无源码，只有 EULA。
- `nvidia-open` 与 ISO 内其他 GPLv2 包：发布时必须能实际交付源码或书面 offer；
  只写上游链接不够。
- Caelestia 当前未分发，接入时再按 GPLv3 交付。
