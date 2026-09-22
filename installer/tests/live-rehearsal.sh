#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Live 内的排练跑：在真实的 Live 环境里驱动一次安装，验检查点 4 / 6。
#
# 这个脚本**在 Live 里跑**（它是从只读源码 ISO 上读出来的），不是在宿主机上。
# 宿主机的 `/run/mipl-src` 挂载要先做好 —— 盘号别猜，用 `lsblk` 按**容量**认：
# 源码盘是那张几百 K 的 rom，启动用的 ISO 是 2.2G 那张（挂在 /run/archiso/bootmnt）：
#
#     lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS
#     mkdir -p /run/mipl-src
#     mount -o ro /dev/sr0 /run/mipl-src      # ← 实测源码盘是 sr0
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

# 把安装日志留一份在**目标盘**上：Live 是内存盘，poweroff 之后 /tmp 里的东西
# 就没了，而失败现场恰恰是最需要留下来的。装完的系统里能直接 `cat /root/…`。
keep_log() {
  local disk="$1" log="$2" target="${3:-/mnt}" root_part
  [[ -f "$log" ]] || return 0
  # 最后一个分区是 root（第一个是 ESP）。
  # **必须带 `-l`（list 模式）**：`lsblk` 的树线（`└─`）在管道里也会输出，
  # 不带 -l 取到的就是 `└─/dev/vda2` 这种路径，`mount` 会失败 —— 实测踩过。
  root_part="$(lsblk -lpno NAME,TYPE "$disk" | awk '$2 == "part" { p = $1 } END { print p }')"
  [[ -n "$root_part" ]] || return 0
  umount -R "$target" 2>/dev/null || true
  mkdir -p "$target" || return 0
  mount "$root_part" "$target" 2>/dev/null || return 0
  mkdir -p "$target/root" && cp "$log" "$target/root/" 2>/dev/null || true
  sync
  umount "$target" 2>/dev/null || true
}

main() {
[[ $EUID -eq 0 ]] || die "这个脚本在 Live 里以 root 跑（Live 里本来就是 root）"
[[ -n "$DISK" ]] || die "用法： live-rehearsal.sh /dev/vda"
[[ -d "${SRC}/installer/backend/mipl_installer" ]] || die "${SRC} 下没有 installer/ —— 源码 ISO 挂了没？（见脚本头部注释）"
[[ -b "$DISK" ]] || die "${DISK} 不是块设备"

printf '== 目标盘 / target disk ==\n'
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS
printf '\n== 核对 / check ==\n'
printf '  待擦的盘（will be wiped）: %s\n' "$DISK"
printf '  源码（source）: %s/installer/backend\n' "$SRC"
printf '  按 Ctrl-C 中止；继续请**输入设备路径**（Ctrl-C aborts, type the path to continue）: '
read -r typed
[[ "$typed" == "$DISK" ]] || die "输入不匹配（收到 ${typed}），什么都没做"

if ! python3 -c 'import parted' 2>/dev/null; then
  printf '\n== 补 python-pyparted（线 E 落地前的临时步骤）==\n'
  pacman -S --noconfirm python-pyparted
fi

# 动手擦盘之前先把 API 名字对一遍：pyparted 是 camelCase，而 _ped 那层是 snake_case，
# 写错名字的代价是「盘已经擦了、装到一半才炸」—— 那一轮就白跑了。
printf '\n== 检查 pyparted API 名字 ==\n'
missing="$(python3 - <<'PY'
import parted
names = ["getDevice", "freshDisk", "Geometry", "FileSystem", "Partition",
         "PARTITION_NORMAL", "PARTITION_ESP"]
print(" ".join(n for n in names if not hasattr(parted, n)))
PY
)"
[[ -z "$missing" ]] || die "这个 pyparted 少了：${missing} —— 先核对上游 API（见 installer/tests/test_parted_api.py），别猜"
printf '  API 齐了：%s\n' "getDevice freshDisk Geometry FileSystem Partition PARTITION_*"

LOG=/tmp/mipl-m1-rehearsal.log
printf '\n== 跑安装器 / running the installer ==\n'
printf '给装后系统的用户设密码（password for the new user, no echo）: '
read -rsp '' PW
printf '\n'
printf '也给 root 设密码吗？不设就锁定，只能用 sudo（set a root password too? [y/N]）: '
read -r want_root
root_args=()
if [[ "$want_root" == [yY]* ]]; then
  printf 'root 密码（no echo）: '
  read -rsp '' RPW
  printf '\n'
  root_args=(--root-password-stdin)
  pw_input="$(printf '%s\n%s' "$PW" "$RPW")"
else
  pw_input="$PW"
fi

rc=0
printf '%s\n' "$pw_input" | PYTHONPATH="${SRC}/installer/backend" python3 -m mipl_installer \
  --disk "$DISK" --yes --password-stdin "${root_args[@]}" --log "$LOG" "${@:2}" || rc=$?

keep_log "$DISK" "$LOG"

if (( rc != 0 )); then
  printf '\n[FAIL] 安装器退出码 %d / installer exit code %d\n' "$rc" "$rc"
  printf '  日志已留一份在目标盘 /root/mipl-m1-rehearsal.log；这里也有一份：%s\n' "$LOG"
  printf '  （Live 的 TTY 显示不了中文是 Issue #36，日志本身是 UTF-8，不影响内容）\n'
  exit "$rc"
fi

printf '\n[OK] 装完了，盘上的样子 / done, disk layout:\n'
lsblk -f "$DISK"
printf '\n日志：%s（也留了一份在装后系统的 /root/ 下）\n' "$LOG"
printf '下一步在 Live 里执行： poweroff\n'
printf '然后在宿主机上： sudo ./scripts/mipl.sh qemu --disk target.qcow2 --boot c\n'
}

# 直接执行时跑主流程；被 `source` 进来（单测要单独调 keep_log）时只定义函数。
#
# 判据用环境变量而不是 BASH_SOURCE：Live 的 root shell 是 **zsh**，
# 那里没有 BASH_SOURCE，而本脚本带 `set -u` —— 实测 sourcing 时报
# `BASH_SOURCE[0]: parameter not set`。$0 也不行：zsh 在 source 时会把 $0 设成被 source 的文件。
if [[ -z "${MIPL_REHEARSAL_SOURCED:-}" ]]; then
  main "$@"
fi
