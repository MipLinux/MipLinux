# 技术细节 02 · 构建与 QEMU 测试

> 目标：用未修改的 `releng` profile 构建出 ISO，并在 QEMU（UEFI）中引导成功。
>
> 前置：已完成 [01-容器环境搭建.md](01-容器环境搭建.md)。

---

## 阶段 A · 构建

### A.1 在容器内执行

```bash
# 进入容器（若尚未进入）
sudo systemd-nspawn -D /var/lib/machines/archbuild \
     -u root \
     --bind ~/Code/Projects/MipLinux/out:/out

# 构建
mkarchiso -v -w /tmp/work -o /out /usr/share/archiso/configs/releng
```

> **不要加 `-b`。** 原因见 [01-容器环境搭建.md](01-容器环境搭建.md) 步骤 3 —— bootstrap 的 root 账户没有密码，加 `-b` 会停在登录提示符且无法登录。

**参数说明：**

| 参数 | 作用 |
|---|---|
| `-v` | 详细输出。**基线构建务必加上**，否则出错时看不到细节 |
| `-w <dir>` | 工作目录。用 `/tmp/work` 避免污染容器其它位置 |
| `-o <dir>` | 输出目录。这里指向绑定的 `/out` |
| 最后一个参数 | profile 路径 |

**预期耗时：** 几分钟（取决于网络速度）。这一步会实际下载 releng 的 129 个包。

**预期输出（末尾）：**

```
INFO: Done! Finished building ISO image.
```

产物出现在宿主机 `~/Code/Projects/MipLinux/out/`：

```
archlinux-<日期>-x86_64.iso
archlinux-<日期>-x86_64.iso.sha256
archlinux-<日期>-x86_64.iso.sig      ← 若容器内有 GPG 密钥才会生成
archlinux-bootstrap-<日期>-x86_64.tar.zst
```

> **注意产物名是 `archlinux-*` 而不是 `miplinux-*`** —— 因为我们还没改 `profiledef.sh`。这是正常的，基线构建就是要用原版。

### A.2 返回宿主机

```bash
exit
```

---

## 阶段 B · 准备测试环境

**以下全部在宿主机上执行，不在容器里。**

### B.1 安装测试依赖

```bash
# Arch 系
sudo pacman -S edk2-ovmf qemu-desktop

# Fedora
sudo dnf install edk2-ovmf qemu-kvm
```

### B.2 检查 KVM 可用

```bash
ls -l /dev/kvm
```

**本机已确认可用。** 若不存在，需检查 BIOS 中的虚拟化开关。

### B.3 确认 OVMF 固件路径

```bash
ls -l /usr/share/edk2/x64/OVMF_CODE.4m.fd /usr/share/edk2/x64/OVMF_VARS.4m.fd
```

**不同发行版路径可能不同**，Fedora 上通常在 `/usr/share/edk2/ovmf/` 下。

### B.4 准备 UEFI 变量文件

```bash
cd ~/Code/Projects/MipLinux/out
cp /usr/share/edk2/x64/OVMF_VARS.4m.fd .
```

> **每次测试都要重新复制一份。**
>
> 引导过的系统会把引导项写进 NVRAM。复用同一份变量文件会导致上一次的引导项影响下一次，表现为「上次能启动、这次不行」——极难排查。

---

## 阶段 C · QEMU 引导验证

### C.1 启动命令（UEFI）

```bash
cd ~/Code/Projects/MipLinux/out

qemu-system-x86_64 -enable-kvm -m 4096 \
  -drive if=pflash,format=raw,readonly=on \
    -file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive if=pflash,format=raw \
    -file=./OVMF_VARS.fd \
  -cdrom archlinux-*.iso \
  -boot order=d \
  -netdev user,id=n0 -device virtio-net,netdev=n0
```

**参数说明：**

| 参数 | 作用 |
|---|---|
| `-enable-kvm` | 硬件加速（本机 `/dev/kvm` 可用） |
| `-m 4096` | 4 GB 内存，Live 环境足够 |
| 第一个 `if=pflash` | UEFI 固件本体，**只读** |
| 第二个 `if=pflash` | UEFI 变量存储，**可写** ← 就是 `OVMF_VARS.fd` |
| `-cdrom` | 待测 ISO |
| `-boot order=d` | 优先从光驱启动 |
| `-netdev user` | 用户模式网络，Live 环境可上网 |

### C.2 更省事的替代方案

`archiso` 自带 `run_archiso` 脚本，封装了常用参数：

```bash
sudo pacman -S archiso      # 宿主机安装，仅为拿这个脚本
run_archiso -u -i out/archlinux-*.iso
```

`-u` 表示 UEFI。

**但基线构建建议先手工执行一次完整命令**——你能清楚知道每个参数在做什么，出问题时也知道去哪查。

---

## 验收标准

### 成功的样子

**Live 环境启动到 root shell 提示符。**

```
Arch Linux <版本> (tty1)

archiso login: root
[root@archiso ~]#
```

### ⚠️ 关键：官方 releng 没有桌面环境

**出现命令行提示符就是成功，不要以为是自己搞错了。**

已实测确认：releng 的 129 个包中**不包含任何桌面环境或显示管理器**：

```
plasma / gnome / hyprland     ✗
sddm / gdm / lightdm          ✗
```

默认 ISO 是一个**命令行救援盘**。桌面环境是后续要加的东西。

### 验收清单

- [ ] QEMU 窗口出现，且能进入 UEFI 引导流程
- [ ] 引导菜单出现（systemd-boot）
- [ ] 内核与 initramfs 加载，无报错
- [ ] 进入 Live 环境，出现登录提示
- [ ] 以 `root` 登录成功（**无密码**）
- [ ] 能执行 `pacman -Q | wc -l` 并看到包数量

### 建议顺带记录的数据

给后续换源提供对照基准：

```bash
# 在 Live 环境内
pacman -Q | wc -l                          # 包总数，releng 应接近 129
ls /etc/pacman.d/mirrorlist && head -3 /etc/pacman.d/mirrorlist
```

同时记录**构建耗时**（后面每次重建都按这个量级估算）。

---

## 常见失败与排查

| 现象 | 可能原因 |
|---|---|
| QEMU 卡在 UEFI shell，不进引导 | ISO 没有 UEFI 引导路径，或 `bootmodes` 配置错 |
| 引导菜单出现但内核加载失败 | initramfs 生成有问题，看构建日志第 6 步 |
| 卡在 `Waiting for /dev/disk/by-label/...` | `iso_label` 与实际不符 |
| 直接重启，无任何输出 | 引导器未正确写入 ISO |
| QEMU 报 `Could not access KVM kernel module` | KVM 不可用，去掉 `-enable-kvm`（会慢很多） |
| 反复出现上次的引导项 | `OVMF_VARS.fd` 没重新复制 |

**构建阶段失败**时，`-v` 的输出就是排查依据。重点看：

- 第 3 步（pacstrap）失败 → 网络或镜像源问题
- 第 6 步（mkinitcpio）失败 → 内核模块或 hook 问题
- 第 9 步（xorriso）失败 → 引导文件缺失

---

## 这一步完成后意味着什么

**你有了一个「已知能工作」的基线。**

```
✅ 工具链验证通过（nspawn → pacstrap → mkinitcpio → squashfs → xorriso → 引导）
✅ 构建环境可重复使用
✅ 后续任何 ISO 起不来，都能确定是自己改的东西导致的
```

**这是整个项目最重要的一个参照物。** 没有它，后面每一次失败都会陷入「是环境问题还是配置问题」的怀疑。

---

## 下一步

基线通过后，可以开始复制 `releng` 为自己的 profile。参见：

- [knowledge/03-项目结构.md](../../knowledge/03-项目结构.md) —— profile 每个文件的作用
- [knowledge/02-环境与工具链.md](../../knowledge/02-环境与工具链.md) 第 3.1 节 —— 换源时必须避开的 `Include` 陷阱
