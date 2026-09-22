#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# mipl-lib · mipl.sh 与 baseline-build.sh 共用的东西
#
# 这里只放「两个入口必须给出同一个答案」的东西。目前是两件：
#
#   1. 容器健康检查 —— Issue #32。
#      bootstrap tarball 的条目顺序决定了：`etc/os-release` 在第 630 条，
#      `usr/bin/bash` 在第 5815 条（共 33105 条）。所以「下载被截断 / tar 被
#      中断」的残缺解压，恰好会留下 etc/os-release —— 于是所有「文件在不在」
#      式的检查一路绿灯，直到 systemd-nspawn 抛出：
#          execv(/bin/bash, /bin/bash, /bin/sh) failed: No such file or directory
#      用户看到的是天书，而真正的信息是「容器里没有能执行的 shell」。
#      健康检查要能自己说出这句话。
#
#   2. 输出颜色约定 —— 两个脚本本来各写了一份一样的判断。
#
# 由调用方提供（source 之前设好）：
#   MIPL_LIB_DIR     本文件所在目录
#   MIPL_LIB_COLORS  设 1 才定义 C_* 颜色变量（默认不碰调用方的变量）
#
# 用法（两个入口都是这个形状，别写 $(dirname "$0")：
# 脚本可能是软链，只有 BASH_SOURCE 指向仓库里那份）：
#   MIPL_LIB_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   MIPL_LIB="${MIPL_LIB_DIR}/mipl-lib.sh"
#   [[ -r "$MIPL_LIB" ]] || { printf '[错误] 缺少 %s\n' "$MIPL_LIB" >&2; exit 1; }
#   MIPL_LIB_COLORS=1 . "$MIPL_LIB"
#
# 不设 set -euo pipefail：调用方已经设了，这里再设一遍只会掩盖调用方的选择。
# ─────────────────────────────────────────────────────────────────────

# ── 输出颜色 ──────────────────────────────────────────────────────────
# 非终端、或设了 NO_COLOR 就不上色。判断放在这里一次，两个入口就永远一致。
#
# 为什么是一个函数而不是一段 if：两个脚本都是「先解析参数、后定 DRY_RUN」，
# 而 --dry-run 要一路传到子脚本，所以颜色判断得排在参数解析之后。调用方
# 解析完参数再调一次（source 时已经自动调过一次）。
mipl_refresh_output_mode() {
  if [[ "${MIPL_LIB_COLORS:-0}" != 1 ]]; then
    return 0
  fi
  if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'
    C_ERR=$'\033[1;31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
  else
    C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_DIM=''; C_OFF=''
  fi
}
mipl_refresh_output_mode

# 共用输出与尺寸格式：两个入口是不同进程，函数不会自动继承。
info() { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s[ok]%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%s[错误]%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }
note() { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF"; }

fmt_size() {
  awk -v b="${1:-0}" 'BEGIN{
    split("B KB MB GB TB", a, " "); i = 1
    while (b >= 1024 && i < 5) { b /= 1024; i++ }
    if (i == 1) printf "%d %s\n", b, a[i]; else printf "%.1f %s\n", b, a[i]
  }'
}

file_size() { fmt_size "$(stat -c %s "$1" 2>/dev/null || echo 0)"; }

# ── 提示里怎么称呼这个入口 ────────────────────────────────────────────
# 在仓库根目录下写相对路径（好复制），在别处写绝对路径（照样能跑）。
# 一律带 sudo —— 两个脚本都要求 root，提示里给一条不带 sudo 的命令没有意义。
# 也放共用库里：baseline-build.sh 单独跑时（不带 mipl.sh）同样要说得出
# 「重建容器该敲哪条命令」。
#   调用方提供：MIPL_LIB（本文件的路径）或 MIPL_LIB_DIR（本文件所在目录），
#              给一个就够；两个都没给就按 BASH_SOURCE 自己算（. 调用时
#              BASH_SOURCE[0] 就是本文件，所以这一步总是成立的）
#   调用方覆盖：MIPL_ROOT（仓库根）、MIPL_CMD（整条命令的原样替换）
if [[ -z "${MIPL_LIB_DIR:-}" ]]; then
  if [[ -n "${MIPL_LIB:-}" ]]; then
    MIPL_LIB_DIR="${MIPL_LIB%/*}"
  else
    MIPL_LIB_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
fi
MIPL_LIB_ROOT="${MIPL_ROOT:-$(cd "${MIPL_LIB_DIR}/.." && pwd)}"
if [[ -z "${MIPL_CMD:-}" ]]; then
  if [[ "$PWD" == "$MIPL_LIB_ROOT" ]]; then
    MIPL_CMD="sudo ./scripts/mipl.sh"
  else
    MIPL_CMD="sudo ${MIPL_LIB_DIR}/mipl.sh"
  fi
fi

# ── bootstrap 缓存的完整性 ────────────────────────────────────────────
# 这几条是 Issue #32 的另一半：原来「文件在不在」就等于「下好了」，
# 于是被截断的下载会被当成缓存，解压出来的容器是残缺的，而所有检查都说 OK。
#
# 这里的判断标准要和处理逻辑（删掉重下）**完全一致** —— 所以放共用库，
# 让 doctor 说的和 build 做的出自同一段代码。

# 进程退出码约定：0 = 通过；非 0 = 不通过，且值本身说明是哪一种不通过。
# doctor 要靠这个值分辨「没清单，验不了」和「验了，没过」。
MIPL_CHK_MISSING=1    # 文件本身不在
MIPL_CHK_NO_LIST=2    # 本地没有 sha256sums.txt，无从对照
MIPL_CHK_UNLISTED=3   # 清单里没有这一项（镜像换了版本，或文件名不是那个）
MIPL_CHK_MISMATCH=4   # 哈希对不上 —— 截断或损坏
MIPL_CHK_NOSUM=5      # 本机没有 sha256sum

# mipl_checksum_ok <文件> <sha256sums.txt>
mipl_checksum_ok() {
  local file="$1" list="$2" want got
  [[ -f "$file" ]] || return $MIPL_CHK_MISSING
  [[ -f "$list" ]] || return $MIPL_CHK_NO_LIST
  command -v sha256sum >/dev/null 2>&1 || return $MIPL_CHK_NOSUM
  # -F 固定串匹配：文件名里的 . 和 + 都不该被当成正则。
  want="$(grep -F -- "$(basename -- "$file")" "$list" 2>/dev/null \
          | head -1 | awk '{print $1}')"
  [[ -n "$want" ]] || return $MIPL_CHK_UNLISTED
  got="$(sha256sum -- "$file" 2>/dev/null | awk '{print $1}')"
  [[ "$got" == "$want" ]] || return $MIPL_CHK_MISMATCH
  return 0
}

# zstd 自带的完整性校验：半截文件在这里就现形，不会拖到解压才报一句
# 看不懂的「unexpected end of file」。没有 zstd 就当这层查不了（交给解压报错）。
mipl_zstd_complete() {
  command -v zstd >/dev/null 2>&1 || return 0
  zstd -t -- "$1" >/dev/null 2>&1
}

# 把退出码翻译成一句人话。调用方负责加前缀（warn / note / 自选项）。
mipl_checksum_reason() {
  case "$1" in
    "$MIPL_CHK_MISSING")  printf '文件不在\n' ;;
    "$MIPL_CHK_NO_LIST")  printf '本地还没有 sha256sums.txt，无从对照\n' ;;
    "$MIPL_CHK_UNLISTED") printf '镜像的 sha256sums.txt 里没有这一项（镜像换版本了？）\n' ;;
    "$MIPL_CHK_MISMATCH") printf 'sha256 对不上（下载被截断或文件损坏）\n' ;;
    "$MIPL_CHK_NOSUM")    printf '本机没有 sha256sum\n' ;;
    *)                    printf '未知原因（rc=%s）\n' "$1" ;;
  esac
}

# mipl_bootstrap_cache_ok <bootstrap 文件> <校验和清单> [哈希变量名]
# 返回 0 = 缓存可用（哈希一致，且 zstd 层也完整）。给了变量名就把算出来的
# sha256 存进去，好让「校验通过」这行能把哈希原样打出来。
mipl_bootstrap_cache_ok() {
  local file="$1" list="$2" into="${3:-}" rc=0 want got
  mipl_checksum_ok "$file" "$list" || rc=$?
  if [[ $rc -ne 0 ]]; then
    MIPL_CHK_LAST=$rc
    return $rc
  fi
  if ! mipl_zstd_complete "$file"; then
    MIPL_CHK_LAST=$MIPL_CHK_MISMATCH
    return $MIPL_CHK_MISMATCH
  fi
  if [[ -n "$into" ]]; then
    got="$(sha256sum -- "$file" 2>/dev/null | awk '{print $1}')"
    printf -v "$into" '%s' "$got"
  fi
  MIPL_CHK_LAST=0
  return 0
}

# ── 容器健康检查 ──────────────────────────────────────────────────────
# 四个「没有就别谈构建」的东西。宁可多报也不要漏报：
# 漏报的代价是把 execv 天书丢给用户，误报的代价只是重建一次容器。
#
#   能执行的 shell   nspawn 不带命令时要靠它进去（/bin/sh 与 /usr/bin/sh
#                    是 Arch 下的同一个 symlink，两个都查是为了别的发行版
#                    根文件系统也能用）
#   动态链接器       有 bash 却没有 ld-linux 时，execve 一样报
#                    「No such file or directory」—— 报错长得和「没有 bash」
#                    一模一样，所以两个都得查
#   pacman           构建前要 pacman -S --needed archiso
MIPL_HEALTH_ITEMS=(
  "能执行的 shell|bin/sh|usr/bin/sh|bin/bash|usr/bin/bash"
  "动态链接器|usr/lib/ld-linux-x86-64.so.2"
  "pacman|usr/bin/pacman"
)

# mipl_shell_in <容器根> → 打印第一个「在」的 shell 路径。
# 只看在不在一列，**不 deref**：bootstrap 里 usr/bin/sh 是 → bash 的符号链接，
# 用 -L 或 test -e 把它当成不存在是错的（-e 会跟着链接走过去，那反而是对的；
# 这里用 in-列 的写法同时容下两种情况）。
mipl_shell_in() {
  local root="$1" p
  for p in bin/sh usr/bin/sh bin/bash usr/bin/bash; do
    if [[ -e "${root}/${p}" || -L "${root}/${p}" ]]; then
      printf '%s\n' "/${p}"
      return 0
    fi
  done
  return 1
}

# mipl_container_health <容器目录> [shell 变量名]
#
# 返回 0：容器看起来是完整的；非 0：残缺，缺什么没有兜底，别拿它去 nspawn。
# 给了变量名就把「标签|容器内路径」逐条存进去，供调用方自己排版。
#
# 注意 mipl_shell_in 会设 mipl_shell —— 这是整份脚本里唯一一个故意留给
# 调用方的全局量，因为它同时是「有没有」和「是哪一个」两个信息。
mipl_container_health() {
  local root="$1" into="${2:-}"
  local item label paths p found

  mipl_shell="$(mipl_shell_in "$root" || true)"
  mipl_missing=()

  for item in "${MIPL_HEALTH_ITEMS[@]}"; do
    label="${item%%|*}"
    IFS='|' read -r -a paths <<< "${item#*|}"
    found=""
    for p in "${paths[@]}"; do
      if [[ -e "${root}/${p}" || -L "${root}/${p}" ]]; then
        found="/${p}"
        break
      fi
    done
    if [[ -z "$found" ]]; then
      mipl_missing+=("${label}|${paths[*]/#//}")
    fi
  done

  if [[ ${#mipl_missing[@]} -gt 0 ]]; then
    if [[ -n "$into" ]]; then
      local -n _dst="$into"
      _dst=("${mipl_missing[@]}")
    fi
    return 1
  fi
  return 0
}

# mipl_missing_paths <数组名> → 只打印缺失项的路径列，供一行提示用。
# 先加分隔符再加内容（而不是加在内容后面）：否则每项尾巴上那两个空格会在
# 拼接处变成四个，行尾也多一截。
mipl_missing_paths() {
  local -n _arr="$1"
  local entry out=""
  for entry in "${_arr[@]}"; do
    out+="${out:+  }${entry#*|}"
  done
  printf '%s' "$out"
}

# mipl_container_guard <容器目录> <重建命令>
#
# shell / build 进容器前统一走这里：容器残缺就直接停，并且说出**为什么**。
# 不在这里 exit —— 调用方各自决定怎么收场（一个 die，另一个可能只想警告）。
mipl_container_guard() {
  local root="$1" rebuild="$2" where="${3:-}"
  local -a missing=()

  if mipl_container_health "$root" missing; then
    return 0
  fi

  {
    printf '%s[错误]%s 构建容器是残缺的，不能进去。\n' "${C_ERR:-}" "${C_OFF:-}"
    printf '       路径：%s\n' "$root"
    printf '       缺：%s\n' "$(mipl_missing_paths missing)"
    echo
    echo "这不是「容器没建」—— 是 bootstrap 没解压完就被中断了。"
    echo "bootstrap 的条目顺序决定了 os-release 排在第 630 条、usr/bin/bash 排在"
    echo "第 5815 条（共 33105 条），所以一次半途而废的解压恰好会留下 os-release："
    echo "所有「文件在不在」的检查都会说 OK，只有真去执行才炸，报错是 ——"
    echo "  execv(/bin/bash, /bin/bash, /bin/sh) failed: No such file or directory"
    echo "（systemd-nspawn 没带命令时会按序试这几个 shell，一个都执行不了。）"
    echo
    echo "重建（残缺的目录会被删掉，然后干净解压一遍）："
    printf '  rm -rf %s\n' "$root"
    printf '  %s\n' "$rebuild"
    if [[ -n "$where" ]]; then
      echo "（在容器里： ${where}）"
    fi
    echo
    echo "如果重建时下载或解压又断了，脚本现在会自己认出坏文件并重下 —— Issue #32。"
  } >&2
  return 1
}
