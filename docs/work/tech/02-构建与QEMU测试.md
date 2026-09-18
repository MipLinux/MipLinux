# 技术细节 02 · 构建与 QEMU 测试

> 目标：用未修改的 `releng` profile 构建出 ISO，并在 QEMU（UEFI）中引导成功。
>
> 前置：已完成 [01-容器环境搭建.md](01-容器环境搭建.md)。

---

## 阶段 A · 构建

### A.1 在容器内执行

```bash
# 进入容器（若尚未进入）—— 路径由脚本自己定位，两台机器都适用
./scripts/mipl.sh shell
```

> `mipl shell` 等价于下面这条命令，但它会先检查容器是否已经在跑
> （容器没关就重进会报错，见 Issue #4）：
>
> ```bash
> sudo systemd-nspawn --directory=/var/lib/machines/archbuild \
>      -u root --machine=archbuild \
>      --bind <仓库根目录>/out:/out
> ```
>
> 注意 `--bind` 的左边**不要写死成自己的家目录** —— 两个人的仓库路径不一样
> （Issue #7 里的文档就写死了 `~/Code/Projects/MipLinux`）。

进入容器后构建：

```bash
mkarchiso -v -w /tmp/work -o /out /usr/share/archiso/configs/releng
```

> 也可以不进容器，直接让脚本一条龙跑完（下载 bootstrap → 解压 → 构建）：
>
> ```bash
> ./scripts/mipl.sh build
> ./scripts/mipl.sh build --work /var/tmp/mipl-work   # /tmp 空间不够时换目录（Issue #6）
> ```

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

产物出现在宿主机 `<仓库根目录>/out/`：

```
archlinux-<日期>-x86_64.iso
archlinux-<日期>-x86_64.iso.sha256
archlinux-<日期>-x86_64.iso.sig      ← 若容器内有 GPG 密钥才会生成
archlinux-bootstrap-<日期>-x86_64.tar.zst
```

> **注意产物名是 `archlinux-*` 而不是 `miplinux-*`** —— 因为我们还没改 `profiledef.sh`。这是正常的，基线构建就是要用原版。
>
> 只有 `.iso` 是必然会生成的：`.sha256` 要自己算，`.sig` 要有 GPG 密钥，
> bootstrap 压缩包留在容器内的 `/tmp`。**这不是故障**（Issue #7 问的就是这个）。
> 想看当前到底有哪些产物：`./scripts/mipl.sh iso`

### A.2 返回宿主机

```bash
poweroff
```

> **不要直接用 `exit`，也不要关终端窗口。** 那样只是断开连接，容器还在后台跑
> （`archbuild.scope`），下次就进不去了 —— 见 Issue #4。
> 忘了关的补救：`./scripts/mipl.sh stop`。

---

## 阶段 B · 准备测试环境

**以下全部在宿主机上执行，不在容器里。**

### B.1 安装测试依赖

```bash
./scripts/mipl.sh deps              # 按你的发行版打印要装什么，并检查还缺什么
./scripts/mipl.sh deps --install    # 直接执行
```

手工装的话：

```bash
# Arch 系
sudo pacman -S edk2-ovmf qemu-desktop

# Fedora（多一个 systemd-container，nspawn 在这个包里）
sudo dnf install edk2-ovmf qemu-kvm systemd-container
```

### B.2 检查 KVM 可用

```bash
ls -l /dev/kvm
```

**本机已确认可用。** 若不存在，需检查 BIOS 中的虚拟化开关。
（`./scripts/mipl.sh doctor` 会一并检查这一项，顺便告诉你缺什么。）

### B.3 确认 OVMF 固件路径

```bash
./scripts/mipl.sh doctor
```

**不同发行版路径和文件名都不一样**，脚本会自动探测并打印结果：

| 发行版 | 目录 | 优选的文件名 | 同目录下的其它变体 |
|---|---|---|---|
| Arch / CachyOS | `/usr/share/edk2/x64/` | `OVMF_CODE.4m.fd` / `OVMF_VARS.4m.fd` | `OVMF_CODE.secboot.4m.fd` |
| Fedora | `/usr/share/edk2/ovmf/` | `OVMF_CODE_4M.fd` / `OVMF_VARS_4M.fd` | `OVMF_CODE.fd`、`.secboot.`、`.inteltdx.`、`.stateless.` |
| Debian / Ubuntu | `/usr/share/OVMF/` | `OVMF_CODE_4M.fd` / `OVMF_VARS_4M.fd` | `OVMF_CODE.fd`、`.ms.`、`.secboot.`、`.snakeoil.` |

> 这张表核对过打包元数据（Fedora 的 `edk2.spec`、Debian `ovmf` 包的文件清单，
> 2026-09-18），不是凭印象写的。但仍以 `doctor` 的探测结果为准 —— 发行版会改。
>
> **`secboot` / `ms` / `snakeoil` 一律不用**：那几种需要 Secure Boot 或微软密钥，
> 测我们自己做的 ISO 只会徒增变量。脚本的优先级已经处理了这件事。
>
> 列这张表不是为了让你手抄 —— 手抄正是 Issue #8 的成因。
> 列出来是为了**探测失败时你知道去哪看**。
>
> 探测结果要回报给文档（线 B4）：`./scripts/mipl.sh doctor --report`

### B.4 准备 UEFI 变量文件

```bash
./scripts/mipl.sh vars
```

> **每次测试都要重新复制一份。**
>
> 引导过的系统会把引导项写进 NVRAM。复用同一份变量文件会导致上一次的引导项影响下一次，表现为「上次能启动、这次不行」——极难排查。
>
> 所以 `mipl vars` 每次都无条件覆盖，`mipl qemu` 每次启动前都会先跑一遍它。

脚本把变量文件统一复制成 **`out/OVMF_VARS.fd`** 这个固定名字。

源文件名各发行版不同（`OVMF_VARS.4m.fd` / `OVMF_VARS_4M.fd` / `OVMF_VARS.fd`），
固定名意味着 **QEMU 参数永远不需要跟着发行版改** —— Issue #8 里的第二个错误
（复制出来叫 `.4m.fd`，QEMU 却去读 `.fd`）就是这么来的。

---

## 阶段 C · QEMU 引导验证

### C.1 启动命令（UEFI）

```bash
./scripts/mipl.sh qemu
```

不给参数就用 `out/` 里**最新的**那个 ISO；也可以指定：

```bash
./scripts/mipl.sh qemu out/archlinux-2026.09.18-x86_64.iso
./scripts/mipl.sh -n qemu        # 只看它准备执行什么，不真的启动
```

脚本实际拼出来的命令长这样 —— **读一遍，出问题时才知道去哪查**：

```bash
qemu-system-x86_64 -name 'MipLinux 测试' -m 4096 -enable-kvm \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive if=pflash,format=raw,file=<仓库>/out/OVMF_VARS.fd \
  -cdrom <仓库>/out/archlinux-2026.09.18-x86_64.iso \
  -boot order=d \
  -netdev user,id=n0 -device virtio-net,netdev=n0
```

> ### ⚠️ `file=` 必须和它所属的 `-drive` 在同一行
>
> 下面这种写法是**错的**，而且错得很隐蔽（看着像正常的续行）：
>
> ```bash
> -drive if=pflash,format=raw,readonly=on \
>   -file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \      # ← 错误示范
> ```
>
> 行尾反斜杠只是把两行接成一条命令，QEMU 收到的是**两个独立参数**：
> `-drive if=pflash,...` 和 `-file=...`。而 QEMU 根本没有 `-file` 这个选项，
> 于是直接报：
>
> ```
> qemu-system-x86_64: -file=/usr/share/edk2/x64/OVMF_CODE.4m.fd: invalid option
> ```
>
> 这是 Issue #8 记录的实际故障。`mipl` 用数组逐条拼参数，从结构上不可能拆开。

**参数说明：**

| 参数 | 作用 |
|---|---|
| `-enable-kvm` | 硬件加速（本机 `/dev/kvm` 可用）。没有 kvm 时脚本会去掉它并提醒 |
| `-m 4096` | 4 GB 内存，Live 环境足够（可用 `MIPL_MEM` 改） |
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

**但推荐用 `mipl qemu`：**

| | `run_archiso` | `mipl qemu` |
|---|---|---|
| 宿主机要不要装 archiso | 要 | **不要** |
| Fedora 上能不能用 | 不能（没有这个包） | 能 |
| 会不会自动刷新 `OVMF_VARS` | 不会 | **会**（这正是最容易忘的一步） |
| 固件路径 | 自己找 | 探测 |

### C.3 无显示器时怎么验证（可选）

没有图形界面（或远程 SSH）时，可以不弹窗口启动，然后从 QEMU 监视器里
把画面截出来看：

```bash
MIPL_QEMU_EXTRA="-display none -monitor unix:/tmp/mipl-mon,server,nowait" \
  ./scripts/mipl.sh qemu &

echo 'screendump /tmp/boot.ppm' | socat - UNIX-CONNECT:/tmp/mipl-mon
convert /tmp/boot.ppm /tmp/boot.png     # 打开看是不是出现了提示符
```

---

## 验收标准

### 成功的样子

**Live 环境启动到 root shell 提示符。**

```
Arch Linux <版本> (tty1)

archiso login: root
[root@archiso ~]#
```

> **已实测通过**（2026-09-18，CachyOS 宿主机 + QEMU 11.1.1 + `archlinux-2026.09.18-x86_64.iso`）：
> 用 `./scripts/mipl.sh qemu` 启动，UEFI 引导进入 Live 环境，
> 出现 `archiso login: root (automatic login)` 与 `[root@archiso ~]#` 提示符。
> 无头复现方式见上面的 C.3。

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
| `qemu-system-x86_64: -file=...: invalid option` | `file=` 被换行拆成了独立参数 —— **Issue #8**。用 `./scripts/mipl.sh qemu`，或把 `file=` 并回 `-drive` 那一行 |
| QEMU 报找不到 `OVMF_VARS.fd` | 复制出来的名字和命令里写的名字不一致（`.4m.fd` vs `.fd`）。`mipl` 统一成固定名，不会有这个问题 |
| QEMU 卡在 UEFI shell，不进引导 | ISO 没有 UEFI 引导路径，或 `bootmodes` 配置错 |
| 引导菜单出现但内核加载失败 | initramfs 生成有问题，看构建日志第 6 步 |
| 卡在 `Waiting for /dev/disk/by-label/...` | `iso_label` 与实际不符 |
| 直接重启，无任何输出 | 引导器未正确写入 ISO |
| QEMU 报 `Could not access KVM kernel module` | KVM 不可用，去掉 `-enable-kvm`（会慢很多） |
| 反复出现上次的引导项 | `OVMF_VARS.fd` 没重新复制 —— `mipl qemu` 每次都会刷新 |

排查第一步永远是：

```bash
./scripts/mipl.sh doctor          # 环境对不对
./scripts/mipl.sh -n qemu         # 命令拼出来是什么
```

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
