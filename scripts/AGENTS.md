---
description: MipLinux 脚本约定：mipl.sh 的 root 要求与 pkexec 用法、路径推导、探测与「能不能用」式检查。
tags: [scripts, bash, mipl, qemu, root, pkexec]
---

# AGENTS.md — scripts/ 脚本约定

`scripts/mipl.sh` 是项目操作台：把「每次都要手抄的长命令」变成一条不会抄错的命令。
本文只写 `scripts/` 特有的规矩；通用红线在[根文件](../AGENTS.md)。

## 权限：一律 root，且不自己提权

**需要 root 的命令不自己 `sudo`** —— 两种合规方式：

```bash
sudo ./scripts/mipl.sh doctor                     # A. 默认：贴给用户，停下等结果
pkexec --keep-cwd "$PWD/scripts/mipl.sh" doctor   # B. 自己跑（弹 polkit 授权框，用户点确认）
```

`pkexec` 的三个坑：

1. **清空环境** —— `MIPL_QEMU_EXTRA` / `MIPL_MEM` / `MIPL_OUT_DIR` 这类变量不会传进去，必须经 `env`：
   `pkexec --keep-cwd /usr/bin/env MIPL_QEMU_EXTRA="-display none" "$PWD/scripts/mipl.sh" qemu`
2. **默认丢弃 `DISPLAY` / `XAUTHORITY`，且不设 `SUDO_USER`** —— 而 `mipl.sh:772` 那句图形会话提示的判据正是 `SUDO_USER`，
   所以 `pkexec ... qemu` **开不出窗口**。三条出路：用 `env` 显式传会话变量；走[无头路径](../docs/work/tech/02-构建与QEMU测试.md)；
   或把这条交给用户用 `sudo` 跑（`sudo` 保留 `DISPLAY` / `XAUTHORITY`，提示也正常）。
3. **退出码 `126` = 用户取消授权、`127` = 未授权或出错** —— 两者都停下问用户，**不换 `sudo` 绕过**。

`./scripts/check-identity.sh` **不需要 root**，直接跑。

## 脚本本体的三条约束

每条都来自实际踩过的坑（GitHub Issues）：

- **一切路径从脚本自身位置推导**，不含 `$HOME`、不含写死的目录 —— 两台机器的仓库路径不同（Issue #7）。
  软链场景只用 `${BASH_SOURCE[0]}`，**不写 `$(dirname "$0")`**：脚本可能被软链到 `~/.local/bin/mipl`。
- **OVMF 固件靠运行时探测，不硬编码** —— Arch / Fedora / Debian 三家的路径都不一样。
- **QEMU 参数用 bash 数组拼装**，一个参数就是数组的一个元素 —— 手写时换行会把 `-file=` 拆成独立的 `-file=`（Issue #8）。

## 「文件在不在」不等于「东西能不能用」

Issue #32 的教训：bootstrap tarball 里 `etc/os-release` 排第 630 条、`usr/bin/bash` 排第 5815 条，
所以半途而废的解压恰好能骗过所有「文件在不在」式的检查。
**状态判断一律落在「能不能用」上**，且 `doctor` / `shell` / `build` 三个入口共用同一段判断（`scripts/mipl-lib.sh`）。

环境变量要写在 `sudo` 后面（`sudo` 默认会清掉你的环境）。

## 风格

注释与文案用简体中文，**写「为什么」，不写「做了什么」** —— 脚本头部把该约束的来历讲清楚，调用点就不会被误改。
改脚本前先读头部注释，它记着每条约束对应的 Issue。
