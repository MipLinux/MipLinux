#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# mipl · MipLinux 项目操作台
#
# 把「每次都要手抄的长命令」变成一条不会抄错的命令。
#
#   sudo ./scripts/mipl.sh doctor        环境自检（换机器第一件事）
#   sudo ./scripts/mipl.sh target        建一块空的目标盘（装系统用）
#   sudo ./scripts/mipl.sh qemu          启动 QEMU（--disk 挂盘，--boot c 从盘启动）
#   sudo ./scripts/mipl.sh shell         进入 nspawn 构建容器
#
# 四条设计约束，每条都来自实际踩过的坑（GitHub Issues）：
#
#   1. 整个脚本一律要求 root，不自己 sudo。
#      同一件事一会儿降权一会儿提权，出问题时根本分不清是谁的权限在起作用
#      （out/ 里的产物一会儿归你、一会儿归 root 就是典型症状）。
#      所以：非 root → 打印该敲的命令，然后退出。
#
#   2. 一切路径从脚本自身位置推导，不含 $HOME、不含写死的目录。
#      两台机器的仓库路径不同 —— 见 Issue #7 里文档写死了
#      ~/Code/Projects/MipLinux/out/，换个人就对不上。
#
#   3. OVMF 固件靠探测，不硬编码。
#      Arch 是 /usr/share/edk2/x64/OVMF_{CODE,VARS}.4m.fd，
#      Fedora 是 /usr/share/edk2/ovmf/OVMF_{CODE,VARS}_4M.fd，
#      Debian 是 /usr/share/OVMF/OVMF_{CODE,VARS}.fd。
#
#   4. QEMU 参数用 bash 数组拼装，一个参数就是数组的一个元素。
#      手写时换行会把 file= 拆成独立的 -file=，QEMU 直接报
#      `invalid option` —— 见 Issue #8。
#
#   5. 「文件在不在」不等于「东西能不能用」。
#      bootstrap 缓存存在 ≠ 它下完整了；容器里有 etc/os-release ≠ 它进得去。
#      Issue #32 就是这么来的：半截的 tarball 被当成缓存、残缺的解压被当成
#      「已初始化」，一路绿灯到 systemd-nspawn 抛 execv 才炸，而那句报错
#      和真正的原因隔了三层。所以状态判断一律落在「能不能用」上，
#      并且 doctor / shell / build 三个入口用的是同一段判断（scripts/mipl-lib.sh）。
#
# ─────────────────────────────────────────────────────────────────────
# 用法：  sudo ./scripts/mipl.sh <命令> [参数]
#         sudo ./scripts/mipl.sh --help
#
# 环境变量要写在 sudo 后面（sudo 默认会清掉你的环境）：
#         sudo MIPL_MEM=8192 ./scripts/mipl.sh qemu
#
# fish 用户： ./scripts/mipl.fish 是同目录的薄封装，逻辑不重复实现。
#
# 文档：  docs/work/tech/02-构建与QEMU测试.md
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

MIPL_VERSION="0.5.0"

# ── 自身定位 ──────────────────────────────────────────────────────────
# 循环解引用：脚本被软链到 ~/.local/bin/mipl 时也能定位到真实仓库。
mipl_self_dir() {
  local src="${BASH_SOURCE[0]}" dir
  while [[ -L "$src" ]]; do
    dir="$(cd -P "$(dirname "$src")" >/dev/null && pwd)"
    src="$(readlink "$src")"
    if [[ "$src" != /* ]]; then
      src="${dir}/${src}"
    fi
  done
  cd -P "$(dirname "$src")" >/dev/null && pwd
}

SCRIPT_DIR="$(mipl_self_dir)"
REPO_ROOT="${MIPL_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

# ── 配置（全部可用环境变量覆盖）───────────────────────────────────────
OUT_DIR="${MIPL_OUT_DIR:-${REPO_ROOT}/out}"
CONTAINER_DIR="${MIPL_CONTAINER:-/var/lib/machines/archbuild}"
MACHINE_NAME="${MIPL_MACHINE:-archbuild}"
MEM_MB="${MIPL_MEM:-4096}"
# QEMU 的 vCPU 数。默认 4：Live 引导 1 个也够，但进去敲命令、以及以后挂盘
# 装系统（A5 的 mipl qemu --disk）时单核会明显拖慢。
SMP="${MIPL_SMP:-4}"
# 容器内 mkarchiso 的工作目录。**不要用 /tmp**：systemd-nspawn 默认把容器的
# /tmp 覆盖成一块 tmpfs（内存），默认只有 10% 内存大小（本机 30 GiB → 3.0 GiB）。
# 构建树到写 EFI 镜像时已有近 3 GiB，撞上就是：
#     plain_io read/write: No space left on device
# 这就是 Issue #6「/tmp 空间不足」的真身。容器里的 /var/tmp 是普通目录，
# 落在宿主磁盘上（2026-09-18 手工构建用的就是 /var/tmp/mkarchiso）。
INNER_WORK_DIR="${MIPL_WORK_DIR:-/var/tmp/mipl-work}"
# 仓库里的 profile：构建的「源代码」。容器不复制它，只读挂载到 /profile ——
# 这样「构建用的是哪一份」就是结构上确定的，不靠人记。
REPO_PROFILE="${MIPL_PROFILE:-${REPO_ROOT}/profile}"
# 容器内原版 releng：基线（--baseline）用的那份，由容器里的 archiso 包提供。
BASELINE_PROFILE="/usr/share/archiso/configs/releng"
# 挂进容器的固定路径。build 与 shell 都挂在同一个位置，两个入口看到的是一份东西。
PROFILE_INNER="/profile"
# 目标文件用固定名。源文件名各发行版不同（OVMF_VARS.4m.fd / OVMF_VARS_4M.fd），
# 固定名意味着 QEMU 参数永远不需要跟着变——Issue #8 的第二个错误就出在这里。
VARS_DST="${OUT_DIR}/OVMF_VARS.fd"
# 目标盘（A5 的 mipl target）：给线 B 装系统用。默认建在 out/ 里 —— 整个 out/
# 都被 .gitignore 忽略，盘和它的派生文件都不会误进 git。
# 40G 是 qcow2 的**虚拟**大小，实际占用随写入增长（刚建好只有约 200 KiB）。
TARGET_DISK_NAME="${MIPL_DISK_NAME:-target.qcow2}"
TARGET_DISK_SIZE="${MIPL_DISK_SIZE:-40G}"
# bootstrap 的本地缓存。构建走的是 baseline-build.sh，但 doctor 要报告它的状态，
# clean --bootstrap 要删它，两边必须说同一个路径。
BOOTSTRAP_FILE="${MIPL_BOOTSTRAP_FILE:-/tmp/archlinux-bootstrap-x86_64.tar.zst}"
BOOTSTRAP_CHECKSUMS_FILE="${MIPL_CHECKSUMS_FILE:-${BOOTSTRAP_FILE}.sha256sums.txt}"
# 容器里的软件源与 DNS。构建时由 baseline-build.sh 生成、只读挂进容器 ——
# 容器自带的 mirrorlist 可能只剩 Include 转发、resolv.conf 更是纯注释，
# 两者都会让 pacman 静默失败、archiso / mkinitcpio 装不上 ——
# 这是 Issue #32 那条链上的另一半：容器「看起来装上了」和「真的能用」是两回事。
MIRROR_URL="${MIPL_MIRROR_URL:-https://mirrors.tuna.tsinghua.edu.cn/archlinux/\$repo/os/\$arch}"
DNS_FALLBACK="${MIPL_DNS_FALLBACK:-223.5.5.5 119.29.29.29 1.1.1.1}"

# ── 共用库（容器健康检查、颜色约定、提示里怎么称呼自己）──────────────
MIPL_LIB="${SCRIPT_DIR}/mipl-lib.sh"
if [[ ! -r "$MIPL_LIB" ]]; then
  printf '[错误] 缺少共用库：%s —— 仓库不完整或脚本被单独拷走了\n' "$MIPL_LIB" >&2
  exit 1
fi
# shellcheck source=scripts/mipl-lib.sh
MIPL_LIB_COLORS=1 . "$MIPL_LIB"

DRY_RUN=0

# ── 输出 ──────────────────────────────────────────────────────────────
# 颜色由共用库按同一套约定定下（非终端或 NO_COLOR 就不上色），这里不再判断 ——
# 两份判断迟早会漂移，而「两个入口对同一件事说法不同」正是 Issue #32 的形态。
info() { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s[ok]%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%s[错误]%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }
note() { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF"; }

# ── 执行封装（--dry-run 只打印）───────────────────────────────────────
# 只给「含空格」的参数加引号：直接 %q 会把 if=pflash,format=raw 也转义成
# if=pflash\,format=raw —— 能跑，但没法读，而可读正是 dry-run 的全部意义。
quote_cmd() {
  local a out=""
  for a in "$@"; do
    if [[ "$a" == *[[:space:]]* ]]; then out+="'${a}' "
    else out+="${a} "; fi
  done
  printf '%s' "${out% }"
}

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '%s[试运行]%s %s\n' "$C_DIM" "$C_OFF" "$(quote_cmd "$@")"
    return 0
  fi
  "$@"
}

have() { command -v "$1" >/dev/null 2>&1; }

# ── 权限：一律要求 root ───────────────────────────────────────────────
# 不提供「部分命令自动 sudo」这种半吊子模式。原来 shell/stop/build 会自己套
# sudo，结果是同一个脚本有时降权有时提权、out/ 里的产物一会儿归你一会儿归
# root，出问题时根本分不清是谁的权限在起作用。现在只有一种模式：
#
#   不是 root → 什么都不做，直接退出，并把该敲的命令原样打给你。
#
# 检查放在最前面（连 --help 也要拦）：「这条命令会以什么身份跑」这件事，
# 不该因为参数不同而不同。
require_root() {
  if [[ ${EUID} -eq 0 ]]; then
    return 0
  fi

  printf '%s[错误]%s 需要 root 权限，当前是普通用户（uid=%s）。\n' \
    "$C_ERR" "$C_OFF" "$EUID" >&2
  echo >&2
  echo "这个脚本会动构建容器、OVMF 固件和 out/ 里的产物，一律以 root 运行。" >&2
  echo "它不会自己 sudo（那属于隐式提权），请显式提权后重跑：" >&2
  echo >&2
  printf '  sudo %s\n' "$0 $*" >&2
  echo >&2
  echo "要传环境变量，写在 sudo 后面（sudo 默认会清掉你的环境）：" >&2
  printf '  sudo MIPL_MEM=8192 %s qemu\n' "$0" >&2
  exit 1
}

# 需要 root 的操作。脚本入口已经强制 root，所以这里就是直接跑 ——
# 保留这个函数只是为了在调用点标明「这一步为什么需要特权」。
run_root() { run "$@"; }

fmt_size() {
  awk -v b="${1:-0}" 'BEGIN{
    split("B KB MB GB TB", a, " "); i = 1
    while (b >= 1024 && i < 5) { b /= 1024; i++ }
    if (i == 1) printf "%d %s\n", b, a[i]; else printf "%.1f %s\n", b, a[i]
  }'
}

file_size() { fmt_size "$(stat -c %s "$1" 2>/dev/null || echo 0)"; }

# ── 发行版判定 ────────────────────────────────────────────────────────
os_field() {
  [[ -r /etc/os-release ]] || { echo ""; return 0; }
  sed -n "s/^$1=//p" /etc/os-release | head -1 | tr -d '"'
}

distro_family() {
  local id like
  id="$(os_field ID)"; like="$(os_field ID_LIKE)"
  case "${id} ${like}" in
    *arch*|*cachyos*|*manjaro*)          echo arch ;;
    *fedora*|*rhel*|*centos*)            echo fedora ;;
    *debian*|*ubuntu*|*linuxmint*)       echo debian ;;
    *)                                   echo unknown ;;
  esac
}

distro_pretty() {
  local name id
  name="$(os_field PRETTY_NAME)"; id="$(os_field ID)"
  if [[ -n "$name" ]]; then echo "${name} (ID=${id}, 类 $(distro_family))"
  else echo "未知（读不到 /etc/os-release）"; fi
}

# ── 路径存在性检查 ────────────────────────────────────────────────────
# 容器目录 /var/lib/machines 是 0700。脚本一律以 root 运行，所以这里不需要
# 再兜「权限不足」的分支 —— 那正是改成强制 root 换来的简化。
path_exists() { [[ -e "$1" ]]; }

# ── OVMF 固件探测 ─────────────────────────────────────────────────────
ovmf_search_dirs() {
  # 显式指定了目录就只找那里，不做兜底扫描 —— 这样「找不到」也是可复现的，
  # 而不是被某处的兜底命中掩盖掉。
  if [[ -n "${MIPL_OVMF_DIR:-}" ]]; then
    if [[ -d "$MIPL_OVMF_DIR" ]]; then printf '%s\n' "$MIPL_OVMF_DIR"; fi
    return 0
  fi
  local -a dirs=()
  dirs+=(
    /usr/share/edk2/x64        # Arch / CachyOS
    /usr/share/edk2/ovmf       # Fedora / RHEL
    /usr/share/edk2/ovmf/4m
    /usr/share/OVMF/x64        # Debian / Ubuntu（/usr/share/OVMF 常是软链）
    /usr/share/OVMF
    /usr/share/edk2-ovmf/x64   # Arch 的旧布局
    /usr/share/qemu
  )
  local d
  for d in "${dirs[@]}"; do
    if [[ -d "$d" ]]; then printf '%s\n' "$d"; fi
  done
}

# 同一目录里可能有 4M / 普通 / ms / secboot / snakeoil 多种变体，优先级如下。
# 顺序要紧：secboot / ms / snakeoil 必须先判，否则 OVMF_VARS_4M.secboot.fd
# 会先被 4M 规则命中，被判成优选。
_ovmf_rank() {
  case "$1" in
    *secboot*)          echo 3 ;;   # 需要 Secure Boot + SMM，测 Linux 不用
    *[._]ms[._]*)       echo 2 ;;   # 微软密钥版，测 Linux 不用
    *snakeoil*)         echo 3 ;;   # 自签证书版，测 Linux 不用
    *4[Mm]*)            echo 0 ;;   # OVMF_VARS.4m.fd / OVMF_VARS_4M.fd
    *)                  echo 1 ;;   # OVMF_VARS.fd
  esac
}

# 探测结果写入全局：OVMF_CODE / OVMF_VARS
detect_ovmf() {
  local -a tried=()
  local dir v c r

  if [[ -n "${MIPL_OVMF_CODE:-}" || -n "${MIPL_OVMF_VARS:-}" ]]; then
    [[ -n "${MIPL_OVMF_CODE:-}" && -n "${MIPL_OVMF_VARS:-}" ]] \
      || die "MIPL_OVMF_CODE 与 MIPL_OVMF_VARS 必须同时设置"
    [[ -r "$MIPL_OVMF_CODE" ]] || die "MIPL_OVMF_CODE 不可读：$MIPL_OVMF_CODE"
    [[ -r "$MIPL_OVMF_VARS" ]] || die "MIPL_OVMF_VARS 不可读：$MIPL_OVMF_VARS"
    OVMF_CODE="$MIPL_OVMF_CODE"; OVMF_VARS="$MIPL_OVMF_VARS"
    return 0
  fi

  local best_v="" best_c="" best_rank=99
  while IFS= read -r dir; do
    tried+=("$dir")
    # 先找 VARS，再把名字里的 VARS 换成 CODE —— 这样 .4m / _4M / 无后缀
    # 三种命名都能自动配对，不需要为每个发行版写一条规则。
    while IFS= read -r v; do
      [[ -n "$v" ]] || continue
      c="$(dirname "$v")/$(basename "${v/OVMF_VARS/OVMF_CODE}")"
      [[ -r "$c" ]] || continue
      r="$(_ovmf_rank "$(basename "$v")")"
      if [[ "$r" -lt "$best_rank" ]]; then
        best_rank="$r"; best_v="$v"; best_c="$c"
      fi
    done < <(find "$dir" -maxdepth 1 -name 'OVMF_VARS*.fd' -type f 2>/dev/null | sort)
  done < <(ovmf_search_dirs)

  if [[ -n "$best_v" ]]; then
    OVMF_CODE="$best_c"; OVMF_VARS="$best_v"
    return 0
  fi

  # 兜底：整片 /usr/share 扫一遍，最多 4 层。指定了 MIPL_OVMF_DIR 就不兜底，
  # 否则「找不到」永远复现不出来，用户也没法验证自己指对了目录。
  if [[ -z "${MIPL_OVMF_DIR:-}" ]]; then
    while IFS= read -r v; do
      [[ -n "$v" ]] || continue
      c="$(dirname "$v")/$(basename "${v/OVMF_VARS/OVMF_CODE}")"
      if [[ -r "$c" ]]; then
        OVMF_CODE="$c"; OVMF_VARS="$v"
        warn "固件不在常见位置，兜底扫描命中：$v"
        return 0
      fi
    done < <(find /usr/share -maxdepth 4 -name 'OVMF_VARS*.fd' -type f 2>/dev/null | sort)
  fi

  {
    echo "找不到 OVMF 固件（需要 OVMF_CODE*.fd 与 OVMF_VARS*.fd 成对存在）。"
    echo
    echo "已经找过这些目录："
    if [[ ${#tried[@]} -eq 0 ]]; then
      echo "  （一个都不存在）"
    else
      printf '  %s\n' "${tried[@]}"
    fi
    echo
    echo "按发行版装上固件包再试："
    echo "  Arch / CachyOS   sudo pacman -S edk2-ovmf qemu-desktop"
    echo "  Fedora           sudo dnf install edk2-ovmf qemu-kvm"
    echo "  Debian / Ubuntu  sudo apt install ovmf qemu-system-x86"
    echo
    echo "如果固件装在别处，直接指着它："
    echo "  MIPL_OVMF_CODE=/路径/OVMF_CODE.fd \\"
    echo "  MIPL_OVMF_VARS=/路径/OVMF_VARS.fd ${MIPL_CMD} qemu"
  } >&2
  return 1
}

# ── 产物 ──────────────────────────────────────────────────────────────
ensure_out_dir() { run mkdir -p "$OUT_DIR"; }

# 最新 ISO 的路径；没有则返回 1
latest_iso() {
  local -a isos=()
  shopt -s nullglob
  isos=("${OUT_DIR}"/*.iso)
  shopt -u nullglob
  [[ ${#isos[@]} -gt 0 ]] || return 1
  ls -1t "${isos[@]}" 2>/dev/null | head -1
}

# ── 容器 ──────────────────────────────────────────────────────────────
machine_running() {
  have machinectl || return 1
  machinectl list --no-legend --no-pager 2>/dev/null \
    | awk 'NF {print $1}' | grep -qx "$MACHINE_NAME"
}

# 「容器建过没有」和「容器能不能用」是两回事。
# 前者原来只看 etc/os-release —— 而它在 bootstrap 归档里排第 630 条，
# usr/bin/bash 排第 5815 条（共 33105 条）。于是半途而废的解压会被判成
# 「已初始化」，一路绿灯到 systemd-nspawn 那里才炸（Issue #32）。
# 现在这个函数只回答「建过没有」，「能不能用」交给 mipl_container_health。
container_exists() { path_exists "${CONTAINER_DIR}/etc/os-release"; }

# 容器的体检报告。与 baseline-build.sh 里的 report_container_health 说的是
# 同一件事 —— 两处排版不同没关系，判断依据必须只有一份，就是共用库里的
# mipl_container_health。
#
# $2：容器是不是正跑着（1 = 是）。跑着的容器 nspawn 会拒绝再进（Issue #4），
#     这时候要报的是「先 stop」，而不是跟着报一句「已初始化」。
# $3：要不要打 [ok] 那行（默认 1）。调用方只想知道结论时关掉它。
report_container_health() {
  local running="${2:-0}" print_ok="${3:-1}"
  local -a local_missing=()
  if mipl_container_health "$CONTAINER_DIR" local_missing; then
    if [[ $print_ok -eq 1 ]]; then
      if [[ $running -eq 1 ]]; then
        _miss "container" "${CONTAINER_DIR}（正在运行！用完记得 ${MIPL_CMD} stop，见 Issue #4）"
      else
        _line "container" "${CONTAINER_DIR}（已初始化，shell ${mipl_shell}）"
      fi
    fi
    return 0
  fi
  _bad "container" "${CONTAINER_DIR}（残缺！缺：$(mipl_missing_paths local_missing)）"
  local item label paths p found
  for item in "${MIPL_HEALTH_ITEMS[@]}"; do
    label="${item%%|*}"
    IFS='|' read -r -a paths <<< "${item#*|}"
    found=""
    for p in "${paths[@]}"; do
      if [[ -e "${CONTAINER_DIR}/${p}" || -L "${CONTAINER_DIR}/${p}" ]]; then
        found="/${p}"; break
      fi
    done
    if [[ -n "$found" ]]; then
      note "     [ok] ${label}  ${found}"
    else
      note "     [缺] ${label}  （找过：${paths[*]/#//}）"
    fi
  done
  note "     这不是「还没建」，是 bootstrap 没解压完 —— 重建："
  note "       rm -rf ${CONTAINER_DIR}"
  note "       ${MIPL_CMD} build"
  return 1
}

# ── 命令：doctor ──────────────────────────────────────────────────────
cmd_doctor() {
  local report=0
  [[ "${1:-}" == "--report" ]] && report=1

  detect_ovmf || true   # 允许失败，这里只报告

  if [[ $report -eq 1 ]]; then
    _doctor_report
    return 0
  fi

  printf '%smipl %s · 环境自检%s\n' "$C_INFO" "$MIPL_VERSION" "$C_OFF"
  printf '%s%s%s\n' "$C_DIM" "────────────────────────────────────────────────────────────" "$C_OFF"

  # 标签一律 ASCII、说明写中文：printf 的 %-Ns 按字节补齐，中文标签
  # 会把表格撑歪，中英混排更是必然歪。列只能对齐在「标签全 ASCII」上。
  _line() { printf '%s[ok]%s %-20s %s\n' "$C_OK" "$C_OFF" "$1" "$2"; }
  _miss() { printf '%s[--]%s %-20s %s\n' "$C_WARN" "$C_OFF" "$1" "$2"; }
  _bad()  { printf '%s[!!]%s %-20s %s\n' "$C_ERR" "$C_OFF" "$1" "$2"; }

  _line "repo"     "$REPO_ROOT"
  _line "cwd"      "$PWD  （脚本不依赖它）"
  if [[ ${EUID} -eq 0 ]]; then
    _line "user"   "uid=0（root）"
  else
    _bad  "user"   "uid=${EUID}（非 root —— 本该在入口就被拒绝，请报告这个 bug）"
  fi
  _line "distro"   "$(distro_pretty)"

  local families_ok=1
  if have systemd-nspawn; then _line "nspawn" "$(command -v systemd-nspawn)"
  else _bad "nspawn" "缺失 —— 构建容器必需"; families_ok=0; fi

  if have machinectl; then _line "machinectl" "$(command -v machinectl)"
  else _miss "machinectl" "缺失 —— 无法查看/关闭容器"; families_ok=0; fi

  if have qemu-system-x86_64; then
    _line "qemu" "$(qemu-system-x86_64 --version 2>/dev/null | head -1 | awk '{print $4}')"
  else
    _bad "qemu" "缺失 —— 无法测试 ISO"; families_ok=0
  fi

  if [[ -w /dev/kvm ]]; then _line "kvm" "/dev/kvm 可读写（硬件加速可用）"
  elif [[ -e /dev/kvm ]]; then _miss "kvm" "/dev/kvm 存在但不可写"
  else _miss "kvm" "/dev/kvm 不存在 —— QEMU 只能软件模拟（很慢）"; fi

  # 容器
  if container_exists; then
    # 「有 etc/os-release」不等于「能进去」。残缺容器必须在这里就现形，
    # 而不是等 systemd-nspawn 抛一句 execv(...) failed（Issue #32）。
    local running=0
    machine_running && running=1
    report_container_health "$CONTAINER_DIR" "$running" || true
    # 工具链：mkarchiso / pacstrap 来自 archiso，mkinitcpio 来自它自己的包 ——
    # **archiso 不依赖 mkinitcpio**，所以只装 archiso 永远不会带上它。
    # 缺哪几个要逐个点名，否则「pacman -S archiso 不就完了」会把 mkinitcpio
    # 一直漏下去（那正是「容器里找不到 archiso 和 mkinitcpio」的来路）。
    local t missing_tools=()
    for t in mkarchiso pacstrap arch-chroot mkinitcpio mksquashfs xorriso mkfs.vfat; do
      path_exists "${CONTAINER_DIR}/usr/bin/${t}" || missing_tools+=("$t")
    done
    if [[ ${#missing_tools[@]} -eq 0 ]]; then
      _line "toolchain" "mkarchiso / pacstrap / mkinitcpio / mksquashfs / xorriso / mkfs.vfat 齐全"
    elif [[ ! -x "${CONTAINER_DIR}/usr/bin/pacman" ]]; then
      _bad "toolchain" "容器不完整（连 pacman 都没有），先重建容器再说装包"
    else
      _miss "toolchain" "缺：${missing_tools[*]}"
      note "     补齐（进容器后，或直接 ${MIPL_CMD} build 会自己装）："
      note "       pacman -S --needed archiso mkinitcpio arch-install-scripts"
      note "     mkinitcpio 单独列：archiso 不依赖它，只装 archiso 装不上它。"
    fi
    # 动态链接器单独列一行：它缺了同样是「execv ... No such file or directory」，
    # 报错长得和「容器里没有 bash」一模一样，不单独查就分不清（Issue #32）。
    if [[ -e "${CONTAINER_DIR}/usr/lib/ld-linux-x86-64.so.2" ]]; then
      _line "container loader" "/usr/lib/ld-linux-x86-64.so.2 在（能执行容器里的二进制）"
    else
      _bad "container loader" "缺 /usr/lib/ld-linux-x86-64.so.2 —— 容器里的程序一个都起不来"
    fi
  else
    _miss "container" "${CONTAINER_DIR}（尚未创建 —— 先跑 ${MIPL_CMD} build）"
  fi

  # 容器里的源与 DNS —— 这两个是「装不上 archiso / mkinitcpio」的常见真凶，
  # 所以在 doctor 里也要能看到。构建时宿主机生成好后只读挂进容器。
  _line "pacman source" "${MIRROR_URL}"
  if grep -qE '^[[:space:]]*nameserver[[:space:]]' /etc/resolv.conf 2>/dev/null; then
    _line "container DNS" "$(awk '/^[[:space:]]*nameserver[[:space:]]/ {printf "%s ", $2}' /etc/resolv.conf)"
  else
    _miss "container DNS" "宿主机 /etc/resolv.conf 里没有 nameserver —— 构建时会用兜底的 ${DNS_FALLBACK}"
  fi

  # bootstrap 缓存：它是不是「下好了」不能只看在不在 —— 截断的文件同样在，
  # 而它会在解压时把容器做成残缺的。这里按构建脚本用的同一套标准报（Issue #32）。
  if [[ -f "$BOOTSTRAP_FILE" ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then
      _miss "bootstrap" "$(file_size "$BOOTSTRAP_FILE")（试运行：不下载清单、不校验）"
    else
      local bs_rc=0
      bootstrap_cache_ok || bs_rc=$?
      case $bs_rc in
        0)  _line "bootstrap" "$(file_size "$BOOTSTRAP_FILE")，sha256 与镜像清单一致、zstd 完整" ;;
        2)  _miss "bootstrap" "$(file_size "$BOOTSTRAP_FILE")（本地还没有 sha256sums.txt，验不了；构建时会取一份再验）" ;;
        *)  _bad "bootstrap" "$(file_size "$BOOTSTRAP_FILE")：$(mipl_checksum_reason "$MIPL_CHK_LAST")" ;;
      esac
      [[ -f "$BOOTSTRAP_CHECKSUMS_FILE" ]] \
        || note "     清单：${BOOTSTRAP_CHECKSUMS_FILE}（构建时会从镜像取）"
      note "     清掉缓存： ${MIPL_CMD} clean --bootstrap"
    fi
  else
    _miss "bootstrap" "还没有本地缓存 —— ${MIPL_CMD} build 会下载到 ${BOOTSTRAP_FILE}"
  fi

  # 固件
  if [[ -n "${OVMF_CODE:-}" && -n "${OVMF_VARS:-}" ]]; then
    _line "OVMF_CODE" "${OVMF_CODE}  ($(file_size "$OVMF_CODE"))"
    _line "OVMF_VARS" "${OVMF_VARS}  ($(file_size "$OVMF_VARS"))"
  else
    _bad "OVMF" "未找到固件 —— 见上方提示，或显式指定 MIPL_OVMF_CODE / MIPL_OVMF_VARS"
  fi

  # 产物与磁盘
  local iso
  if iso="$(latest_iso)"; then
    _line "ISO" "$(basename "$iso")  ($(file_size "$iso"))"
  else
    _miss "ISO" "${OUT_DIR} 里还没有 .iso —— 先跑 ${MIPL_CMD} build"
  fi

  # 目标盘（A5）：装系统用。有就报一句，没有就告诉你怎么建 ——
  # 「线 B 卡在没有盘」这件事，应该在这里就能看见。
  local tdisk="${OUT_DIR}/${TARGET_DISK_NAME}" tinfo
  if [[ -f "$tdisk" ]]; then
    tinfo="$(file_size "$tdisk") 占用"
    if have qemu-img; then tinfo="${tinfo}，虚拟 $(disk_virtual_size "$tdisk")"; fi
    _line "target disk" "$(basename "$tdisk")  (${tinfo})"
  else
    _miss "target disk" "还没有 —— 建一块： ${MIPL_CMD} target"
  fi

  # profile：构建的「源代码」。它不在，mipl build 会直接拒绝运行 ——
  # 所以这一项要能和 ISO 并排看见。
  if [[ -f "${REPO_PROFILE}/profiledef.sh" ]]; then
    local iso_name
    iso_name="$(sed -n 's/^iso_name="\(.*\)"/\1/p' "${REPO_PROFILE}/profiledef.sh" | head -1)"
    _line "profile" "${REPO_PROFILE}  (iso_name=${iso_name:-未知}) → 容器内 ${PROFILE_INNER}"
  else
    _bad "profile" "仓库里没有 ${REPO_PROFILE}/profiledef.sh —— ${MIPL_CMD} build 会拒绝运行"
  fi

  if [[ -d "$OUT_DIR" ]]; then
    _line "disk/out" "$(df -h --output=avail "$OUT_DIR" 2>/dev/null | tail -1 | tr -d ' ') 可用"
  fi
  local host_dir; host_dir="$(dirname "$CONTAINER_DIR")"
  if [[ -x "$host_dir" ]]; then
    _line "disk/var" "$(df -h --output=avail "$host_dir" 2>/dev/null | tail -1 | tr -d ' ') 可用（$host_dir，Issue #6 的坑）"
  fi

  if [[ $families_ok -eq 0 ]]; then
    echo
    info "补齐依赖（按你的发行版）："
    cmd_deps
  fi
  echo
  note "把本机环境填进文档： ${MIPL_CMD} doctor --report"
}

_doctor_report() {
  local iso
  iso="$(latest_iso || echo "")"
  cat <<EOF
<!-- 由 ${MIPL_CMD} doctor --report 生成 -->
| 项 | 值 |
|---|---|
| 发行版 | $(distro_pretty) |
| 仓库路径 | \`${REPO_ROOT}\` |
| systemd-nspawn | \`$(command -v systemd-nspawn 2>/dev/null || echo 缺失)\` |
| qemu-system-x86_64 | \`$(have qemu-system-x86_64 && qemu-system-x86_64 --version 2>/dev/null | head -1 || echo 缺失)\` |
| /dev/kvm | $(if [[ -w /dev/kvm ]]; then echo "可用"; else echo "不可用"; fi) |
| OVMF_CODE | \`${OVMF_CODE:-未找到}\` |
| OVMF_VARS | \`${OVMF_VARS:-未找到}\` |
| 最新 ISO | $(if [[ -n "$iso" ]]; then echo "\`$(basename "$iso")\` ($(file_size "$iso"))"; else echo "无"; fi) |
EOF
}

# ── 目标盘与它的 NVRAM ────────────────────────────────────────────────
# 一块盘和它的 UEFI 变量是**一套**测试资产：安装器写进 NVRAM 的引导项，决定
# 「装完重启能不能进新系统」。所以变量文件按盘走，不与 ISO 测试共用那一份 ——
# 否则任何人跑一次普通 mipl qemu（测构建、测中文），装好系统的引导项就被刷掉了。
# 名字刻意避开 mipl clean 的 OVMF_VARS*.fd glob：清 ISO 测试残留不该误伤一块
# 装好系统的盘。删盘走 mipl clean --disk。
disk_vars_path() {
  local disk="$1"
  printf '%s/%s.vars.fd\n' "$(dirname -- "$disk")" "$(basename -- "${disk%.*}")"
}

# 盘的格式交给 qemu-img 探测，而不是假设 qcow2：format= 写错时 QEMU 会拒绝启动，
# 报错却像「镜像损坏」，很难查。
# 用人类可读输出而不是 --output=json：JSON 里嵌套了 child 节点，第一处
# "format" 是子节点的 "file"，按行解析会拿到错误答案。
disk_format() {
  LC_ALL=C qemu-img info -- "$1" 2>/dev/null | sed -n 's/^file format: //p' | head -1
}

disk_virtual_size() {
  local n
  n="$(LC_ALL=C qemu-img info -- "$1" 2>/dev/null \
      | sed -n 's/^virtual size: .*(\([0-9]*\) bytes).*/\1/p' | head -1)"
  if [[ -n "$n" ]]; then fmt_size "$n"; else printf '未知\n'; fi
}

# 变量文件怎么来：refresh = 从固件重拷（NVRAM 清空）；keep = 没有才建，有就留着。
ensure_vars() {
  local dst="$1" how="$2"
  if [[ "$how" == keep && -f "$dst" ]]; then
    note "变量文件：${dst}（保留 —— NVRAM 里的引导项还在，从盘启动靠的就是它）"
    return 0
  fi
  run cp -f "$OVMF_VARS" "$dst"
  if [[ $DRY_RUN -eq 0 ]]; then
    ok "变量文件：${dst}（新拷一份，NVRAM 是干净的）"
  fi
  return 0
}

# ── 命令：vars ────────────────────────────────────────────────────────
cmd_vars() {
  detect_ovmf || exit 1
  ensure_out_dir
  info "固件来源： $OVMF_VARS"
  note "        $OVMF_CODE"
  # 每次都重新复制：引导过的系统会把引导项写进 NVRAM，复用旧文件会让
  # 上一次的引导项影响这一次，表现为「上次能启动、这次不行」。
  ensure_vars "$VARS_DST" refresh
  if [[ $DRY_RUN -eq 0 ]]; then
    local stale
    for stale in "${OUT_DIR}"/OVMF_VARS*.fd; do
      [[ -e "$stale" ]] || continue
      [[ "$stale" == "$VARS_DST" ]] && continue
      warn "残留的旧变量文件（名字带发行版后缀，已不再使用）：$(basename "$stale")"
      note "  删掉它： ${MIPL_CMD} clean"
    done
  fi
}

# ── 命令：qemu ────────────────────────────────────────────────────────
cmd_qemu() {
  have qemu-system-x86_64 || die "找不到 qemu-system-x86_64。先跑： ${MIPL_CMD} deps"

  local iso="" disk="" boot="d" want_fresh=0 want_keep=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --disk)
        [[ -n "${2:-}" ]] || die "--disk 后面要跟目标盘（裸文件名按 ${OUT_DIR} 解析）"
        disk="$2"; shift 2 ;;
      --boot)
        [[ -n "${2:-}" ]] || die "--boot 后面要跟 d 或 c"
        boot="$2"; shift 2 ;;
      --fresh-vars) want_fresh=1; shift ;;
      --keep-vars)  want_keep=1;  shift ;;
      -*) die "未知选项：$1（用 --help 看用法）" ;;
      *)
        [[ -z "$iso" ]] || die "ISO 参数只能给一个，多出来的是：$1"
        iso="$1"; shift ;;
    esac
  done

  [[ "$boot" == d || "$boot" == c ]] \
    || die "--boot 只接受 d（光驱优先，装系统用）或 c（从盘启动），收到：${boot}"
  [[ $want_fresh -eq 0 || $want_keep -eq 0 ]] \
    || die "--fresh-vars 与 --keep-vars 只能选一个"

  # ── 目标盘 ──
  local disk_fmt="" vars_file="$VARS_DST"
  if [[ -n "$disk" ]]; then
    [[ -f "$disk" || -f "${OUT_DIR}/${disk}" ]] || die "目标盘不存在：${disk}
     先建一块： ${MIPL_CMD} target"
    [[ -f "$disk" ]] || disk="${OUT_DIR}/${disk}"
    have qemu-img || die "找不到 qemu-img（要用它探测盘的格式）。Arch → pacman -S qemu-img"
    disk_fmt="$(disk_format "$disk")"
    [[ -n "$disk_fmt" ]] || die "读不出盘的格式：${disk}
     文件可能坏了，先看： qemu-img info '${disk}'"
    vars_file="$(disk_vars_path "$disk")"
  fi

  # ── 从盘启动 = 不挂 ISO ──
  # 「挂着 ISO 又从盘启动」是最坏的组合：盘上引导不了时它会安静地回落到 ISO，
  # 你会在 Live 环境里以为装好的系统起来了。宁可给你一个明确的 no bootable device。
  if [[ "$boot" == c ]]; then
    [[ -n "$disk" ]] || die "--boot c 是「从盘启动」，得先有 --disk FILE"
    [[ -z "$iso" ]] || die "--boot c 不挂 ISO —— 它要验的是盘上的系统。
     去掉 ISO 参数，或改用 --boot d（装系统时用这个）。"
    [[ $want_fresh -eq 0 ]] || die "--boot c 靠的就是 NVRAM 里的引导项，不能再加 --fresh-vars"
    want_keep=1
  fi

  # ── ISO ──
  if [[ -n "$iso" ]]; then
    [[ -f "$iso" || -f "${OUT_DIR}/${iso}" ]] || die "ISO 不存在：$iso"
    [[ -f "$iso" ]] || iso="${OUT_DIR}/${iso}"
  elif [[ "$boot" == d ]]; then
    iso="$(latest_iso)" || die "${OUT_DIR} 里没有 .iso。先跑： ${MIPL_CMD} build"
  fi

  detect_ovmf || exit 1
  ensure_out_dir

  # ── 变量文件（NVRAM）──
  # 有盘：默认**保留** —— 装完重启进新系统，靠的是安装器写进 NVRAM 的那个引导项。
  # 没盘：保持老行为，每次刷新（反复引导同一个 ISO 时，旧引导项只会添乱）。
  local vars_how="refresh"
  if [[ -n "$disk"      ]]; then vars_how="keep";    fi
  if [[ $want_fresh -eq 1 ]]; then vars_how="refresh"; fi
  if [[ $want_keep  -eq 1 ]]; then vars_how="keep";    fi
  ensure_vars "$vars_file" "$vars_how"

  if [[ -n "$iso" ]]; then
    info "引导 ISO： $(basename "$iso")  ($(file_size "$iso"))"
  fi
  if [[ -n "$disk" ]]; then
    info "目标盘：   $(basename "$disk")  ($(file_size "$disk") 占用，虚拟 $(disk_virtual_size "$disk")，${disk_fmt})"
    note "           客机里是 /dev/vda（virtio）—— 分区前先 lsblk 确认"
  fi

  # 参数逐条放进数组：file= 永远和它所属的 -drive 在同一个元素里，
  # 换行/缩进都不可能把它们拆开 —— Issue #8 就是这么来的。
  local -a q=(
    qemu-system-x86_64
    -name "MipLinux 测试"
    -m "$MEM_MB"
    -smp "$SMP"
  )
  if [[ -w /dev/kvm ]]; then
    q+=(-enable-kvm)
  else
    warn "没有可用的 /dev/kvm，去掉 -enable-kvm（会慢很多）"
  fi
  q+=(
    -drive "if=pflash,format=raw,readonly=on,file=${OVMF_CODE}"
    -drive "if=pflash,format=raw,file=${vars_file}"
  )
  if [[ -n "$disk" ]]; then
    q+=(-drive "file=${disk},if=virtio,format=${disk_fmt}")
  fi
  if [[ -n "$iso" ]]; then
    q+=(-cdrom "$iso")
  fi
  q+=(
    -boot "order=${boot}"
    -netdev user,id=n0
    -device virtio-net,netdev=n0
  )

  # 临时加参数（按空格切分，不支持引号）：MIPL_QEMU_EXTRA="-display none -S"
  if [[ -n "${MIPL_QEMU_EXTRA:-}" ]]; then
    local -a extra=()
    read -r -a extra <<< "$MIPL_QEMU_EXTRA"
    q+=("${extra[@]}")
    note "附加参数： ${MIPL_QEMU_EXTRA}"
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    run "${q[@]}"
    return 0
  fi

  # 现在是以 root 跑的，而图形会话属于调用 sudo 的那个用户。sudo 默认会保留
  # DISPLAY 与 XAUTHORITY（所以 XWayland 那条路通常能开窗），但会清掉
  # WAYLAND_DISPLAY 和 XDG_RUNTIME_DIR。两者都没有时先说一句，别让人对着
  # 一个「什么都没发生」的终端发呆。
  if [[ -n "${SUDO_USER:-}" && -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    warn "没有检测到图形会话环境（DISPLAY / WAYLAND_DISPLAY 都是空的）"
    note "QEMU 可能开不出窗口。三个办法，任选一个："
    note "  1) 显式把会话变量递给 sudo："
    note "     sudo DISPLAY=\$DISPLAY XAUTHORITY=\$XAUTHORITY $0 qemu"
    note "  2) 用无头方式验证，见 docs/work/tech/02-构建与QEMU测试.md 的 C.3"
    note "  3) 只想确认参数对不对： sudo $0 -n qemu"
  fi

  echo
  if [[ "$boot" == c ]]; then
    note "预期结果：进入盘上装好的系统（不是 Live 环境）"
    note "盘上若没有可引导的 ESP 项，UEFI 会给你 no bootable device / UEFI shell ——"
    note "那说明安装器没把引导写上，不是这次启动的问题（NVRAM 我们特意保留了）。"
  elif [[ -n "$disk" ]]; then
    note "预期结果：出现 [root@archiso ~]# 提示符（Live 环境；releng 没有桌面环境）"
    note "系统就装在挂的那块盘上：Live 里 lsblk 应该看到 vda"
  else
    note "预期结果：出现 [root@archiso ~]# 提示符（releng 没有桌面环境，这是成功）"
  fi
  note "退出 QEMU：窗口里 Ctrl+A 然后 X，或直接关窗口"
  echo
  run "${q[@]}"
}

# ── 命令：target ──────────────────────────────────────────────────────
# 建一块空的目标盘给线 B 装系统用。它本身只做一件事：qemu-img create ——
# 但要把「下一步敲什么」和「它的 NVRAM 在哪」一起说清楚，否则挂载那一步
# 只能靠人回忆，而回忆出来的命令迟早会漏掉 --disk c 这类关键参数。
cmd_target() {
  local name="$TARGET_DISK_NAME" size="$TARGET_DISK_SIZE" force=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --name)
        [[ -n "${2:-}" ]] || die "--name 后面要跟文件名"
        name="$2"; shift 2 ;;
      --size)
        [[ -n "${2:-}" ]] || die "--size 后面要跟大小，例如 40G"
        size="$2"; shift 2 ;;
      --force) force=1; shift ;;
      -*) die "未知选项：$1（用 --help 看用法）" ;;
      *)  die "target 不接受位置参数：$1（文件名用 --name）" ;;
    esac
  done

  have qemu-img || die "找不到 qemu-img。装它：
     Arch / CachyOS   sudo pacman -S qemu-img
     Fedora           sudo dnf install qemu-img"
  ensure_out_dir

  # 裸文件名按 out/ 解析，和 qemu 的 ISO 参数同一套约定。
  local path="$name"
  [[ "$path" == */* ]] || path="${OUT_DIR}/${path}"
  local vars; vars="$(disk_vars_path "$path")"

  if [[ -e "$path" ]]; then
    if [[ $force -eq 0 ]]; then
      die "目标盘已存在：${path}
     它上面可能已经装着一个系统 —— 所以默认不覆盖。
       看看它：   qemu-img info '${path}'
       直接用：   ${MIPL_CMD} qemu --disk $(basename -- "$path")
       重新造：   ${MIPL_CMD} target --force   （盘和它的 NVRAM 一起换新）"
    fi
    warn "--force：覆盖已有的盘，并丢弃它的 NVRAM（$(basename -- "$vars")）"
    run rm -f -- "$path" "$vars"
  fi

  info "建目标盘：$(basename -- "$path")  虚拟大小 ${size}"
  run qemu-img create -f qcow2 -- "$path" "$size"

  if [[ $DRY_RUN -eq 1 ]]; then
    return 0
  fi
  [[ -f "$path" ]] || die "qemu-img 没有产出 ${path}，看上面的报错"

  ok "已创建 ${path}（占用 $(file_size "$path")，虚拟 $(disk_virtual_size "$path")）"
  note "它的 NVRAM 会存在 ${vars}（首次挂载时自动生成，之后一直保留）"
  echo
  info "下一步："
  note "  1) 装系统（ISO 优先启动，同时挂上这块盘）："
  note "       ${MIPL_CMD} qemu --disk $(basename -- "$path")"
  note "  2) 装完重启进新系统（不挂 ISO、保留 NVRAM）："
  note "       ${MIPL_CMD} qemu --disk $(basename -- "$path") --boot c"
  note "  在 Live 里它应该是 /dev/vda —— 动手分区之前先 lsblk 确认。"
}

# ── 命令：shell / stop ────────────────────────────────────────────────
cmd_shell() {
  local restart=0
  [[ "${1:-}" == "--restart" ]] && restart=1

  ensure_out_dir

  # 机器名被占用这件事要单独判：容器可能在文件系统里存在、但正跑着，
  # 那种情况下 nspawn 会拒绝启动（Issue #4）。
  local running=0
  if machine_running; then running=1; fi
  if [[ $running -eq 0 ]] && ! container_exists; then
    die "构建容器不存在：${CONTAINER_DIR}
     先创建： ${MIPL_CMD} build"
  fi

  if [[ $running -eq 1 ]]; then
    warn "机器名 '${MACHINE_NAME}' 已被一个仍在运行的容器占用（Issue #4）"
    note "容器不会因为关闭终端而停止，它由 systemd 作为 ${MACHINE_NAME}.scope 管理"
    if [[ $restart -eq 1 ]]; then
      info "先关掉它，再重新进入"
      cmd_stop
    else
      die "两种做法：
       ${MIPL_CMD} stop            # 只关闭旧容器
       ${MIPL_CMD} shell --restart # 关闭并立刻重新进入"
    fi
  fi

  info "进入容器 ${CONTAINER_DIR}"
  note "宿主机 ${OUT_DIR}  →  容器内 /out"

  # 和 mipl build 挂在同一个位置：容器里永远能在 /profile 看到仓库的 profile，
  # 于是「进容器 diff 一下」（A1 的验收）和「构建」看到的是同一份东西。
  # 只读，理由同 build：profile 的改动只能从宿主机走 git。
  local -a bind_args=(--bind "${OUT_DIR}:/out")
  local shell_profile="${REPO_PROFILE}"
  [[ "$shell_profile" == /* ]] || shell_profile="${REPO_ROOT}/${shell_profile}"
  if [[ -f "${shell_profile}/profiledef.sh" ]]; then
    run mkdir -p "${CONTAINER_DIR}${PROFILE_INNER}"   # 挂载点先备好（老版本 systemd 不自动建）
    bind_args+=(
      --bind-ro "${shell_profile}:${PROFILE_INNER}"
      --setenv "MIPL_PROFILE=${PROFILE_INNER}"
    )
    note "宿主机 ${shell_profile}  →  容器内 ${PROFILE_INNER}（只读）"
    note "对照的原版 releng 在容器内 ${BASELINE_PROFILE}"
  else
    warn "仓库里没有 ${shell_profile}/profiledef.sh —— 这次不挂 ${PROFILE_INNER}"
  fi

  note "用完请在容器内执行 poweroff，别直接关窗口"
  echo
  run_root systemd-nspawn --directory="${CONTAINER_DIR}" \
    -u root --machine="${MACHINE_NAME}" \
    "${bind_args[@]}"
}

cmd_stop() {
  local force=0
  [[ "${1:-}" == "--force" ]] && force=1
  have machinectl || die "找不到 machinectl"

  if ! machine_running; then
    ok "没有正在运行的容器，无需处理"
    return 0
  fi

  if [[ $force -eq 1 ]]; then
    info "terminate ${MACHINE_NAME}（强杀，不给清理时间）"
    run_root machinectl terminate "$MACHINE_NAME"
  else
    info "poweroff ${MACHINE_NAME}（走正常关机流程）"
    run_root machinectl poweroff "$MACHINE_NAME"
  fi

  [[ $DRY_RUN -eq 1 ]] && return 0
  local i
  for i in $(seq 1 15); do
    machine_running || { ok "容器已停止"; return 0; }
    sleep 1
  done
  warn "等了 15 秒还在运行，试试： sudo machinectl terminate ${MACHINE_NAME}"
}

# ── 命令：build ───────────────────────────────────────────────────────
# 默认用仓库里的 profile/ 构建，--baseline 改用容器内原版 releng。
# profile 只在宿主机上定一次、在宿主机上先校验，然后只读挂进容器 —— 见
# baseline-build.sh 顶部关于「为什么 profile 要挂进容器」的说明。
cmd_build() {
  local -a passthrough=(--auto)
  local baseline=0 profile_given=0 profile="$REPO_PROFILE"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --work)
        [[ -n "${2:-}" ]] || die "--work 后面要跟目录"
        INNER_WORK_DIR="$2"; passthrough+=(--work "$2"); shift 2 ;;
      --baseline)
        baseline=1; passthrough+=(--baseline); shift ;;
      --profile)
        [[ -n "${2:-}" ]] || die "--profile 后面要跟 profile 目录"
        profile="$2"; profile_given=1; shift 2 ;;
      --keep-work)
        # 默认构建前会清工作目录（坑 1）。这个开关只给调试 mkarchiso 的
        # _run_once 行为用 —— 清理本身在 baseline-build.sh 里做。
        passthrough+=(--keep-work); shift ;;
      --auto)
        shift ;;                       # 默认就是一条龙；交互式请用 mipl shell
      --) shift; passthrough+=("$@"); break ;;
      -*) die "未知选项：$1（用 --help 看用法）" ;;
      *)  die "未知参数：$1（用 --help 看用法）" ;;
    esac
  done

  [[ $baseline -eq 1 && $profile_given -eq 1 ]] \
    && die "--baseline 与 --profile 只能选一个"

  local script="${SCRIPT_DIR}/baseline-build.sh"
  [[ -x "$script" ]] || die "找不到可执行的 ${script}"

  ensure_out_dir

  if [[ $baseline -eq 1 ]]; then
    info "构建 profile： 容器内原版 releng（${BASELINE_PROFILE}）"
    note "  基线：用它分开「环境坏了」和「自己改坏了」"
  else
    # 相对路径按仓库根解析 —— 这条命令在仓库外敲也一样能用。
    [[ "$profile" == /* ]] || profile="${REPO_ROOT}/${profile}"
    profile="$(realpath -m -- "$profile")"
    [[ -f "${profile}/profiledef.sh" ]] || die "profile 目录里没有 profiledef.sh：${profile}
      （要用容器内原版 releng 构建，加 --baseline）"
    passthrough+=(--profile "$profile")
    info "构建 profile： ${profile}"
    if [[ "${MIPL_PROFILE_RW:-0}" == 1 ]]; then
      note "  容器内固定挂在 ${PROFILE_INNER}，可写挂载（MIPL_PROFILE_RW=1）"
    else
      note "  容器内固定挂在 ${PROFILE_INNER}，只读挂载；需要可写时设 MIPL_PROFILE_RW=1"
    fi
  fi

  info "构建工作目录（容器内）： ${INNER_WORK_DIR}"
  note "  **不要放在 /tmp**：容器里它是 nspawn 挂的内存盘（10% 内存），必然 ENOSPC"
  note "  构建前会自动清空它（坑 1：_run_once 标记会让改动静默失效）；"
  note "  要故意保留上一次的目录： --keep-work"

  # baseline-build.sh 已经处理了「下载 bootstrap → 解压 → 进容器构建」的完整流程。
  # 这里只负责把配置传进去，不重复实现。用 env 显式赋值而不是靠环境继承：
  # 如果用户是用 `sudo MIPL_WORK_DIR=… mipl build` 调用的，sudo 会保留；但直接
  # 在普通 shell 里 export 的变量，sudo 默认会清掉 —— 显式传一次最稳。
  # MIPL_OUT_DIR / MIPL_CONTAINER 也要传：否则子脚本按自己的默认值算，
  # 产物目录和挂载点会和上面提示里说的不是同一个。
  local -a env_args=(
    "MIPL_WORK_DIR=${INNER_WORK_DIR}"
    "MIPL_OUT_DIR=${OUT_DIR}"
    "MIPL_CONTAINER=${CONTAINER_DIR}"
    "MIPL_MACHINE=${MACHINE_NAME}"
    # bootstrap 的路径也要传：doctor / clean --bootstrap 说的是这个路径，
    # 子脚本要是按自己的默认值算，就可能出现「这边说缓存是好的、那边在下另一份」。
    "MIPL_BOOTSTRAP_FILE=${BOOTSTRAP_FILE}"
    "MIPL_CHECKSUMS_FILE=${BOOTSTRAP_CHECKSUMS_FILE}"
  )
  # 换镜像时把地址一起带过去，子脚本自己推 sha256sums.txt 的位置。
  [[ -n "${MIPL_BOOTSTRAP_URL:-}" ]] && env_args+=("MIPL_BOOTSTRAP_URL=${MIPL_BOOTSTRAP_URL}")
  # 容器里的源与 DNS 同理：doctor 报的是这两个值，构建时就得用同两个值，
  # 否则会出现「doctor 说源没问题、构建里却在用另一个源」。
  env_args+=("MIPL_MIRROR_URL=${MIRROR_URL}")
  [[ -n "${MIPL_DNS:-}" ]] && env_args+=("MIPL_DNS=${MIPL_DNS}")
  [[ -n "${MIPL_MIRRORLIST:-}" ]] && env_args+=("MIPL_MIRRORLIST=${MIPL_MIRRORLIST}")
  # 试运行要一路传到底：否则 -n 只打印到这一步，容器里真正要跑的那条
  # mkarchiso 命令（以及 profile 挂在哪）就看不见了。
  [[ $DRY_RUN -eq 1 ]] && env_args+=("MIPL_DRY_RUN=1")
  # 同上：显式传，别依赖 sudo 保留环境变量。
  [[ -n "${MIPL_PROFILE_RW:-}" ]] && env_args+=("MIPL_PROFILE_RW=${MIPL_PROFILE_RW}")

  run_root env "${env_args[@]}" "$script" "${passthrough[@]}"
}

# ── 命令：iso ─────────────────────────────────────────────────────────
cmd_iso() {
  ensure_out_dir
  local -a isos=()
  shopt -s nullglob
  isos=("${OUT_DIR}"/*.iso)
  shopt -u nullglob
  if [[ ${#isos[@]} -eq 0 ]]; then
    info "${OUT_DIR} 里还没有 ISO"
    note "先构建： ${MIPL_CMD} build"
    return 0
  fi
  info "ISO 产物（按时间新→旧）："
  local f
  while IFS= read -r f; do
    printf '  %s  %-52s %s\n' "$(date -r "$f" '+%m-%d %H:%M')" "$(basename "$f")" "$(file_size "$f")"
  done < <(ls -1t "${isos[@]}")
  echo
  note "启动最新的： ${MIPL_CMD} qemu"
}

# ── 命令：deps ────────────────────────────────────────────────────────
cmd_deps() {
  local install=0
  [[ "${1:-}" == "--install" ]] && install=1

  local -a pkgs=()
  case "$(distro_family)" in
    arch)   pkgs=(edk2-ovmf qemu-desktop) ;;
    fedora) pkgs=(edk2-ovmf qemu-kvm systemd-container) ;;
    debian) pkgs=(ovmf qemu-system-x86 systemd-container) ;;
    *)      pkgs=() ;;
  esac

  echo "宿主机需要的包（构建容器里那套不算）："
  echo
  case "$(distro_family)" in
    arch)   echo "  sudo pacman -S --needed ${pkgs[*]}" ;;
    fedora) echo "  sudo dnf install ${pkgs[*]}" ;;
    debian) echo "  sudo apt install ${pkgs[*]}" ;;
    *)      echo "  Arch / CachyOS   sudo pacman -S --needed edk2-ovmf qemu-desktop"
            echo "  Fedora           sudo dnf install edk2-ovmf qemu-kvm systemd-container"
            echo "  Debian / Ubuntu  sudo apt install ovmf qemu-system-x86 systemd-container" ;;
  esac
  echo
  note "不需要在宿主机安装 archiso —— 构建在容器里做，qemu 命令由本脚本自己生成"
  echo

  local -a missing=()
  have systemd-nspawn       || missing+=(systemd-nspawn)
  have machinectl           || missing+=(machinectl)
  have qemu-system-x86_64   || missing+=(qemu-system-x86_64)
  if [[ ${#missing[@]} -eq 0 ]]; then
    ok "该有的都有了"
    return 0
  fi
  warn "当前还缺：${missing[*]}"

  if [[ $install -eq 1 && ${#pkgs[@]} -gt 0 ]]; then
    echo
    case "$(distro_family)" in
      arch)   run_root pacman -S --needed --noconfirm "${pkgs[@]}" ;;
      fedora) run_root dnf install -y "${pkgs[@]}" ;;
      debian) run_root apt install -y "${pkgs[@]}" ;;
    esac
  else
    note "加上 --install 让脚本直接执行上面那条命令"
  fi
}

# ── 命令：clean ───────────────────────────────────────────────────────
# 删不可逆的东西之前问一句。管道/脚本里（非 tty）直接放行 ——
# 否则自动化会被一个等不到输入的提示卡死。
confirm_delete() {
  local ans=""
  [[ $DRY_RUN -eq 0 && -t 0 ]] || return 0
  printf '输入 yes 确认删除：'
  read -r ans || ans=""
  if [[ "$ans" != "yes" ]]; then
    note "已取消，什么都没删"
    return 1
  fi
  return 0
}

cmd_clean() {
  local with_iso=0 with_disk=0 with_bootstrap=0 disk_name="$TARGET_DISK_NAME"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --iso)  with_iso=1; shift ;;
      --bootstrap)
        # 缓存的 bootstrap 是「下载 → 解压」这条链的上游。它一旦是坏的
        # （截断 / 下到一半 / 镜像换了版本），解压出来的容器就是残缺的，
        # 而残缺容器要到进 nspawn 才现形 —— 见 Issue #32。
        # 所以除了让构建脚本自己认出坏文件，也给一条「我自己来清」的路。
        with_bootstrap=1; shift ;;
      --disk)
        # 盘名可选：mipl target --name 造出来的盘也能在这里删掉
        with_disk=1
        if [[ -n "${2:-}" && "$2" != -* ]]; then disk_name="$2"; shift 2; else shift; fi ;;
      -*) die "未知选项：$1（用 --help 看用法）" ;;
      *)  die "clean 不接受位置参数：$1（盘名跟在 --disk 后面）" ;;
    esac
  done

  local -a vars=()
  shopt -s nullglob
  vars=("${OUT_DIR}"/OVMF_VARS*.fd)
  shopt -u nullglob

  if [[ ${#vars[@]} -gt 0 ]]; then
    info "删除 OVMF 变量文件（下次 qemu 会重新复制）："
    printf '  %s\n' "${vars[@]##*/}"
    run rm -f "${vars[@]}"
  else
    note "没有需要删除的 OVMF 变量文件"
  fi

  if [[ $with_iso -eq 1 ]]; then
    local -a isos=()
    shopt -s nullglob
    isos=("${OUT_DIR}"/*.iso)
    shopt -u nullglob
    if [[ ${#isos[@]} -gt 0 ]]; then
      warn "即将删除 ${#isos[@]} 个 ISO（重新构建要几分钟到几十分钟）"
      printf '  %s\n' "${isos[@]##*/}"
      if confirm_delete; then run rm -f "${isos[@]}"; fi
    else
      note "没有 ISO 可删"
    fi
  else
    note "ISO 不动。真要删： ${MIPL_CMD} clean --iso"
  fi

  # 目标盘：**绝不默认删**。它上面可能装着一个系统，重建要跑一整遍安装。
  # 它不在上面那个 OVMF_VARS*.fd glob 里，所以「清变量」不会误伤装好的系统。
  if [[ $with_disk -eq 1 ]]; then
    local disk="$disk_name" dvar
    [[ "$disk" == */* ]] || disk="${OUT_DIR}/${disk}"
    dvar="$(disk_vars_path "$disk")"
    if [[ -e "$disk" || -e "$dvar" ]]; then
      warn "即将删除目标盘及其 NVRAM（盘上的系统会一起没）："
      if [[ -e "$disk" ]]; then printf '  %s\n' "${disk##*/}"; fi
      if [[ -e "$dvar" ]]; then printf '  %s\n' "${dvar##*/}"; fi
      if confirm_delete; then run rm -f -- "$disk" "$dvar"; fi
    else
      note "没有目标盘可删：${disk}"
    fi
  else
    note "目标盘不动（它上面可能是装好的系统）。真要删： ${MIPL_CMD} clean --disk"
  fi

  # bootstrap 缓存：只有明确要删才删。默认不碰 —— 它是 126 MB 的下载，
  # 留着能让下次构建少等一次下载；而且「坏缓存」本来就会在构建时被校验认出来。
  if [[ $with_bootstrap -eq 1 ]]; then
    local -a boot_files=("$BOOTSTRAP_FILE" "$BOOTSTRAP_CHECKSUMS_FILE")
    local -a present=()
    local f
    for f in "${boot_files[@]}"; do
      [[ -e "$f" ]] && present+=("$f")
    done
    if [[ ${#present[@]} -eq 0 ]]; then
      note "没有 bootstrap 缓存可删：${BOOTSTRAP_FILE}"
    else
      info "即将删除 bootstrap 缓存（下次构建要重新下载约 126 MB）："
      local sz=""
      for f in "${present[@]}"; do
        sz=""
        [[ -f "$f" ]] && sz="  ($(file_size "$f"))"
        printf '  %s%s\n' "$f" "$sz"
      done
      if confirm_delete; then run rm -f -- "${present[@]}"; fi
    fi
  else
    note "bootstrap 缓存不动。构建时它会自己校验，坏了会重下；"
    note "要现在清掉： ${MIPL_CMD} clean --bootstrap（缓存：${BOOTSTRAP_FILE}）"
  fi
}

# ── 命令：help ────────────────────────────────────────────────────────
cmd_help() {
  cat <<EOF
mipl ${MIPL_VERSION} · MipLinux 项目操作台

用法： sudo ./scripts/mipl.sh <命令> [参数]
       sudo ./scripts/mipl.fish <命令> [参数]     # fish 用户的同一入口

权限： 整个脚本一律要求 root，普通用户运行会被直接拒绝（连 --help 也是）。
       它不会自己 sudo —— 隐式提权会让「谁在改我的 out/」变得说不清。
       环境变量写在 sudo 后面，例如：
         sudo MIPL_MEM=8192 ./scripts/mipl.sh qemu

命令：
  doctor [--report]   环境自检。换机器、换人接手时先跑这个；
                      --report 输出一段可粘进文档的 Markdown 表格。
  qemu [ISO] [--disk FILE] [--boot d|c] [--fresh-vars] [--keep-vars]
                      启动 QEMU。不给 ISO 就用 out/ 里最新的那个。
      --disk FILE     挂一块目标盘（裸文件名按 out/ 解析）。**这块盘的 NVRAM
                      存在 out/<盘名>.vars.fd**：首次挂载自动生成，之后一直保留
                      —— ISO 测试用的 out/OVMF_VARS.fd 永远不会碰它。装完系统
                      能重启进新系统，靠的就是它的 NVRAM 没被刷掉。
      --boot d        光驱优先（默认）。**装系统用这个**。
      --boot c        从盘启动：不挂 ISO、保留 NVRAM。**装完重启用这个**。
                      盘上没有 ESP 引导项时你会看到 no bootable device ——
                      那是诚实的失败，不会安静地回落到 Live 环境骗过你。
      --fresh-vars    重置变量文件（NVRAM 清空，从头来一遍）。
      --keep-vars     不重置（ISO 测试时想复现「上次的引导项」才用）。
  target [--name F] [--size 40G] [--force]
                      建一块空的目标盘（默认 out/target.qcow2）给安装器用。
                      已存在就拒绝：它上面可能装着一个系统。
                      --force 覆盖，并连同它的 NVRAM 一起换新。
  vars                只复制 OVMF 变量文件（out/OVMF_VARS.fd），不启动 QEMU。
  shell [--restart]   进入 nspawn 构建容器（自动挂好 /out 与只读的 /profile）。
                      旧容器还开着时会拦住你，--restart 会先关掉它。
  stop [--force]      关闭构建容器（poweroff；--force 用 terminate）。
  build [选项]        跑 baseline-build.sh：下载 bootstrap → 解压 → 构建 ISO。
                      默认用仓库里的 profile/（只读挂进容器的 /profile）。
                      进容器时会把「干净的镜像列表」和「可用的 resolv.conf」
                      只读挂进去 —— 容器自带的那两份都不能用（前者可能只剩
                      Include 转发，后者是纯注释），pacman 会静默失败。
      --baseline      改用容器内原版 releng 构建，即「基线」：
                      构建挂了时跑一次它，就能分开「环境坏了」和「自己改坏了」。
      --profile DIR   改用指定的 profile 目录（宿主机路径，相对仓库根解析）。
      --work DIR      容器内的工作目录，默认 /var/tmp/mipl-work。
                      **别放 /tmp**：容器里它是 nspawn 挂的内存盘（10% 内存），
                      会在写 efiboot.img 时以 ENOSPC 失败。构建前会自动清空它
                      —— 见 --keep-work。
      --keep-work     保留工作目录，构建前不清理。只在调试 mkarchiso 的
                      _run_once 行为时用：正常构建必须清，否则它会跳过装包、
                      拷 airootfs、生成 ISO，交给你一个「构建成功」的旧产物。
  iso                 列出 out/ 里的 ISO。
  deps [--install]    打印（或执行）本机需要装的包。
  clean [--iso] [--disk [FILE]] [--bootstrap]
                      删除 OVMF 变量文件；--iso 连 ISO 一起删；
                      --disk 删目标盘及其 NVRAM（默认 out/target.qcow2）；
                      --bootstrap 删 bootstrap 缓存（下载的 126 MB 那个）
                      后两个不可逆，会先问一句。

全局选项：
  -n, --dry-run       只打印将要执行的命令，不做任何改动。
  -h, --help          显示本帮助。
      --version       显示版本。

环境变量（都可覆盖默认值）：
  MIPL_ROOT       仓库根目录      默认：脚本所在目录的上一级
  MIPL_OUT_DIR    产物目录        默认：\$MIPL_ROOT/out
  MIPL_CONTAINER  容器目录        默认：/var/lib/machines/archbuild
  MIPL_MACHINE    容器机器名      默认：archbuild
  MIPL_MEM        QEMU 内存(MB)   默认：4096
  MIPL_SMP        QEMU vCPU 数    默认：4（Live 引导 1 个也够，装机时多点省时间）
  MIPL_DISK_NAME  目标盘文件名    默认：target.qcow2（mipl target 用，落在 out/）
  MIPL_DISK_SIZE  目标盘虚拟大小  默认：40G（qcow2 稀疏文件，占用随写入增长）
  MIPL_WORK_DIR   容器内工作目录  默认：/var/tmp/mipl-work（别用 /tmp：内存盘）
  MIPL_PROFILE    宿主机 profile  默认：\$MIPL_ROOT/profile（build 与 shell 都用它）
  MIPL_PROFILE_RW 设 1 则 profile 可写挂载（默认只读；只在排查构建失败时用）
  MIPL_OVMF_DIR   只在这个目录里找固件（不做兜底扫描，便于复现问题）
  MIPL_OVMF_CODE  显式指定固件本体
  MIPL_OVMF_VARS  显式指定变量文件
  MIPL_BOOTSTRAP_FILE   bootstrap 缓存路径  默认：/tmp/archlinux-bootstrap-x86_64.tar.zst
  MIPL_BOOTSTRAP_URL    bootstrap 下载地址  默认：清华镜像；构建时可换镜像
  MIPL_CHECKSUMS_FILE   校验和清单缓存      默认：<bootstrap>.sha256sums.txt
  MIPL_MIRROR_URL  容器内 pacman 的源   默认：清华 https://…/archlinux/\$repo/os/\$arch
                   构建时生成一份干净的 mirrorlist 只读挂进容器（容器自带的那份
                   可能只剩 Include 转发，pacman 会 failed to synchronize）
  MIPL_DNS         容器内 /etc/resolv.conf 的 nameserver，空格或逗号分隔
                   默认：抄宿主机 /etc/resolv.conf；抄不到时用内置兜底
                   （bootstrap 自带的 resolv.conf 是纯注释，DNS 全废）
  MIPL_QEMU_EXTRA 追加给 qemu 的参数（按空格切分），如 "-display none"
  NO_COLOR        设了就不输出颜色

为什么要有这个脚本：
  手抄长命令必然出错，而且错误出现在最不该花时间的地方。
  仓库的 Issues 里已经记了三个：固件路径各发行版不同（#8）、
  文档写死了某台机器的家目录（#7）、容器没关就重进（#4）。
  这些坑现在都固化成了脚本的默认行为。

文档： docs/work/tech/02-构建与QEMU测试.md
EOF
}

# ── 主流程 ────────────────────────────────────────────────────────────
main() {
  # 权限检查放在最前面：连 --help 也要拦。
  # 「这条命令会以什么身份跑」不该因为参数不同而不同。
  require_root "$@"

  # 先把 --dry-run 从任何位置摘出来：`mipl -n qemu` 和 `mipl qemu -n` 都接受，
  # 因为手最容易两种都打，而其中一种静默失效是最讨厌的失败方式。
  local -a args=()
  local a
  for a in "$@"; do
    if [[ "$a" == "-n" || "$a" == "--dry-run" ]]; then
      DRY_RUN=1
    else
      args+=("$a")
    fi
  done
  set -- ${args[@]+"${args[@]}"}

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)    cmd_help; return 0 ;;
      --version)    echo "mipl ${MIPL_VERSION}"; return 0 ;;
      --)           shift; break ;;
      -*)           die "未知选项：$1（用 --help 看用法）" ;;
      *)            break ;;
    esac
  done

  local cmd="${1:-help}"
  [[ $# -gt 0 ]] && shift

  case "$cmd" in
    doctor)  cmd_doctor "$@" ;;
    vars)    cmd_vars "$@" ;;
    qemu)    cmd_qemu "$@" ;;
    target)  cmd_target "$@" ;;
    shell)   cmd_shell "$@" ;;
    stop)    cmd_stop "$@" ;;
    build)   cmd_build "$@" ;;
    iso|ls)  cmd_iso "$@" ;;
    deps)    cmd_deps "$@" ;;
    clean)   cmd_clean "$@" ;;
    help)    cmd_help ;;
    *)       die "未知命令：$cmd（用 --help 看用法）" ;;
  esac
}

main "$@"
