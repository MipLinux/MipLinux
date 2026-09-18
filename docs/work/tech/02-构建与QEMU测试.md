# 技术细节 02 · 构建与 QEMU 测试

> 目标：用未修改的 `releng` profile 构建出 ISO，并在 QEMU（UEFI）中引导成功。
>
> 前置：已完成 [01-容器环境搭建.md](01-容器环境搭建.md)。
>
> **权限**：本文所有 `mipl` 命令都要 `sudo` 跑。脚本一律要求 root，普通用户运行
> 会被直接拒绝 —— 它不自己提权，因为同一件事一会儿降权一会儿提权，
> 出问题时根本分不清是谁的权限在起作用（`out/` 里的产物一会儿归你、一会儿归 root）。

---

## 阶段 A · 构建

### A.1 在容器内执行

```bash
# 进入容器（若尚未进入）—— 路径由脚本自己定位，两台机器都适用
sudo ./scripts/mipl.sh shell
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

进入容器后构建（**原版 releng**，也就是「基线」）：

```bash
mkarchiso -v -w /var/tmp/mipl-work -o /out /usr/share/archiso/configs/releng
```

> 也可以不进容器，直接让脚本一条龙跑完（下载 bootstrap → 解压 → 构建）。
> **不给参数时用的是仓库里的 `profile/`**：
>
> ```bash
> sudo ./scripts/mipl.sh build                              # profile = 仓库 profile/
> sudo ./scripts/mipl.sh build --baseline                    # profile = 容器内原版 releng
> sudo ./scripts/mipl.sh build --work /var/tmp/w             # 换工作目录（默认 /var/tmp/mipl-work）
> sudo ./scripts/mipl.sh -n build                            # 只打印将执行的命令
> ```
>
> **profile 是怎么进容器的：** 仓库里的 `profile/` 不复制，而是**只读挂载**到容器的
> `/profile`（`mipl shell` 也挂同一个位置）。所以容器里的构建命令永远是
> `mkarchiso ... /profile`，日志里还会写明它来自宿主机的哪个目录 ——
> 「这次用的是哪份 profile」因此是看得见的，而不是靠人记。
>
> **工作目录在构建前会被自动清空**（容器内，默认 `/var/tmp/mipl-work`）。这不是洁癖：
> `mkarchiso` 用工作目录里的标记文件保证「装包 / 拷 airootfs / 生成 ISO」只跑一次
> （`_run_once`），不清就会跳过这些步骤、交给你一个「构建成功」的旧产物；
> `<work>/build_date` 还在时版本号也会沿用旧值。清理**不影响下载量** —— 包缓存在
> 容器内的 `/var/cache/pacman/pkg`，不在工作目录里。要故意保留上一次的目录
> （调试 `_run_once` 时才需要）：加 `--keep-work`。
>
> **⚠️ 工作目录不要放在 `/tmp`。** `systemd-nspawn` 默认会把容器的 `/tmp` 覆盖成一块
> **tmpfs（内存盘）**（`SYSTEMD_NSPAWN_TMPFS_TMP=0` 才不这么做），默认大小只有 10% 内存
> （本机 30 GiB → 3.0 GiB）。构建树到写 EFI 镜像时已有近 3 GiB（airootfs + `iso/` +
> `efiboot.img`），撞上就是：
>
> ```
> plain_io read/write: No space left on device
> ```
>
> 这正是 [Issue #6](https://github.com/MipLinux/MipLinux/issues/6)「/tmp 空间不足」的真身。
> 所以默认值是 `/var/tmp/mipl-work`（容器内普通目录 → 宿主磁盘），脚本也会在容器里
> 检查一次，发现工作目录在内存盘上就直接报错。
>
> 手工在容器里敲 `mkarchiso` 时脚本管不到，自己先 `rm -rf /var/tmp/mipl-work`，并且
> 别用 `-w /tmp/…`。
>
> **`--baseline` 是常备的诊断工具，不是一次性动作。** 某次构建挂了，跑一次
> `mipl build --baseline`：基线能过 → 问题在自己改的 profile；基线也过不了 →
> 问题在环境。
>
> 容器里那两份可以直接对照（A1 的验收）：
>
> ```bash
> diff -r --no-dereference /profile /usr/share/archiso/configs/releng
> ```
>
> `--no-dereference` 不能省：releng 里的 systemd enable 全是符号链接，
> 少了它会连「链接指向哪」都看不见。权限位与文件类型另比一遍：
>
> ```bash
> ( cd /profile && find . -printf '%y %m %P\n' | sort ) > /tmp/p
> ( cd /usr/share/archiso/configs/releng && find . -printf '%y %m %P\n' | sort ) > /tmp/r
> diff /tmp/p /tmp/r
> ```

> **不要加 `-b`。** 原因见 [01-容器环境搭建.md](01-容器环境搭建.md) 步骤 3 —— bootstrap 的 root 账户没有密码，加 `-b` 会停在登录提示符且无法登录。

**参数说明：**

| 参数 | 作用 |
|---|---|
| `-v` | 详细输出。**基线构建务必加上**，否则出错时看不到细节 |
| `-w <dir>` | 工作目录。用 `/var/tmp/mipl-work`（**别用 `/tmp`，容器里是内存盘**）。**手工重建前先删掉它**（脚本一条龙时会自动清） |
| `-o <dir>` | 输出目录。这里指向绑定的 `/out` |
| 最后一个参数 | profile 路径。容器里就是 `/profile`（仓库那份）或 `/usr/share/archiso/configs/releng`（基线） |

**预期耗时：** 几分钟（取决于网络速度）。这一步会实际下载 releng 的 129 个包。

**预期输出（末尾）：**

```
INFO: Done! Finished building ISO image.
```

产物出现在宿主机 `<仓库根目录>/out/`：

```
miplinux-<日期>-x86_64.iso
miplinux-<日期>-x86_64.iso.sha256
miplinux-<日期>-x86_64.iso.sig              ← 若容器内有 GPG 密钥才会生成
archlinux-bootstrap-<日期>-x86_64.tar.zst   ← bootstrap 是 Arch 官方的，名字改不了
```

> **产物名从 A6 改名起是 `miplinux-*`**（`iso_name="miplinux"`）。在那之前构建的
> `archlinux-2026.09.18-x86_64.iso` 是**改名前的对照物，别删**；想要新的对照，
> `sudo ./scripts/mipl.sh build --baseline`（容器内原版 releng）随时能重建一份。
>
> 改名之后，「这份 ISO 到底是不是我们的」**不需要 root、也不用开机**就能确认：
>
> ```bash
> ./scripts/check-identity.sh --iso out/miplinux-*.iso
> ```
>
> 它读 ISO9660 的 PVD（卷标 / publisher / application）、核对产物名，再扫一遍 ISO
> 未压缩区里的品牌文本。**改 profile 之前先跑不带参数的那条**（扫 profile，秒级），
> 它会把没改干净的地方列出来 —— 别让半改名的 ISO 被构建出来。
>
> 只有 `.iso` 是必然会生成的：`.sha256` **文件**不会自动落盘（哈希会打在终端上，见下），
> `.sig` 要有 GPG 密钥，bootstrap 压缩包留在容器内的 `/tmp`。**这不是故障**（Issue #7 问的就是这个）。
> 想看当前到底有哪些产物：`sudo ./scripts/mipl.sh iso`
>
> **构建结束会直接打一份报告**，A7 要的数字都在里面，不用事后翻 journal
> （下面这次是**改名前的第一次**构建，所以名字还是 `archlinux-…`；之后的产物名是 `miplinux-…`）：
>
> ```
> ==> 本次构建报告
>       总耗时（含下载 bootstrap / 解压 / 进容器）：2 分 09 秒
>       构建耗时（容器内 mkarchiso）：2 分 07 秒
>       产物：  <仓库>/out/archlinux-2026.09.18-x86_64.iso
>       体积：  1.5 GB（1616740352 字节）
>       sha256：787d4ce5514c…
> ```
>
> sha256 只对**本次新产出**的 ISO 计算（历史产物不重算）。如果一行都没打出来，
> 说明这次没真的产出产物 —— 先去看坑 1（工作目录里的 `_run_once` 标记）。
>
> **体积和耗时是 P3（ISO 形态）的依据：** 加了 NVIDIA（`nvidia-utils` 装完约 1 GB）
> 和桌面环境之后会明显增长，起点不记，后面就没有参照。

### A.2 返回宿主机

```bash
poweroff
```

> **不要直接用 `exit`，也不要关终端窗口。** 那样只是断开连接，容器还在后台跑
> （`archbuild.scope`），下次就进不去了 —— 见 Issue #4。
> 忘了关的补救：`sudo ./scripts/mipl.sh stop`。

---

## 阶段 B · 准备测试环境

**以下全部在宿主机上执行，不在容器里。**

### B.1 安装测试依赖

```bash
sudo ./scripts/mipl.sh deps              # 按你的发行版打印要装什么，并检查还缺什么
sudo ./scripts/mipl.sh deps --install    # 直接执行
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
（`sudo ./scripts/mipl.sh doctor` 会一并检查这一项，顺便告诉你缺什么。）

### B.3 确认 OVMF 固件路径

```bash
sudo ./scripts/mipl.sh doctor
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
> 探测结果要回报给文档（线 B4）：`sudo ./scripts/mipl.sh doctor --report`

### B.4 准备 UEFI 变量文件

```bash
sudo ./scripts/mipl.sh vars
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
sudo ./scripts/mipl.sh qemu
```

不给参数就用 `out/` 里**最新的**那个 ISO；也可以指定：

```bash
sudo ./scripts/mipl.sh qemu out/miplinux-*.iso
sudo ./scripts/mipl.sh -n qemu        # 只看它准备执行什么，不真的启动
```

脚本实际拼出来的命令长这样 —— **读一遍，出问题时才知道去哪查**：

```bash
qemu-system-x86_64 -name 'MipLinux 测试' -m 4096 -smp 4 -enable-kvm \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive if=pflash,format=raw,file=<仓库>/out/OVMF_VARS.fd \
  -cdrom <仓库>/out/miplinux-<日期>-x86_64.iso \
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
| `-smp 4` | 4 个 vCPU。Live 引导 1 个也够，但进系统后敲命令、以后挂盘装系统（A5）时多点省时间（可用 `MIPL_SMP` 改） |
| 第一个 `if=pflash` | UEFI 固件本体，**只读** |
| 第二个 `if=pflash` | UEFI 变量存储，**可写** ← 就是 `OVMF_VARS.fd` |
| `-cdrom` | 待测 ISO |
| `-boot order=d` | 优先从光驱启动 |
| `-netdev user` | 用户模式网络，Live 环境可上网 |

### C.2 更省事的替代方案

`archiso` 自带 `run_archiso` 脚本，封装了常用参数：

```bash
sudo pacman -S archiso      # 宿主机安装，仅为拿这个脚本
run_archiso -u -i out/miplinux-*.iso
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
# 环境变量要写在 sudo 后面 —— sudo 默认会清掉你 shell 里的变量
sudo MIPL_QEMU_EXTRA="-display none -monitor unix:/tmp/mipl-mon,server,nowait" \
  ./scripts/mipl.sh qemu &

echo 'screendump /tmp/boot.ppm' | socat - UNIX-CONNECT:/tmp/mipl-mon
convert /tmp/boot.ppm /tmp/boot.png     # 打开看是不是出现了提示符
```

### C.4 挂一块目标盘（装系统 / 装完重启）

线 B 的安装器要有地方装。A5 把这件事固化成三条命令：

```bash
sudo ./scripts/mipl.sh target                              # 建 out/target.qcow2（40G 虚拟，qcow2）
sudo ./scripts/mipl.sh qemu --disk target.qcow2            # 装：ISO 优先启动 + 挂上这块盘
sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c   # 装完：不挂 ISO，从盘启动
```

`mipl target` 产出两个文件：

| 文件 | 是什么 |
|---|---|
| `out/target.qcow2` | 目标盘本体。qcow2 的 40G 是**虚拟**大小，刚建好只占约 200 KiB |
| `out/target.vars.fd` | **这块盘自己的 UEFI 变量（NVRAM）**，第一次挂载时自动生成 |

> ### ⚠️ 为什么盘的 NVRAM 要单独一份
>
> 装系统时，安装器（`grub-install` / `efibootmgr`）会把引导项写进 **NVRAM**。
> `-boot order=c` 只决定「先试哪个设备」；真正决定这块盘能不能起来的是
> **NVRAM 里那个引导项**（或者 ESP 上的兜底路径 `\EFI\BOOT\BOOTX64.EFI`）。
>
> 所以：
>
> - 带 `--disk` 时，变量文件默认**保留**（`out/<盘名>.vars.fd`）—— 装完重启进得去；
> - 不带 `--disk` 时，`out/OVMF_VARS.fd` 仍然**每次刷新** —— 反复引导同一个 ISO 时，
>   上一次残留的引导项只会添乱（见 B.4）；
> - 两份文件互不干扰：**测 ISO 不会把装好系统的引导项刷掉**。三个人、一台机器，
>   这件事以前是必然会发生的。
>
> 想清空重来：`--fresh-vars`。
>
> 盘上没有可引导的 ESP 项时，`--boot c` 会明确给你 `no bootable device` / UEFI shell ——
> 它不会悄悄回落到 ISO 骗你。看到这个，先查安装器写没写引导（[05-测试方法](../../knowledge/05-测试方法.md) 检查点 4）。

**进 Live 之后先确认盘在**：

```bash
lsblk          # 应该看到 vda，40G —— virtio 盘在客机里是 /dev/vda
```

**不开机检查装好的盘**（比启动快一个数量级，需要 libguestfs）：

```bash
sudo guestmount -a out/target.qcow2 -i /mnt
sudo guestumount /mnt
```

**删掉重来**：

```bash
sudo ./scripts/mipl.sh clean --disk      # 删 target.qcow2 + 它的 NVRAM（会先问一句）
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

> **已实测通过**（2026-09-18，CachyOS 宿主机 + QEMU 11.1.1 + `archlinux-2026.09.18-x86_64.iso`，
> 这是**改名前**的那份产物）：用 `sudo ./scripts/mipl.sh qemu` 启动，UEFI 引导进入 Live 环境，
> 出现 `archiso login: root (automatic login)` 与 `[root@archiso ~]#` 提示符。
> 无头复现方式见上面的 C.3。
>
> **改名（A6）之后这两行文字不会变，这是对的：** `Arch Linux <版本>` 来自
> `/etc/issue`（`filesystem` 包提供），`archiso` 来自 `/etc/hostname` —— 两者都在
> `airootfs/`，属线 C 的文件，A6 只改了 ISO 元数据与引导菜单。看到它们没变，
> 说明改名没有越界，不是没改成功。待办登记在 [06-待定事项 P1](../../knowledge/06-待定事项.md)。

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
- [ ] 引导菜单出现（systemd-boot），**标题是 `MipLinux install medium (x86_64, UEFI)`**（A6 起）
- [ ] 内核与 initramfs 加载，无报错
- [ ] 进入 Live 环境，出现登录提示（`archiso login:` —— 主机名属线 C，还没改）
- [ ] 以 `root` 登录成功（**无密码**）
- [ ] 能执行 `pacman -Q | wc -l` 并看到包数量

### 建议顺带记录的数据

给后续换源提供对照基准：

```bash
# 在 Live 环境内
pacman -Q | wc -l                          # 包总数（含依赖）。注意 129 是 packages.x86_64
                                           # 的行数，不是安装数 —— 实际会多得多
ls /etc/pacman.d/mirrorlist && head -3 /etc/pacman.d/mirrorlist
```

同时记录**构建耗时**（后面每次重建都按这个量级估算）。

---

## 常见失败与排查

| 现象 | 可能原因 |
|---|---|
| `qemu-system-x86_64: -file=...: invalid option` | `file=` 被换行拆成了独立参数 —— **Issue #8**。用 `sudo ./scripts/mipl.sh qemu`，或把 `file=` 并回 `-drive` 那一行 |
| QEMU 报找不到 `OVMF_VARS.fd` | 复制出来的名字和命令里写的名字不一致（`.4m.fd` vs `.fd`）。`mipl` 统一成固定名，不会有这个问题 |
| QEMU 报 `cannot open display` / 窗口不出现 | 脚本以 root 跑，图形会话却是你的用户的。`sudo` 默认保留 `DISPLAY` 和 `XAUTHORITY`（走 XWayland 通常没问题），但会清掉 `WAYLAND_DISPLAY`。用 `sudo DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY ./scripts/mipl.sh qemu`，或改用 C.3 的无头方式 |
| QEMU 卡在 UEFI shell，不进引导 | ISO 没有 UEFI 引导路径，或 `bootmodes` 配置错 |
| 引导菜单出现但内核加载失败 | initramfs 生成有问题，看构建日志第 6 步 |
| 卡在 `Waiting for /dev/disk/by-label/...` | `iso_label` 与实际不符 |
| 直接重启，无任何输出 | 引导器未正确写入 ISO |
| QEMU 报 `Could not access KVM kernel module` | KVM 不可用，去掉 `-enable-kvm`（会慢很多） |
| 反复出现上次的引导项 | `OVMF_VARS.fd` 没重新复制 —— `mipl qemu` 每次都会刷新 |

排查第一步永远是：

```bash
sudo ./scripts/mipl.sh doctor          # 环境对不对
sudo ./scripts/mipl.sh -n qemu         # 命令拼出来是什么
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
