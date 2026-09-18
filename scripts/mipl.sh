#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# mipl · MipLinux 项目操作台
#
# 把「每次都要手抄的长命令」变成一条不会抄错的命令。
#
#   sudo ./scripts/mipl.sh doctor        环境自检（换机器第一件事）
#   sudo ./scripts/mipl.sh qemu          刷新 OVMF 变量 + 启动 QEMU
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

MIPL_VERSION="0.2.0"

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
# 容器内 mkarchiso 的工作目录。Issue #6：/tmp 空间不足会导致构建失败。
INNER_WORK_DIR="${MIPL_WORK_DIR:-/tmp/work}"
# 目标文件用固定名。源文件名各发行版不同（OVMF_VARS.4m.fd / OVMF_VARS_4M.fd），
# 固定名意味着 QEMU 参数永远不需要跟着变——Issue #8 的第二个错误就出在这里。
VARS_DST="${OUT_DIR}/OVMF_VARS.fd"

# 提示信息里怎么称呼自己：在仓库根目录下写相对路径（好复制），在别处写绝对
# 路径（照样能跑）。脚本自己不依赖 cwd，那它给出的下一步命令也不该依赖。
# 一律带 sudo —— 因为脚本本身就要求 root（见下面的权限检查）。
if [[ "$PWD" == "$REPO_ROOT" ]]; then
  MIPL_CMD="sudo ./scripts/mipl.sh"
else
  MIPL_CMD="sudo ${SCRIPT_DIR}/mipl.sh"
fi

DRY_RUN=0

# ── 输出 ──────────────────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'
  C_ERR=$'\033[1;31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_DIM=''; C_OFF=''
fi

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

container_exists() { path_exists "${CONTAINER_DIR}/etc/os-release"; }

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
    if machine_running; then
      _miss "container" "${CONTAINER_DIR}（正在运行！用完记得 ${MIPL_CMD} stop，见 Issue #4）"
    else
      _line "container" "${CONTAINER_DIR}（已初始化）"
    fi
    local t missing_tools=()
    for t in mkarchiso pacstrap mkinitcpio mksquashfs xorriso; do
      path_exists "${CONTAINER_DIR}/usr/bin/${t}" || missing_tools+=("$t")
    done
    if [[ ${#missing_tools[@]} -eq 0 ]]; then
      _line "toolchain" "mkarchiso / pacstrap / mkinitcpio / mksquashfs / xorriso 齐全"
    else
      _miss "toolchain" "缺：${missing_tools[*]}（进容器后 pacman -S archiso，见 Issue #5）"
    fi
  else
    _miss "container" "${CONTAINER_DIR}（尚未创建 —— 先跑 ${MIPL_CMD} build）"
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

# ── 命令：vars ────────────────────────────────────────────────────────
cmd_vars() {
  detect_ovmf || exit 1
  ensure_out_dir
  info "固件来源： $OVMF_VARS"
  note "        $OVMF_CODE"
  # 每次都重新复制：引导过的系统会把引导项写进 NVRAM，复用旧文件会让
  # 上一次的引导项影响这一次，表现为「上次能启动、这次不行」。
  run cp -f "$OVMF_VARS" "$VARS_DST"
  if [[ $DRY_RUN -eq 0 ]]; then
    ok "已刷新 ${VARS_DST}  ($(file_size "$VARS_DST"))"
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

  local iso="${1:-}"
  if [[ -z "$iso" ]]; then
    iso="$(latest_iso)" || die "${OUT_DIR} 里没有 .iso。先跑： ${MIPL_CMD} build"
  elif [[ ! -f "$iso" && -f "${OUT_DIR}/${iso}" ]]; then
    iso="${OUT_DIR}/${iso}"
  fi
  [[ -f "$iso" ]] || die "ISO 不存在：$iso"

  detect_ovmf || exit 1
  cmd_vars

  info "引导： $(basename "$iso")  ($(file_size "$iso"))"

  # 参数逐条放进数组：file= 永远和它所属的 -drive 在同一个元素里，
  # 换行/缩进都不可能把它们拆开 —— Issue #8 就是这么来的。
  local -a q=(
    qemu-system-x86_64
    -name "MipLinux 测试"
    -m "$MEM_MB"
  )
  if [[ -w /dev/kvm ]]; then
    q+=(-enable-kvm)
  else
    warn "没有可用的 /dev/kvm，去掉 -enable-kvm（会慢很多）"
  fi
  q+=(
    -drive "if=pflash,format=raw,readonly=on,file=${OVMF_CODE}"
    -drive "if=pflash,format=raw,file=${VARS_DST}"
    -cdrom "$iso"
    -boot order=d
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
  note "预期结果：出现 [root@archiso ~]# 提示符（releng 没有桌面环境，这是成功）"
  note "退出 QEMU：窗口里 Ctrl+A 然后 X，或直接关窗口"
  echo
  run "${q[@]}"
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
  note "用完请在容器内执行 poweroff，别直接关窗口"
  echo
  run_root systemd-nspawn --directory="${CONTAINER_DIR}" \
    -u root --machine="${MACHINE_NAME}" \
    --bind "${OUT_DIR}:/out"
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
cmd_build() {
  local -a passthrough=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --work)
        [[ -n "${2:-}" ]] || die "--work 后面要跟目录"
        INNER_WORK_DIR="$2"; shift 2 ;;
      --) shift; passthrough+=("$@"); break ;;
      *)  passthrough+=("$1"); shift ;;
    esac
  done

  local script="${SCRIPT_DIR}/baseline-build.sh"
  [[ -x "$script" ]] || die "找不到可执行的 ${script}"

  ensure_out_dir

  info "构建工作目录（容器内）： ${INNER_WORK_DIR}"
  note "  空间不够时换一个： ${MIPL_CMD} build --work /var/tmp/mipl-work（Issue #6）"

  # baseline-build.sh 已经处理了「下载 bootstrap → 解压 → 进容器构建」的完整流程。
  # 这里只负责把工作目录传进去，不重复实现。用 env 显式赋值而不是靠环境继承：
  # 如果用户是用 `sudo MIPL_WORK_DIR=… mipl build` 调用的，sudo 会保留；但直接
  # 在普通 shell 里 export 的变量，sudo 默认会清掉 —— 显式传一次最稳。
  run_root env "MIPL_WORK_DIR=${INNER_WORK_DIR}" "$script" "${passthrough[@]}"
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
cmd_clean() {
  local with_iso=0
  [[ "${1:-}" == "--iso" ]] && with_iso=1

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
      # 删 ISO 是不可逆的，交互时问一句；管道/脚本里（非 tty）直接执行，
      # 否则自动化会被一个等不到输入的提示卡死。
      if [[ $DRY_RUN -eq 0 && -t 0 ]]; then
        local ans=""
        printf '输入 yes 确认删除：'
        read -r ans || ans=""
        if [[ "$ans" != "yes" ]]; then
          note "已取消，什么都没删"
          return 0
        fi
      fi
      run rm -f "${isos[@]}"
    else
      note "没有 ISO 可删"
    fi
  else
    note "ISO 不动。真要删： ${MIPL_CMD} clean --iso"
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
  qemu [ISO]          刷新一份全新的 OVMF 变量文件并启动 QEMU。
                      不给 ISO 就用 out/ 里最新的那个。
  vars                只复制 OVMF 变量文件，不启动 QEMU。
  shell [--restart]   进入 nspawn 构建容器（自动 --bind）。
                      旧容器还开着时会拦住你，--restart 会先关掉它。
  stop [--force]      关闭构建容器（poweroff；--force 用 terminate）。
  build [--work DIR]  跑 baseline-build.sh：下载 bootstrap → 解压 → 构建 ISO。
                      DIR 是容器内的工作目录，默认 /tmp/work。
  iso                 列出 out/ 里的 ISO。
  deps [--install]    打印（或执行）本机需要装的包。
  clean [--iso]       删除 OVMF 变量文件；--iso 连 ISO 一起删。

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
  MIPL_WORK_DIR   容器内工作目录  默认：/tmp/work
  MIPL_OVMF_DIR   只在这个目录里找固件（不做兜底扫描，便于复现问题）
  MIPL_OVMF_CODE  显式指定固件本体
  MIPL_OVMF_VARS  显式指定变量文件
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
