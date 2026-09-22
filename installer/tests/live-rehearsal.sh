#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Live 内的排练跑：在真实的 Live 环境里驱动一次安装，验检查点 4 / 6。
#
# 这个脚本**在 Live 里跑**（它是从只读源码 ISO 上读出来的），不是在宿主机上。
# 宿主机的 `/run/mipl-src` 挂载要先做好：
#
#     lsblk                                   # 确认第二个光驱是 /dev/sr1
#     mkdir -p /run/mipl-src
#     mount -o ro /dev/sr1 /run/mipl-src
#     bash /run/mipl-src/installer/tests/live-rehearsal.sh /dev/vda
#
# 源码挂在 /run/mipl-src 而不是 /mnt —— /mnt 是**安装器要用的**目标挂载点，
# 两者混在一起会让「装到哪」这件事变得说不清。
#
# 为什么还要当场装 python-pyparted：线 E 的包清单还没落地（M0 在做）。
# 它落在 Live 的内存里，不写仓库、不写目标盘 —— 线 E 合入后这一步删掉即可。
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SRC="${MIPL_SRC:-/run/mipl-src}"
DISK="${1:-}"

die() { printf '[错误] %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "这个脚本在 Live 里以 root 跑（Live 里本来就是 root）"
[[ -n "$DISK" ]] || die "用法： live-rehearsal.sh /dev/vda"
[[ -d "${SRC}/installer/mipl_installer" ]] || die "${SRC} 下没有 installer/ —— 源码 ISO 挂了没？（见脚本头部注释）"
[[ -b "$DISK" ]] || die "${DISK} 不是块设备"

printf '== 目标盘 ==\n'
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS
printf '\n== 核对 ==\n'
printf '  待擦的盘：%s\n' "$DISK"
printf '  源码：    %s/installer\n' "$SRC"
printf '  按 Ctrl-C 中止；继续请输入设备路径：'
read -r typed
[[ "$typed" == "$DISK" ]] || die "输入不匹配（收到 ${typed}），什么都没做"

if ! python3 -c 'import parted' 2>/dev/null; then
  printf '\n== 补 python-pyparted（线 E 落地前的临时步骤）==\n'
  pacman -S --noconfirm python-pyparted
fi

printf '\n== 跑安装器 ==\n'
printf '给装后系统的用户设密码（不回显）：'
read -rsp '' PW
printf '\n'
printf '%s\n' "$PW" | PYTHONPATH="${SRC}/installer" python3 -m mipl_installer \
  --disk "$DISK" --yes --password-stdin --log /tmp/mipl-m1-rehearsal.log "${@:2}"

printf '\n== 装完了，盘上的样子 ==\n'
lsblk -f "$DISK"
printf '\n日志：/tmp/mipl-m1-rehearsal.log（重启前可 rsync 出去，或直接抄进 tech/04）\n'
printf '下一步在 Live 里执行： poweroff\n'
printf '然后在宿主机上： sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c\n'
