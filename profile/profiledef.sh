#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="miplinux"
iso_label="MIPLINUX_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="MipLinux <https://github.com/MipLinux/>"
iso_application="MipLinux Live/Install Medium"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux'
           'uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86,arm64' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
# 这张表是**白名单**，不是可选优化：mkarchiso 装 airootfs 时用的是
#   cp -af --no-preserve=ownership,mode
# 也就是先把所有文件的模式重置成 umask 默认（022 → 755 目录 / 644 文件），
# 再**只**给这里列出的路径补回模式。没列进来的可执行文件进 ISO 就变成 644，
# 内核 execve 直接 EACCES —— systemd 报 203/EXEC + "Permission denied"。
# 安装器入口踩过这个坑（Issue #51）：仓库里是 755、装配副本也是 755，
# 只有 ISO 里是 644。新增可执行文件时，这里必须同步加一行。
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/root/.gnupg"]="0:0:700"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/local/lib/mipl-installer/frontend/mipl-installer"]="0:0:755"
  ["/usr/local/lib/mipl-installer/frontend/mipl-kiosk"]="0:0:755"
)
