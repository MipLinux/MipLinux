---
description: MipLinux 构建源约定：profile 改动如何影响产物、构建前的品牌断言、pacman.conf 与包清单的既有决策。
tags: [profile, archiso, build, branding, pacman]
---

# AGENTS.md — profile/ 构建源

`profile/` 就是发行版的「源代码」：它由上游 releng 改名而来，构建过程是**装配**而不是编译。
改这里的一个配置文件，等于改最终 ISO 的行为。本文只写 `profile/` 特有的规矩；通用红线在[根文件](../AGENTS.md)。

## 改完先跑品牌断言

```bash
./scripts/check-identity.sh     # 不需要 root；红了别构建，否则产出的是半改名的 ISO
```

上游 `mkarchiso` 只替换 `%ARCH%` / `%INSTALL_DIR%` / `%ARCHISO_UUID%`，**没有名字占位符** ——
所以品牌文本是硬编码的，散在 **9 个文件、26 处**（`profiledef.sh` 的四个变量 + `efiboot/` / `syslinux/` / `grub/` 的菜单与帮助文本）。
「有没有漏改」由这个脚本断言，豁免项逐条带理由。改名前后各跑一次即可看到红 → 绿。

引导项用的是构建时生成的**时间戳 UUID**（`archisosearchuuid`），不是卷标 —— 所以换卷标不需要同步改引导配置。

## 不要动的两处

- **`packages.x86_64` 第 1–130 行**是 `# ==> 基础 · 从 releng 继承，勿动 <==` 标记块。极简 Live 的裁剪清单待定（P4），别顺手删。
- **`PROFILE.md`** 记录 releng 的出处与 `archiso` 包元数据，是历史事实，不能改。

## pacman.conf 的两条既有决策

- **`profile/pacman.conf` 里的 6 处 `Include` 全部注释掉** —— 这是 D3 的落地形态：不使用宿主机 `pacman.conf` 的 `Include` 隐式解析，
  否则会静默引入宿主发行版的软件源。**不要打开它们。**
- **`airootfs/etc/pacman.conf` 的 `[archlinuxcn]` 写的是 `SigLevel = Optional TrustAll`**（即不校验签名）。
  内部构建无所谓，但 D10 定了对外发布，而**装后系统的 `pacman.conf` 由安装器写** —— 收紧方案还挂在 P11，别自作主张改。

## 两个目录的角色

| 路径 | 是什么 |
|---|---|
| `airootfs/` | Live 环境的**出厂设置**，会被装后系统继承；「配置即事实」指的就是它进了 git |
| `efiboot/` `syslinux/` `grub/` | 引导菜单与帮助文本，品牌文本的另一半 |

## 所有权

`profile/packages.x86_64` 与 `profile/airootfs/**` 属**线 E · Live 环境与入口**。
移到装后系统的那部分（P10 定案后）会牵动 D6，先问再动。
