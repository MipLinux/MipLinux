# PROFILE

**来源路径**
`/usr/share/archiso/configs/releng`

**archiso 信息**
```txt
Installed From : extra
名字           : archiso
版本           : 90-1
描述           : Tools for creating Arch Linux live and install iso images
架构           : any
URL            : https://gitlab.archlinux.org/archlinux/archiso
软件许可       : GPL-3.0-or-later
组             : 无
提供           : 无
依赖于         : arch-install-scripts  bash  dosfstools  e2fsprogs  erofs-utils  libarchive  libisoburn  mtools  squashfs-tools
可选依赖       : edk2-ovmf: for emulating UEFI with run_archiso [已安装]
                 gnupg: for OpenPGP signature verification of rootfs over PXE [已安装]
                 grub: for grub support in the ISO
                 openssl: for CMS signature verification of PXE artifacts and rootfs over PXE [已安装]
                 qemu-desktop: for run_archiso [已安装]
依赖它         : 无
被可选依赖     : 无
与它冲突       : 无
取代           : 无
安装后大小     : 228.82 KiB
打包者         : Robin Candau <antiz@archlinux.org>
编译日期       : 2026年09月02日 星期三 01时04分24秒
安装日期       : 2026年09月18日 星期五 18时21分46秒
安装原因       : 单独指定安装
安装脚本       : 否
验证者         : 数字签名
```

**拷贝日期**
`2026年9月18日星期五 中国标准时间 18:21:58`

---

## 与 releng 的有意差异

「`profile/` 与 releng 零差异」是 A1 的验收标准，不是永久状态。差异只有下面这几处，
**每一处都必须写在这里** —— 没有登记的差异，就等于下次 diff 时说不清是谁改坏的。

| 日期 | 文件 | 差异 | 为什么 |
|---|---|---|---|
| 2026-09-18 | `packages.x86_64` | 首尾各加一行分区注释（`# ==> 基础 · 从 releng 继承，勿动 <==`） | 两位长期开发者共写这一个文件，按注释分段是唯一不撞车的方式 |
| 2026-09-18 | `PROFILE.md` | 新增本文件 | 记录来源、archiso 版本、拷贝日期，否则「零差异」无从复核 |
| 2026-09-18 | `profiledef.sh` | `iso_name` / `iso_label` / `iso_publisher` / `iso_application` 四个变量 | A6 改名（P1 定案：MipLinux） |
| 2026-09-18 | `efiboot/loader/entries/*.conf`、`syslinux/archiso_{head,sys-linux,pxe-linux}.cfg`、`grub/{grub,loopback}.cfg` | 菜单标题与帮助文本里的 `Arch Linux` → `MipLinux` | 同上；这些文件都会进 ISO，是用户能看见的那一层 |

**复核方式**（容器里跑，参照物就是上面记的那个 archiso 版本）：

```bash
# profile 只读挂在 /profile（mipl shell / mipl build 都会挂）
diff -r --no-dereference /usr/share/archiso/configs/releng /profile
```

**没改的东西也在这里说清楚：** `%ARCH%` / `%INSTALL_DIR%` / `%ARCHISO_UUID%`、
`archisobasedir=` / `archisosearchuuid=`、`mkinitcpio-archiso` 的 hook 名、
`efiboot/loader/loader.conf` 里的 entry 文件名 —— 这些是内核与 mkinitcpio 的契约，
不是品牌，改了引导就挂。`airootfs/` 里的品牌文本属线 C，登记在
[06-待定事项 P1](../docs/knowledge/06-待定事项.md)。

一条命令检查有没有漏改（不需要 root）：

```bash
./scripts/check-identity.sh
```
