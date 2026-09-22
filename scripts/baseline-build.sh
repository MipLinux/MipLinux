#!/usr/bin/env bash
# 构建脚本 —— 用仓库里的 profile（默认）或容器内原版 releng 构建 ISO
#
# 用法：
#   sudo ./scripts/baseline-build.sh --auto                    # 用仓库 profile/ 一条龙构建
#   sudo ./scripts/baseline-build.sh --auto --baseline         # 用容器内原版 releng 构建
#   sudo ./scripts/baseline-build.sh --auto --profile <目录>   # 用指定的 profile 构建
#   sudo ./scripts/baseline-build.sh --auto --keep-work        # 保留工作目录（调试用）
#   sudo ./scripts/baseline-build.sh                           # 交互式：只把容器打开
#
#   一般不直接调用它，走上层入口更省事：
#   sudo ./scripts/mipl.sh build                    # = 本脚本 --auto（profile = 仓库 profile/）
#   sudo ./scripts/mipl.sh build --baseline         # = 本脚本 --auto --baseline
#   sudo ./scripts/mipl.sh build --work /var/tmp/w  # 换容器内的工作目录（默认 /var/tmp/mipl-work）
#   sudo ./scripts/mipl.sh shell                    # 只进容器，不构建（同样挂好 /profile）
#
# 为什么 profile 要挂进容器：
#   profile 是「发行版的源代码」，它属于仓库，不属于容器。所以容器不复制它，
#   而是只读挂载宿主机上的那一份，挂载点固定为 /profile。于是：
#     · 容器里构建用的永远是仓库里那份，不会出现「构建用了一份、改的是另一份」
#     · 容器改不动它（默认只读），profile 的改动只能从宿主机走 git diff
#   排查构建失败时确实需要可写挂载：MIPL_PROFILE_RW=1。
#
# 环境变量：
#   MIPL_WORK_DIR    容器内 mkarchiso 的工作目录，默认 /var/tmp/mipl-work
#                    （**别用 /tmp**：容器里是内存盘。构建前会自动清空它 ——
#                     见下面「工作目录」与 --keep-work）
#   MIPL_KEEP_WORK   设 1 保留工作目录，等价于 --keep-work
#   MIPL_PROFILE     宿主机上的 profile 目录（等价于 --profile；--baseline 时忽略）
#   MIPL_PROFILE_RW  设 1 则 profile 可写挂载（默认只读）
#   MIPL_CONTAINER   容器目录，默认 /var/lib/machines/archbuild
#   MIPL_MACHINE     容器机器名，默认 archbuild
#   MIPL_OUT_DIR     产物目录，默认 <仓库根>/out
#   MIPL_DRY_RUN     设 1（等价于 -n）只打印将执行的命令，不做任何改动
#   MIPL_BOOTSTRAP_URL    bootstrap 的下载地址，默认清华镜像的 latest
#   MIPL_BOOTSTRAP_FILE   bootstrap 的本地缓存，默认 /tmp/archlinux-bootstrap-x86_64.tar.zst
#   MIPL_CHECKSUMS_URL    校验和清单地址，默认与 bootstrap 同目录的 sha256sums.txt
#   MIPL_CHECKSUMS_FILE   校验和清单的本地缓存（默认 <bootstrap>.sha256sums.txt）
#   MIPL_MIRROR_URL       容器里 pacman 用的源，默认清华的 archlinux 仓库
#   MIPL_MIRRORLIST       它在容器内的挂载点，默认 /etc/pacman.d/mirrorlist.mipl
#   MIPL_DNS              容器 /etc/resolv.conf 的 nameserver（空格/逗号分隔）
#   MIPL_DNS_FALLBACK     宿主机也拿不到 nameserver 时的兜底 DNS
#
# 容器里的源与 DNS（Issue #32 的延伸）：
#   bootstrap 自带的 /etc/pacman.d/mirrorlist 有效内容全是
#   `Include = /etc/pacman.d/mirrorlist.d/*.conf` 这种转发，指向的目录可能是空的；
#   自带的 /etc/resolv.conf 更是纯注释、一个 nameserver 都没有。
#   两者都会让 pacman 静默失败 → archiso / mkinitcpio 装不上。
#   所以这两个文件都由宿主机生成后**只读挂进容器**，容器里的原文件不动。
#
#   这里只保证「有一个能用的源」，不解决「哪个源最快」—— 自动测速换源是
#   Issue #18，还没做。眼下要换源就是改 MIPL_MIRROR_URL。
#
# 工具链（Issue #32 的延伸）——「装上了」和「能用」是两回事：
#   装的是 archiso + mkinitcpio + arch-install-scripts。
#   **archiso 不依赖 mkinitcpio**（只依赖 arch-install-scripts、squashfs-tools、
#   libisoburn、mtools、dosfstools、e2fsprogs、erofs-utils…），所以
#   `pacman -S archiso` 永远不会带上 mkinitcpio —— 必须显式装。
#
# 下载与解压都会验完整性（Issue #32）：
#   1. 本地缓存先过 sha256（对照镜像的 sha256sums.txt）—— 对不上就删掉重下；
#   2. 下完再过一遍 sha256 与 zstd 完整性，三次都不通过就报错退出，
#      不会把半截文件留在缓存里冒充「已经下好了」；
#   3. 解压完成后查容器是否真的能用（能执行的 shell / 动态链接器 / pacman），
#      而不是只看 etc/os-release 在不在 —— 它在归档里排第 630 条，
#      usr/bin/bash 排第 5815 条，半途而废的解压必然骗过那种检查。
#
# 文档：docs/work/tech/01-容器环境搭建.md
#       docs/work/tech/02-构建与QEMU测试.md
set -euo pipefail

# ── 配置 ────────────────────────────────────────────────────────────
CONTAINER_DIR="${MIPL_CONTAINER:-/var/lib/machines/archbuild}"
MACHINE_NAME="${MIPL_MACHINE:-archbuild}"
# 定位自身用的是 BASH_SOURCE 而不是 $0：$0 说不清软链和 . 调用的情况。
SELF_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SELF_DIR}/.." && pwd)"
OUT_DIR="${MIPL_OUT_DIR:-${REPO_ROOT}/out}"
BOOTSTRAP_URL="${MIPL_BOOTSTRAP_URL:-https://mirrors.tuna.tsinghua.edu.cn/archlinux/iso/latest/archlinux-bootstrap-x86_64.tar.zst}"
BOOTSTRAP_FILE="${MIPL_BOOTSTRAP_FILE:-/tmp/archlinux-bootstrap-x86_64.tar.zst}"
# 校验和：镜像目录里的 sha256sums.txt。
# 注意它盖的是「那台镜像现在提供的那一版」，所以缓存文件只在正好等于当前版本时
# 才算「已验证」。镜像一升级，checksum_ok 立刻变「对不上 / 不在清单里」，
# 于是重新下载 —— 这正是我们要的，缓存永远跟着镜像的最新版走。
BOOTSTRAP_DIR="${BOOTSTRAP_URL%/*}"
if [[ "$BOOTSTRAP_DIR" == "$BOOTSTRAP_URL" ]]; then
  # 不用 die：这里在函数定义之前，消息得自己打（die 也还不存在）。
  printf '[错误] MIPL_BOOTSTRAP_URL 里没有目录部分，推不出 sha256sums.txt 的位置：%s\n' \
    "$BOOTSTRAP_URL" >&2
  exit 1
fi
CHECKSUMS_URL="${MIPL_CHECKSUMS_URL:-${BOOTSTRAP_DIR}/sha256sums.txt}"
# 校验和也缓存在本地：重跑时不为了一个 1 KB 的文件再打一次网络。
CHECKSUMS_FILE="${MIPL_CHECKSUMS_FILE:-${BOOTSTRAP_FILE}.sha256sums.txt}"

# ── 共用库（容器健康检查、颜色约定）──────────────────────────────────
MIPL_LIB="${SELF_DIR}/mipl-lib.sh"
if [[ ! -r "$MIPL_LIB" ]]; then
  printf '[错误] 缺少共用库：%s —— 仓库不完整或脚本被单独拷走了\n' "$MIPL_LIB" >&2
  exit 1
fi
# shellcheck source=scripts/mipl-lib.sh
MIPL_LIB_COLORS=1 . "$MIPL_LIB"

# 容器内原版 releng：由容器里的 archiso 包提供，是「基线」的定义。
BASELINE_PROFILE="/usr/share/archiso/configs/releng"
# 仓库里的 profile：默认拿它构建。
DEFAULT_PROFILE="${REPO_ROOT}/profile"
# 挂进容器的固定路径。容器内的命令、文档、脚本都只认这一个位置。
PROFILE_INNER="/profile"

# ── 容器里的软件源与 DNS ─────────────────────────────────────────────
# 这两样都不改容器里的原文件，而是宿主机生成好后只读挂进去 —— 于是
# 「这次用的是哪个镜像」和「DNS 从哪来」都是结构上确定的，不靠容器之前
# 碰巧是什么状态。
#
# 为什么非做不可：bootstrap 自带的 /etc/pacman.d/mirrorlist 只有 79 行有效
# 内容，而且全是 `Include = /etc/pacman.d/mirrorlist.d/*.conf` 这种转发，
# 指向的目录在容器里可能是空的 —— 于是 pacman 以 "failed to synchronize"
# 失败，archiso / mkinitcpio 一个也装不上。bootstrap 自带的
# /etc/resolv.conf 更是**纯注释、没有 nameserver**，DNS 直接全废。
MIRROR_URL="${MIPL_MIRROR_URL:-https://mirrors.tuna.tsinghua.edu.cn/archlinux/\$repo/os/\$arch}"
MIRRORLIST_INNER="${MIPL_MIRRORLIST:-/etc/pacman.d/mirrorlist.mipl}"
# 显式指定 DNS。留空就从宿主机的 /etc/resolv.conf 里抄；一个 nameserver
# 都抄不到时用 MIPL_DNS_FALLBACK，保证容器里总有东西可解析。
DNS_FALLBACK="${MIPL_DNS_FALLBACK:-223.5.5.5 119.29.29.29 1.1.1.1}"

MODE="repo"          # repo（仓库/指定的 profile） | baseline（容器内原版 releng）
PROFILE_HOST=""      # 宿主机上的 profile 目录（baseline 模式为空 = 不挂载）
PROFILE_DESC=""      # 给人看的一句话说明
AUTO_BUILD=0
DRY_RUN=0
[[ "${MIPL_DRY_RUN:-0}" == 1 ]] && DRY_RUN=1

# 容器内 mkarchiso 的工作目录。这个默认值全项目只在这里出现一次：
# mipl.sh 总是显式传进来，内层脚本只认 MIPL_WORK_DIR（自己不再兜底）。
# 默认 /var/tmp 而不是 /tmp：nspawn 把容器的 /tmp 覆盖成 tmpfs（内存，默认
# 只有 10% 内存大小），构建树放不下 —— 会在写 efiboot.img 时 ENOSPC（Issue #6）。
WORK_DIR="${MIPL_WORK_DIR:-/var/tmp/mipl-work}"
# 默认 0 = 构建前清掉工作目录（A3 / 坑 1）。1 = 保留，只给调试 _run_once 用。
KEEP_WORK=0
[[ "${MIPL_KEEP_WORK:-0}" == 1 ]] && KEEP_WORK=1

# 构建报告（A7 要的耗时 / 体积 / sha256）用的两个量：
# 脚本启动时刻，以及容器内 mkarchiso 那一段的耗时（在 step_enter 里记）。
BUILD_START="$(date +%s)"
NSPAWN_SECONDS=-1

# ── 辅助函数 ────────────────────────────────────────────────────────
# 颜色与基础输出函数由 mipl-lib.sh 统一提供。
# 告警的后续行：照样是 stderr —— 否则重定向时警告会被拆成两半。
wnote() { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF" >&2; }
dry()  { printf '%s[试运行]%s %s\n' "$C_DIM" "$C_OFF" "$*"; }

# 只给「含空格」的参数加引号：直接 %q 会把 --setenv=k=v 之类也转义成难读的
# 形式，而可读正是试运行的全部意义（与 mipl.sh 同一套约定）。
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
    dry "$(quote_cmd "$@")"
    return 0
  fi
  "$@"
}

require_root() {
  [[ ${EUID} -eq 0 ]] || die "需要 root 权限。请用 sudo 运行。"
}

# 容器的体检报告。doctor / shell / build 三个入口说的是同一件事，
# 免得一个说「已初始化」、另一个在 execv 上炸（Issue #32）。
report_container_health() {
  local root="$1" item label paths p found
  if mipl_container_health "$root"; then
    note "  容器完整，shell：${mipl_shell}"
    return 0
  fi
  for item in "${MIPL_HEALTH_ITEMS[@]}"; do
    label="${item%%|*}"
    IFS='|' read -r -a paths <<< "${item#*|}"
    found=""
    for p in "${paths[@]}"; do
      if [[ -e "${root}/${p}" || -L "${root}/${p}" ]]; then found="/${p}"; break; fi
    done
    if [[ -n "$found" ]]; then
      note "  [ok] ${label}  ${found}"
    else
      wnote "  [缺] ${label}  （找过：${paths[*]/#//}）"
    fi
  done
  return 1
}

# ── 构建报告（A7 要的数字：耗时 / 体积 / sha256）─────────────────────
# 这些以前得事后从 journal 和 ls 里挖，现在构建完直接打在终端上，
# 粘进文档就行。
fmt_duration() {
  local s="${1:-0}"
  if (( s < 60 )); then printf '%d 秒' "$s"
  elif (( s < 3600 )); then printf '%d 分 %02d 秒' "$((s / 60))" "$((s % 60))"
  else printf '%d 时 %02d 分 %02d 秒' "$((s / 3600))" "$(((s % 3600) / 60))" "$((s % 60))"
  fi
}

report_artifacts() {
  local f bytes
  local -a isos=() fresh=()
  shopt -s nullglob
  isos=("${OUT_DIR}"/*.iso)
  shopt -u nullglob

  echo
  info "本次构建报告"

  if [[ $DRY_RUN -eq 1 ]]; then
    note "（试运行：下面是 ${OUT_DIR} 里现有的产物，不是本次构建的）"
    if [[ ${#isos[@]} -gt 0 ]]; then
      printf '%s\n' "${isos[@]}" | sed 's/^/    /'
    else
      note "  （一个都没有）"
    fi
    return 0
  fi

  note "  总耗时（含下载 bootstrap / 解压 / 进容器）：$(fmt_duration "$(( $(date +%s) - BUILD_START ))")"
  if (( NSPAWN_SECONDS >= 0 )); then
    note "  构建耗时（容器内 mkarchiso）：$(fmt_duration "$NSPAWN_SECONDS")"
  fi

  # 只对「比脚本启动还新」的 ISO 算 sha256：1.5 GiB 跑一遍要几秒，历史产物
  # 没必要重算。一个都没有 = 这次其实没产出 —— 坑 1 的典型症状，直接喊出来。
  for f in "${isos[@]}"; do
    if [[ "$(stat -c %Y -- "$f")" -ge "$BUILD_START" ]]; then
      fresh+=("$f")
    fi
  done

  if [[ ${#fresh[@]} -eq 0 ]]; then
    warn "没有比本次构建更新的 ISO —— 这次没真的产出产物（先看坑 1）"
    return 0
  fi

  for f in "${fresh[@]}"; do
    bytes="$(stat -c %s -- "$f")"
    note "  产物：  ${f}"
    note "  体积：  $(fmt_size "$bytes")（${bytes} 字节）"
    if command -v sha256sum >/dev/null 2>&1; then
      note "  sha256：$(sha256sum -- "$f" | awk '{print $1}')"
    fi
  done
  note "  （上面这几行就是 A7 表格里的值）"
}

usage() {
  cat <<'EOF'
用法：sudo ./scripts/baseline-build.sh [选项]

选项：
  --auto             一条龙：下载 bootstrap → 解压 → 进容器构建 ISO
                     （不给就只把容器打开，交给你手工操作）
  --baseline         用容器内原版 releng（/usr/share/archiso/configs/releng）构建，
                     即「基线」。构建挂了时跑一次它，就能分开
                     「环境坏了」和「自己改坏了」。
  --profile <目录>   用指定的 profile 构建（宿主机路径；相对路径按仓库根解析）。
                     不给就是仓库里的 profile/。
  --work <目录>      容器内 mkarchiso 的工作目录，默认 /var/tmp/mipl-work。
                     **别用 /tmp**：nspawn 把容器的 /tmp 覆盖成 tmpfs（内存，
                     默认只有 10% 内存大小），构建树放不下，会在写 efiboot.img
                     时以 No space left on device 失败（Issue #6 的真身）。
  --keep-work        保留工作目录，构建前不清理。只在调试 mkarchiso 的
                     _run_once 行为时用：正常构建必须清，否则它会跳过装包、
                     拷 airootfs、生成 ISO，交给你一个「构建成功」的旧产物。
  -n, --dry-run      只打印将执行的命令，不做任何改动（普通用户也能跑）。
  -h, --help         显示本帮助。

工作目录：
  默认 /var/tmp/mipl-work（容器内）。**别用 /tmp**：systemd-nspawn 默认给容器的
  /tmp 挂一块 tmpfs（内存），默认只有 10% 内存大小；构建树到写 efiboot.img 时
  约 3 GiB，撞上就是 `plain_io read/write: No space left on device`。容器里会
  检查这一点，发现是内存盘就直接报错。
  构建前会自动清空 <work> —— mkarchiso 用目录里的标记文件保证「装包 / 拷
  airootfs / 生成 ISO」只跑一次，不清就会拿到旧产物，<work>/build_date 还会让
  版本号沿用旧值（见 docs/work/2026-09-19.md 坑 1）。
  清理不会导致重新下载包：包缓存在容器内的 /var/cache/pacman/pkg，不在工作目录里。

profile 怎么进容器：
  仓库里的 profile 不复制，而是只读挂载进容器，挂载点固定为 /profile。
  所以容器内的构建命令永远是 mkarchiso ... /profile，构建日志里也会写明
  它来自宿主机的哪个目录 —— 这就是「这次用的是哪份 profile」的证据。
  MIPL_PROFILE_RW=1 可以改成可写挂载（只在排查构建失败时用）。

环境变量：
  MIPL_WORK_DIR    同 --work             MIPL_KEEP_WORK   1 = 同 --keep-work
  MIPL_PROFILE     同 --profile          MIPL_PROFILE_RW  1 = profile 可写挂载
  MIPL_CONTAINER   容器目录              MIPL_MACHINE     容器机器名
  MIPL_OUT_DIR     产物目录              MIPL_DRY_RUN     1 = 同 -n
  MIPL_BOOTSTRAP_URL     bootstrap 下载地址（换镜像用这个）
  MIPL_BOOTSTRAP_FILE    bootstrap 本地缓存（默认 /tmp 下那个）
  MIPL_CHECKSUMS_URL     校验和清单地址（默认与 bootstrap 同目录）
  MIPL_CHECKSUMS_FILE    校验和清单的本地缓存
  MIPL_MIRROR_URL        容器里 pacman 的源（默认清华 archlinux 仓库）
  MIPL_MIRRORLIST        它在容器内的挂载点（默认 /etc/pacman.d/mirrorlist.mipl）
  MIPL_DNS               容器里 /etc/resolv.conf 的 nameserver（空格/逗号分隔）
  MIPL_DNS_FALLBACK      宿主机也拿不到 nameserver 时的兜底 DNS

容器里的源与 DNS：
  这两个文件由宿主机生成后只读挂进容器，容器内的原文件不动：
    <out>/mirrorlist     →  /etc/pacman.d/mirrorlist.mipl（默认清华）
    <out>/resolv.conf    →  /etc/resolv.conf
  为什么非做不可：bootstrap 自带的 mirrorlist 有效内容全是 Include 转发、
  指向的目录可能是空的；自带的 resolv.conf 是纯注释、没有 nameserver。
  pacman 会以 failed to synchronize 失败，archiso / mkinitcpio 一个也装不上。

装什么：
  archiso + mkinitcpio + arch-install-scripts。**archiso 不依赖 mkinitcpio**，
  只装 archiso 永远不会带上它，而构建 initramfs 要用到。

bootstrap 的完整性：
  本地缓存先按镜像的 sha256sums.txt 核对 sha256；对不上就删掉重下。
  下载完成后再核对一遍 sha256 与 zstd 完整性，三次都不通过就报错退出，
  半截文件不会留在缓存里冒充「已下好」。
  解压完成后查容器真的能用（能执行的 shell / 动态链接器 / pacman），
  而不是只看 etc/os-release —— 它在归档里排第 630 条、usr/bin/bash 排第
  5815 条（共 33105 条），半途而废的解压恰好能骗过那种检查（Issue #32）。

文档：docs/work/tech/02-构建与QEMU测试.md
EOF
}

# ── 参数 ────────────────────────────────────────────────────────────
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --auto)
        AUTO_BUILD=1; shift ;;
      --baseline)
        MODE="baseline"; shift ;;
      --profile)
        [[ -n "${2:-}" ]] || die "--profile 后面要跟 profile 目录"
        PROFILE_HOST="$2"; shift 2 ;;
      --work)
        [[ -n "${2:-}" ]] || die "--work 后面要跟目录"
        WORK_DIR="$2"; shift 2 ;;
      --keep-work)
        KEEP_WORK=1; shift ;;
      -n|--dry-run)
        DRY_RUN=1; shift ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        # 以前这里不认的参数一律当空气 —— 「看起来跑了、其实还是老行为」
        # 就是这么来的。现在直接拒绝。
        die "未知参数：$1（用 --help 看用法）" ;;
    esac
  done

  if [[ "$MODE" == "baseline" && -n "$PROFILE_HOST" ]]; then
    die "--baseline 和 --profile 只能选一个：前者用容器内原版 releng，后者用你指的目录"
  fi
}

# ── 定下这次到底用哪个 profile ──────────────────────────────────────
resolve_profile() {
  if [[ "$MODE" == "baseline" ]]; then
    PROFILE_HOST=""
    PROFILE_DESC="容器内原版 releng（${BASELINE_PROFILE}）"
    return 0
  fi

  [[ -n "$PROFILE_HOST" ]] || PROFILE_HOST="${MIPL_PROFILE:-$DEFAULT_PROFILE}"
  # 相对路径按仓库根解析：脚本自己不依赖 cwd，它给的解释也不该依赖 cwd。
  [[ "$PROFILE_HOST" == /* ]] || PROFILE_HOST="${REPO_ROOT}/${PROFILE_HOST}"
  PROFILE_HOST="$(realpath -m -- "$PROFILE_HOST")"

  [[ -d "$PROFILE_HOST" ]] || die "profile 目录不存在：${PROFILE_HOST}
     要用容器内原版 releng 构建，加 --baseline。"
  [[ -f "${PROFILE_HOST}/profiledef.sh" ]] || die "profile 目录里没有 profiledef.sh：${PROFILE_HOST}
     mkarchiso 要的是那个含 profiledef.sh / packages.x86_64 / airootfs/ … 的目录"

  PROFILE_DESC="宿主机 ${PROFILE_HOST} → 容器内 ${PROFILE_INNER}"
}

# ── nspawn 参数（profile 与 /out 的挂载都在这里定）──────────────────
# ── 容器里的源与 DNS：宿主机生成，只读挂进容器 ───────────────────────
# 生成物都放在 $OUT_DIR 里（整个 out/ 都被 .gitignore 忽略，会被挂到容器
# /out，所以它们同时也是「这次到底用了哪个镜像」的现场证据）。

# 镜像列表。容器里那份是 bootstrap 原带的，可能是空的或只剩 Include 转发；
# 我们不动它，而是生成一份干净的挂到 /etc/pacman.d/mirrorlist.mipl。
generate_mirrorlist() {
  local dst="${OUT_DIR}/mirrorlist"
  run mkdir -p "$OUT_DIR"
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "写入 ${dst}（容器内 ${MIRRORLIST_INNER}）："
    printf '        Server = %s\n' "$MIRROR_URL"
    return 0
  fi
  {
    echo "## 由 mipl 生成（baseline-build.sh）—— 容器里的 pacman 用这一份。"
    echo "## 源：${MIRROR_URL}"
    echo "## 容器自带的 /etc/pacman.d/mirrorlist 没被改动。"
    echo "## 换源： sudo MIPL_MIRROR_URL='https://<镜像>/archlinux/\$repo/os/\$arch' ./scripts/mipl.sh build"
    echo
    echo "Server = ${MIRROR_URL}"
  } > "$dst"
  note "软件源：${MIRROR_URL}"
  note "  → 容器内 ${MIRRORLIST_INNER}（只读；不动容器自带的 mirrorlist）"
}

# resolv.conf。nspawn 默认把宿主机那份拷进容器，但宿主机/容器里那份可能
# 只有注释（bootstrap 自带的就是），于是容器里 DNS 全废、pacman 静默失败。
# 这里显式备一份有 nameserver 的挂进去，从根上不等 nspawn 的默认行为。
generate_resolv_conf() {
  local dst="${OUT_DIR}/resolv.conf" ns=() line s

  run mkdir -p "$OUT_DIR"
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "写入 ${dst}（容器内 /etc/resolv.conf）："
    if [[ -n "${MIPL_DNS:-}" ]]; then
      printf '        nameserver %s\n' ${MIPL_DNS}
    else
      printf '        nameserver %s\n' ${DNS_FALLBACK}
    fi
    return 0
  fi

  if [[ -n "${MIPL_DNS:-}" ]]; then
    # 环境变量里可以给多个，用空格或逗号分隔都认。
    IFS=' ,' read -r -a ns <<< "${MIPL_DNS}"
    note "DNS：用 MIPL_DNS 指定的 ${ns[*]}"
  else
    while IFS= read -r line; do
      ns+=("$line")
    done < <(awk '/^[[:space:]]*nameserver[[:space:]]/ { print $2 }' /etc/resolv.conf 2>/dev/null || true)
    if [[ ${#ns[@]} -gt 0 ]]; then
      note "DNS：抄宿主机 /etc/resolv.conf 的 ${ns[*]}"
    else
      IFS=' ' read -r -a ns <<< "${DNS_FALLBACK}"
      warn "宿主机的 /etc/resolv.conf 里没有 nameserver —— 用兜底的 ${ns[*]}"
      wnote "容器里解析不了域名的话，用 MIPL_DNS=\"<你的 DNS>\" 显式指定。"
    fi
  fi

  {
    echo "# 由 mipl 生成（baseline-build.sh）—— 容器里就是这一份。"
    echo "# 宿主机 /etc/resolv.conf 可能只有注释（bootstrap 自带的那份就是纯注释），"
    echo "# 那种情况下容器里 DNS 全废、pacman 静默失败。"
    for s in "${ns[@]}"; do
      echo "nameserver ${s}"
    done
    echo "options edns0 trust-ad"
  } > "$dst"
  note "  → 容器内 /etc/resolv.conf（只读）"
}

build_nspawn_args() {
  NSPAWN_ARGS=(
    systemd-nspawn -D "${CONTAINER_DIR}"
    -u root --machine="${MACHINE_NAME}"
  )

  # 工作目录传进容器。用 --setenv 而不是靠环境继承：nspawn 不会把宿主机的
  # 任意变量透进去（与 mipl.sh 一致）。无条件传：默认值只在 $WORK_DIR 里定一次，
  # 内层脚本自己不再兜底 —— 否则「这次到底用了哪个目录」会有两个答案。
  NSPAWN_ARGS+=(--setenv="MIPL_WORK_DIR=${WORK_DIR}")

  # 源与 DNS：只读挂载 + 显式 --setenv 告诉容器内脚本用哪一份。
  NSPAWN_ARGS+=(--bind-ro="${OUT_DIR}/mirrorlist:${MIRRORLIST_INNER}")
  NSPAWN_ARGS+=(--setenv="MIPL_MIRRORLIST=${MIRRORLIST_INNER}")
  NSPAWN_ARGS+=(--setenv="MIPL_MIRROR_URL=${MIRROR_URL}")
  # --resolv-conf=off 是必须的：nspawn 默认（auto）会按它自己的规则处理
  # /etc/resolv.conf，可能把容器里那份**原样留着**（宿主机那份只有注释时，
  # 容器里就是纯注释 —— DNS 全废）。关掉它，容器里看到的就只有我们挂的这一份，
  # 于是「DNS 从哪来」是结构上确定的，不随 systemd 版本或宿主机状态变。
  NSPAWN_ARGS+=(--resolv-conf=off)
  NSPAWN_ARGS+=(--bind-ro="${OUT_DIR}/resolv.conf:/etc/resolv.conf")

  if [[ -n "$PROFILE_HOST" ]]; then
    local mount_kind="只读挂载"
    if [[ "${MIPL_PROFILE_RW:-0}" == 1 ]]; then
      mount_kind="可写挂载 MIPL_PROFILE_RW=1"
      NSPAWN_ARGS+=(--bind="${PROFILE_HOST}:${PROFILE_INNER}")
    else
      NSPAWN_ARGS+=(--bind-ro="${PROFILE_HOST}:${PROFILE_INNER}")
    fi
    NSPAWN_ARGS+=(--setenv="MIPL_PROFILE=${PROFILE_INNER}")
    NSPAWN_ARGS+=(--setenv="MIPL_PROFILE_SRC=宿主机 ${PROFILE_HOST}（${mount_kind}）")
  else
    NSPAWN_ARGS+=(--setenv="MIPL_PROFILE=${BASELINE_PROFILE}")
    NSPAWN_ARGS+=(--setenv="MIPL_PROFILE_SRC=容器内 archiso 包自带的 releng")
  fi

  NSPAWN_ARGS+=(--bind "${OUT_DIR}:/out")
}

# ── 坑 1 · 构建前清工作目录（A3）────────────────────────────────────
# mkarchiso 用工作目录里的标记文件保证「装包 / 拷 airootfs / 生成 ISO」只跑一次：
#
#   _run_once() {
#       if [[ ! -e "${work_dir}/${run_once_mode}.${1}" ]]; then
#           "$1"; touch "${work_dir}/${run_once_mode}.${1}"
#       fi
#   }
#
# 于是复用同一个工作目录重建，它会跳过这些步骤，交给你一个「构建成功」的旧产物；
# <work_dir>/build_date 还在时 SOURCE_DATE_EPOCH 也沿用旧值（版本号跟着旧）。
# 所以清理是默认行为，不是提醒。要故意续跑（调试 _run_once）用 --keep-work。
#
# 放在宿主机做而不是写进容器内的脚本：这个目录在宿主机上就是
# ${CONTAINER_DIR}${WORK_DIR}，删它不需要容器起得来；而且失败得早 ——
# 不会等 bootstrap 下完、容器起来才发现删不掉。
ensure_clean_work_dir() {
  local work="$WORK_DIR" host_work

  if [[ "$KEEP_WORK" == 1 ]]; then
    warn "--keep-work：保留工作目录，本次不做清理"
    wnote "容器内：${work}"
    wnote "mkarchiso 会跳过装包 / 拷 airootfs / 生成 ISO —— 你刚改的东西"
    wnote "可能不生效，拿到的是上一次的产物（见 docs/work/2026-09-19.md 坑 1）。"
    return 0
  fi

  # 下面每一条都是必需的：这个 rm -rf 拼的是宿主路径，
  # 一个手滑的 `--work /` 就等于把整个构建容器删掉。
  [[ "$work" == /* ]] || die "--work 只接受容器内的绝对路径（默认 /var/tmp/mipl-work），收到：${work}
     相对路径算不出宿主路径，也就说不清要删的是什么。"
  case "$work" in
    /tmp/*|/var/tmp/*) ;;
    *) die "--work 只允许容器内 /tmp/… 或 /var/tmp/… 之下，拒绝清理：${work}
     （要算的宿主路径是 ${CONTAINER_DIR}${work}，白名单之外的地方不敢动）" ;;
  esac
  [[ "$work" != *..* ]] || die "--work 不允许包含 .. ：${work}"

  # rm -rf 会跟着 "link/" 走进目标目录，所以路径上任何一段都不能是符号链接。
  local p="${CONTAINER_DIR}" seg
  local -a segs=()
  IFS='/' read -r -a segs <<< "${work#/}"
  [[ ${#segs[@]} -ge 2 ]] || die "--work 路径太浅，拒绝清理：${work}"
  for seg in "${segs[@]}"; do
    [[ -n "$seg" ]] || continue
    p="${p}/${seg}"
    [[ -L "$p" ]] && die "路径上有符号链接，拒绝清理：${p}"
  done

  host_work="$(realpath -m -- "${CONTAINER_DIR}${work}")"
  case "$host_work" in
    "${CONTAINER_DIR}"/*) ;;
    *) die "解析后的路径不在容器目录里，拒绝清理：${host_work}" ;;
  esac

  if [[ ! -e "$host_work" ]]; then
    if [[ $DRY_RUN -eq 1 && ! -r "$CONTAINER_DIR" ]]; then
      # /var/lib/machines 是 0700：非 root 的试运行看不见里面，别假装它是干净的。
      note "（试运行：读不到 ${CONTAINER_DIR}，无法确认是否存在；真跑时会清理 ${work}）"
    else
      note "工作目录不存在，无需清理：${work}（容器内）"
      return 0
    fi
  fi

  info "清理上次的构建工作目录（坑 1）"
  note "  容器内：  ${work}"
  note "  宿主路径：${host_work}"
  note "  要故意保留：--keep-work（或 MIPL_KEEP_WORK=1）"
  run rm -rf -- "$host_work"
  [[ $DRY_RUN -eq 1 || ! -e "$host_work" ]] || die "删除失败：${host_work}"
}

# ── 步骤 1 · 下载 bootstrap（带校验）────────────────────────────────
# 原来这里只判断「文件在不在」，于是被截断的下载会被当成下载好了（缺 -f
# 时 HTTP 错误页也一样算「下载完成」）；解压被中断留下的残缺容器又会被下一次
# 运行当成「已初始化」。两条路都通向同一个现场，见 Issue #32。
BOOTSTRAP_CACHE_DIR="$(dirname -- "${BOOTSTRAP_FILE}")"
[[ -n "$BOOTSTRAP_CACHE_DIR" && "$BOOTSTRAP_CACHE_DIR" != "." ]] || BOOTSTRAP_CACHE_DIR="/tmp"

# checksum_ok <文件>：0 = 与镜像的 sha256sums.txt 对得上，且 zstd 层完整。
# 判断本身在共用库（mipl_bootstrap_cache_ok）—— doctor 报的和这里做的是同一套
# 标准，不许有第二份实现（Issue #32 就是「两处判断不一致」长出来的）。
checksum_ok() {
  mipl_bootstrap_cache_ok "$1" "$CHECKSUMS_FILE"
}

# 校验没过的原因，用中文说一句。退出码 → 人话的映射也在共用库里。
checksum_reason() {
  mipl_checksum_reason "$1"
}

# 先取清单，让冷缓存与热缓存走同一条校验路径（Issue #39）。
download_checksums() {
  [[ -s "$CHECKSUMS_FILE" ]] && return 0

  info "本地还没有校验和清单，取一份：${CHECKSUMS_URL}"
  curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 \
    -o "${CHECKSUMS_FILE}.part" "$CHECKSUMS_URL" \
    || warn "校验和清单下载失败：${CHECKSUMS_URL}"
  if [[ -s "${CHECKSUMS_FILE}.part" ]]; then
    mv -f "${CHECKSUMS_FILE}.part" "$CHECKSUMS_FILE"
  else
    rm -f "${CHECKSUMS_FILE}.part"
  fi
}

# 手上这份归档可信吗？不可信就删掉，让下载流程重来。
#
# 为什么解压前还要再问一次：容器完整时 step_extract 会直接跳过解压，而这中间
# 缓存完全可能变坏或变旧（手动 cp 进来的、下到一半的、或者你在两次构建之间
# 换了镜像）。直接 tar 一个坏归档，得到的正是 Issue #32 那份残缺容器 ——
# 而这时候 step_download 已经跑过了，它只看了「容器在不在解压那一步」。
ensure_usable_bootstrap() {
  local rc=0
  # 试运行不许有任何副作用 —— 包括「删掉坏缓存」这种听起来正确的动作。
  # 这里只报告结论，真正的删除留给真跑。
  if [[ $DRY_RUN -eq 1 ]]; then
    if [[ -s "$CHECKSUMS_FILE" ]] && ! checksum_ok "$BOOTSTRAP_FILE"; then
      note "（试运行：这份缓存的 sha256 与清单对不上，真跑时会删掉重下）"
    fi
    return 0
  fi
  # 清单在手里才做完整校验（哈希是唯一能证明「这份就是镜像那一版」的东西）。
  if [[ -s "$CHECKSUMS_FILE" ]]; then
    checksum_ok "$BOOTSTRAP_FILE" && return 0
    rc=$MIPL_CHK_LAST
    warn "手上的 bootstrap 不可用：$(checksum_reason "$rc")"
    note "  文件：${BOOTSTRAP_FILE}"
    run rm -f -- "$BOOTSTRAP_FILE"
    step_download
    return 0
  fi
  # 没有清单时只查 zstd 完整性。这一条挡不住「旧版本但完整」的文件，
  # 但那种文件 tar 得动，后面解压后的容器体检还兜着 —— 不会像半截文件那样
  # 无声无息地造出一个残缺容器。
  mipl_zstd_complete "$BOOTSTRAP_FILE" && return 0
  warn "手上的 bootstrap 是半截的（zstd 完整性检查没过）"
  note "  文件：${BOOTSTRAP_FILE}"
  run rm -f -- "$BOOTSTRAP_FILE"
  step_download
}

step_download() {
  local attempt verified=0 rc=0

  # 清单必须在下载循环之前取得，否则冷缓存无从核对新文件。
  if [[ $DRY_RUN -eq 0 ]]; then
    download_checksums
  fi

  if [[ -f "$BOOTSTRAP_FILE" ]]; then
    info "已有 bootstrap 缓存：${BOOTSTRAP_FILE}  ($(file_size "$BOOTSTRAP_FILE"))"
    if [[ $DRY_RUN -eq 1 ]]; then
      note "（试运行：不校验也不重下；真跑时会先核对 sha256 与 zstd 完整性）"
      return 0
    fi
    if checksum_ok "$BOOTSTRAP_FILE"; then
      ok "缓存校验通过（sha256 与镜像的 sha256sums.txt 一致，zstd 完整）"
      return 0
    fi
    rc=$MIPL_CHK_LAST
    warn "缓存不能用：$(checksum_reason "$rc")—— 删掉重下"
    note "  缓存：  ${BOOTSTRAP_FILE}"
    note "  清单：  ${CHECKSUMS_FILE}（镜像换版本时上一版就查不到了，这属正常）"
    run rm -f -- "$BOOTSTRAP_FILE"
  fi

  info "下载 Arch bootstrap…"
  note "${BOOTSTRAP_URL}"
  note "  → ${BOOTSTRAP_FILE}"

  for attempt in 1 2 3; do
    if [[ $DRY_RUN -eq 1 ]]; then
      dry "curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 -C - \\"
      dry "     -o ${BOOTSTRAP_FILE} ${BOOTSTRAP_URL}"
      note "（试运行，未真的下载）"
      return 0
    fi

    if [[ -f "$BOOTSTRAP_FILE" ]]; then
      note "  接着上次下（-C -）"
      curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 -C - \
        --progress-bar -o "$BOOTSTRAP_FILE" "$BOOTSTRAP_URL" || true
    else
      curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 \
        --progress-bar -o "$BOOTSTRAP_FILE" "$BOOTSTRAP_URL" || true
    fi

    # 校验和 zstd 完整性是同一个判断（共用库），所以这里只报一句原因。
    if checksum_ok "$BOOTSTRAP_FILE"; then
      verified=1
      ok "下载完成并已校验：$(file_size "$BOOTSTRAP_FILE")"
      break
    fi
    rc=$MIPL_CHK_LAST
    warn "第 ${attempt}/3 次：$(checksum_reason "$rc")"

    # 删掉重来：半截的文件留着只会让下一次继续下到同一个坏尾巴上。
    run rm -f -- "$BOOTSTRAP_FILE"
  done

  if [[ $verified -eq 0 ]]; then
    die "bootstrap 下载三次都没通过校验：${BOOTSTRAP_URL}
     半截文件已经删掉了，不会留在 ${BOOTSTRAP_CACHE_DIR} 里冒充缓存。

     换个镜像（现在是 ${BOOTSTRAP_DIR}）：
       sudo MIPL_BOOTSTRAP_URL=<别的镜像>/archlinux/iso/latest/archlinux-bootstrap-x86_64.tar.zst \\
         ${MIPL_CMD} build
     官方与备用镜像见 docs/work/tech/01-容器环境搭建.md。

     想确认本地缓存到底是什么状态：
       ${MIPL_CMD} doctor
       ${MIPL_CMD} clean --bootstrap      # 把缓存清干净，下次重头下"
  fi
}

# ── 步骤 2 · 解压成容器（残缺就认出残缺）─────────────────────────────
# 「跳过解压」的条件原来是 etc/os-release 存在 —— 它不是解压完成的标志：
# bootstrap 里 os-release 排在第 630 条，而 usr/bin/bash 排在第 5815 条
# （共 33105 条）。一次被 Ctrl-C / 断线 / 盘满打断的解压，留下的正是
# 「有 os-release、没有 bash」这种谁也看不出来的残缺容器（Issue #32）。
#
# 所以解压前查健康，解压后**再查一遍**：后者才是真正的完成判据。
step_extract() {
  if [[ -d "$CONTAINER_DIR" ]]; then
    if mipl_container_health "$CONTAINER_DIR"; then
      info "容器已存在且完整，跳过解压（shell：${mipl_shell}）"
      return
    fi
    if [[ -e "${CONTAINER_DIR}/etc/os-release" ]]; then
      warn "容器目录在，但它是残缺的 —— 删掉重新解压"
      report_container_health "$CONTAINER_DIR"
    else
      info "容器目录存在但没有文件系统，重新解压"
    fi
    run rm -rf -- "$CONTAINER_DIR"
  fi

  if [[ $DRY_RUN -eq 0 && ! -f "$BOOTSTRAP_FILE" ]]; then
    die "bootstrap 不在：${BOOTSTRAP_FILE}（下载那一步没走完？）"
  fi

  # 解压之前再验一次缓存：tar 一个坏归档 = 造一个残缺容器。
  ensure_usable_bootstrap

  info "解压到 ${CONTAINER_DIR}…"
  note "  tar --numeric-owner -xpf ${BOOTSTRAP_FILE} -C ${CONTAINER_DIR} --strip-components=1"
  run mkdir -p "$CONTAINER_DIR"

  # tar 自己的报错已经够具体了，但被 set -e 直接带走时人只看到一行；
  # 这里包一层，好把「下载的归档是坏的」和「盘写不进去」分开说。
  local rc=0
  if [[ $DRY_RUN -eq 0 ]]; then
    # --numeric-owner 保留 uid/gid；--strip-components=1 去掉顶层 root.x86_64/
    tar --numeric-owner -xpf "$BOOTSTRAP_FILE" \
        -C "$CONTAINER_DIR" --strip-components=1 || rc=$?
    if [[ $rc -ne 0 ]]; then
      run rm -rf -- "$CONTAINER_DIR"
      die "解压失败（tar 退出码 ${rc}）：${BOOTSTRAP_FILE}
     半截的容器目录已经删掉了 —— 留着它只会被下次运行当成「已初始化」。

     最可能的原因是归档不完整或落盘失败。先看这两个：
       df -h $(dirname -- "$CONTAINER_DIR")     # 空间还够吗（解压后约 576 MB）
       ${MIPL_CMD} clean --bootstrap            # 清掉缓存，下次重下并重新校验"
    fi
  else
    note "（试运行，未真的解压；下面按容器已就绪继续演示）"
    return 0
  fi

  [[ -f "${CONTAINER_DIR}/etc/os-release" ]] \
    || die "解压结果异常：找不到 ${CONTAINER_DIR}/etc/os-release"

  # 真正的完成判据。os-release 在第 630 条就有了，靠它判定必然误判（Issue #32）。
  if ! mipl_container_health "$CONTAINER_DIR"; then
    report_container_health "$CONTAINER_DIR"
    die "解压出来的容器不完整（见上）。解压过程没报错却缺文件，通常是归档本身是坏的：
       ${MIPL_CMD} clean --bootstrap    # 删掉缓存的 bootstrap
       ${MIPL_CMD} build                # 重新下载（会校验）并重新解压"
  fi
  ok "解压完成，容器可用（shell：${mipl_shell}）"
}

# ── 容器内执行的脚本（构建过程本身）────────────────────────────────
render_inner_script() {
  cat <<'INNER_SCRIPT'
#!/usr/bin/env bash
# 由宿主机的 scripts/baseline-build.sh 生成并写入容器，在容器内执行。
set -euo pipefail

PROFILE="${MIPL_PROFILE:-/usr/share/archiso/configs/releng}"
PROFILE_SRC="${MIPL_PROFILE_SRC:-（未说明）}"
# 没有兜底值：宿主机一定用 --setenv 传进来（默认值只在宿主机定一次）。
WORK_DIR="${MIPL_WORK_DIR:?工作目录没传进来：宿主机应该用 --setenv 传 MIPL_WORK_DIR}"

echo "==> 构建 profile：${PROFILE}"
echo "    来源：${PROFILE_SRC}"
if [[ ! -f "${PROFILE}/profiledef.sh" ]]; then
  echo "错误：${PROFILE} 里没有 profiledef.sh —— profile 路径不对" >&2
  exit 1
fi

# 工作目录不能是内存盘：nspawn 默认把容器的 /tmp 覆盖成 tmpfs（默认只有 10%
# 内存大小），构建树到写 efiboot.img 时约 3 GiB，撞上就是：
#     plain_io read/write: No space left on device
# 在这里拦住，比跑二十分钟再失败划算得多（Issue #6 的真身）。
if command -v findmnt >/dev/null 2>&1; then
  _work_parent="$(dirname -- "${WORK_DIR}")"
  _work_fstype="$(findmnt -no FSTYPE --target "${_work_parent}" 2>/dev/null || true)"
  if [[ "${_work_fstype}" == tmpfs ]]; then
    echo "错误：工作目录在内存盘上（tmpfs）：${WORK_DIR}" >&2
    echo "      容器里的 /tmp 是 systemd-nspawn 默认挂上去的 tmpfs，默认只有 10%" >&2
    echo "      内存大小；构建树到写 efiboot.img 时约 3 GiB，会以 No space left on" >&2
    echo "      device 失败 —— 这正是 Issue #6 的真身。" >&2
    df -h -- "${_work_parent}" 2>/dev/null | sed 's/^/      /' >&2 || true
    echo "      换一个目录（容器内普通目录 → 宿主磁盘）：" >&2
    echo "        --work /var/tmp/mipl-work" >&2
    echo "      确实要用内存盘：在宿主机设 SYSTEMD_NSPAWN_TMPFS_TMP=0，" >&2
    echo "      让 /tmp 保持镜像里的普通目录。" >&2
    exit 1
  fi
fi

echo "==> 软件源（镜像）"
# 这里永远看到的是宿主机准备好、只读挂进来的那份，所以「用的是哪个镜像」是
# 结构上确定的：容器自己的 /etc/pacman.d/mirrorlist 是 bootstrap 原带的（容易
# 是空的或全是 Include 转发），我们不改它，而是把干净的一份盖在上面。
MIRRORLIST="${MIPL_MIRRORLIST:-/etc/pacman.d/mirrorlist.mipl}"
if [[ -f "${MIRRORLIST}" ]]; then
  echo "    用 ${MIRRORLIST}（宿主机只读挂载，内容是干净的镜像列表）"
  awk '!/^[[:space:]]*#/ && NF { print "      " $0 }' "${MIRRORLIST}"
else
  echo "    警告：没挂到 ${MIRRORLIST}，只能用容器自带的镜像列表"
  echo "          它是空的或全是注释时，pacman 会以 'failed to synchronize' 失败"
  if ! awk '!/^[[:space:]]*#/ && NF { found = 1 } END { exit !found }' \
       /etc/pacman.d/mirrorlist 2>/dev/null; then
    echo "          而且 /etc/pacman.d/mirrorlist 里没有一个有效的 Server ——"
    echo "          这次多半装不上包。"
  fi
fi

echo "==> DNS 解析"
# nspawn 默认把宿主机的 resolv.conf 拷进来，但宿主机那份可能只有注释
# （bootstrap 自带的 /etc/resolv.conf 就是纯注释），于是容器里 DNS 全废、
# pacman 静默失败。所以宿主机显式挂了一份进来，这里确认一下它真的在。
if grep -qE '^[[:space:]]*nameserver[[:space:]]' /etc/resolv.conf 2>/dev/null; then
  awk '/^[[:space:]]*nameserver[[:space:]]/ { print "    " $0 }' /etc/resolv.conf
  if ! getent hosts 'mirror' >/dev/null 2>&1; then
    # getent 用 NSS，不等于 DNS；这里只是提醒，不当失败处理。
    :
  fi
else
  echo "    警告：/etc/resolv.conf 里没有 nameserver —— 容器里解析不了域名。"
  echo "          宿主机上看 /etc/resolv.conf；需要时用 MIPL_DNS=\"1.1.1.1\" 显式指定。"
fi

echo "==> 初始化密钥环（若尚未初始化）"
if [[ ! -d /etc/pacman.d/gnupg/private-keys-v1.d ]] || \
   [[ -z "$(ls -A /etc/pacman.d/gnupg/private-keys-v1.d 2>/dev/null)" ]]; then
  pacman-key --init
  pacman-key --populate archlinux
else
  echo "    已初始化，跳过"
fi

echo "==> 更新包数据库"
# 单独一步：pacman -Sy 失败是「源不通」，和「装包失败」是两回事，
# 分开报才说得清是哪一头的问题。
if ! pacman -Sy --noconfirm; then
  echo "错误：pacman -Sy 失败 —— 包数据库同步不下来。按这个顺序查：" >&2
  echo "      1) 镜像：上面那行 awk 打出来的 Server 是不是有效" >&2
  echo "      2) DNS ：getent hosts mirrors.tuna.tsinghua.edu.cn 有没有结果" >&2
  echo "      3) 时间：date 差太多的话 PGP 校验会失败" >&2
  exit 1
fi

# 要装什么、以及为什么：
#   archiso    提供 mkarchiso / pacstrap，构建本体
#   mkinitcpio 生成 initramfs 的工具。**它不在 archiso 的依赖里**
#              （archiso 只依赖 arch-install-scripts、squashfs-tools、
#               libisoburn、mtools、dosfstools、e2fsprogs、erofs-utils…），
#              所以只装 archiso 永远不会带上它。
#   arch-install-scripts  显式列出来，免得依赖变动后 pacstrap 悄悄不见了
WANT_PKGS=(archiso mkinitcpio arch-install-scripts)

echo "==> 安装构建工具链：${WANT_PKGS[*]}"
pacman_install() {
  # 失败不在这里 exit：下面统一报错，好把三种原因的提示一次给全。
  if ! pacman -S --needed --noconfirm "${WANT_PKGS[@]}"; then
    echo "    装包失败，刷新密钥环再试一次……"
    # 依赖包换签名密钥、或密钥环是旧的，都会让装包以 PGP 错误失败；
    # --populate 是幂等的，重来一次通常就过了。
    pacman-key --populate archlinux || true
    pacman -Sy --noconfirm || true
    pacman -S --needed --noconfirm "${WANT_PKGS[@]}" || return 1
  fi
}
if ! pacman_install; then
  echo "错误：工具链没装上（见上面的 pacman 输出）。" >&2
  echo "      容器缺的这几个包在 extra / core 仓库里，装不上通常是：" >&2
  echo "        · 镜像无效或不通（看上面「DNS 解析」与「软件源」两段）" >&2
  echo "        · 密钥环坏了：在容器里跑 pacman-key --init && pacman-key --populate archlinux" >&2
  echo "        · 时间不对：date 差太多会让 PGP 校验失败" >&2
  exit 1
fi
echo "    archiso    版本：$(pacman -Q archiso 2>/dev/null || echo 未知)"
echo "    mkinitcpio 版本：$(pacman -Q mkinitcpio 2>/dev/null || echo 未知)"
# 上面这两行是「profile/ 与 releng 零差异」这条验收的参照物：
# profile/ 是照这个 archiso 版本拷的。不记下来，以后 diff 失败时分不清是
# archiso 升级了，还是自己改坏了。

echo "==> 工具链检查"
_missing_tools=()
# 这份清单是有出处的，不是凭感觉列的：
#   · mkarchiso / pacstrap / arch-chroot  —— 构建本体
#   · mksquashfs / xorriso / mkfs.vfat / mkfs.ext4 / mkfs.erofs
#                    —— mkarchiso 自己会 `command -v` 检查这几个（见它的
#                       _validate_requirements_* 与各 iso 生成函数）
#   · mmd / mcopy    —— mtools，做 EFI 的 FAT 镜像要用
#   · gzip / bsdtar / awk / find / openssl —— mkarchiso 同样逐个检查
#   · mkinitcpio     —— 生成 initramfs。**它不属于 archiso 的依赖**，
#                       只装 archiso 不会有它
#   · zstd           —— 压缩 airootfs 镜像（airootfs_image_tool_options 里用）
#
# 注意：mkinitcpio-archiso **不是命令**，它提供的是
# /usr/lib/initcpio/{hooks,install}/archiso 这些 hook 文件，
# 所以不能拿去 command -v（那样每次都会假报缺失）。
INNER_TOOLS=(
  mkarchiso pacstrap arch-chroot
  mkinitcpio
  mksquashfs xorriso zstd
  mkfs.vfat mkfs.ext4 mkfs.erofs
  mmd mcopy
  gzip bsdtar awk find openssl
)
for c in "${INNER_TOOLS[@]}"; do
  printf '    %-18s ' "$c"
  if command -v "$c" >/dev/null 2>&1; then
    echo OK
  else
    echo 缺失
    _missing_tools+=("$c")
  fi
done

# 命令在不在，和「包装没装上」是两件事：包在而命令不在，说明容器已经
# 半坏（比如 /usr/bin 被改过）。一起报出来，省得下次再猜。
_missing_pkgs=()
for p in archiso mkinitcpio arch-install-scripts; do
  pacman -Q "$p" >/dev/null 2>&1 || _missing_pkgs+=("$p")
done

if [[ ${#_missing_tools[@]} -gt 0 || ${#_missing_pkgs[@]} -gt 0 ]]; then
  [[ ${#_missing_tools[@]} -gt 0 ]] \
    && echo "错误：容器里缺这些命令：${_missing_tools[*]}" >&2
  [[ ${#_missing_pkgs[@]} -gt 0 ]] \
    && echo "错误：容器里缺这些包：${_missing_pkgs[*]}" >&2
  echo "      它们由这些包装着（在容器里补装）：" >&2
  echo "        archiso               → mkarchiso / pacstrap / arch-chroot" >&2
  echo "        mkinitcpio            → mkinitcpio（**archiso 不依赖它**）" >&2
  echo "        squashfs-tools        → mksquashfs" >&2
  echo "        libisoburn            → xorriso" >&2
  echo "        dosfstools            → mkfs.vfat" >&2
  echo "        mtools                → mmd / mcopy" >&2
  echo "        erofs-utils           → mkfs.erofs" >&2
  echo "      一条命令补齐：" >&2
  echo "        pacman -S --needed archiso mkinitcpio arch-install-scripts \\" >&2
  echo "          squashfs-tools libisoburn dosfstools mtools erofs-utils zstd" >&2
  exit 1
fi
echo "    全部到位。"

echo "==> 开始构建"
echo "    工作目录：${WORK_DIR}"
mkarchiso -v -w "${WORK_DIR}" -o /out "${PROFILE}"

echo "==> 构建完成，产物："
ls -lh /out/*.iso
INNER_SCRIPT
}

write_inner_script() {
  local dst="${CONTAINER_DIR}/root/baseline-build.sh"
  if [[ $DRY_RUN -eq 1 ]]; then
    dry "写入 ${dst}，内容如下："
    render_inner_script | sed 's/^/    /'
    return 0
  fi
  render_inner_script > "$dst"
  chmod +x "$dst"
}

# ── 步骤 3 · 进入容器 ───────────────────────────────────────────────
step_enter() {
  info "准备输出目录: ${OUT_DIR}"
  run mkdir -p "${OUT_DIR}"

  # 先把容器要用的「源」和「DNS」备好 —— 这两个文件是挂载源，
  # build_nspawn_args 会把它们写进 nspawn 参数，所以顺序不能反。
  generate_mirrorlist
  generate_resolv_conf

  build_nspawn_args

  # 进容器之前最后拦一道。step_extract 已经查过，但「解压完 → 进容器」之间
  # 人可能手动动过这个目录，而 nspawn 遇到残缺容器给出的是一句
  # execv(...) failed: No such file or directory —— 那时候再解释就晚了
  # （Issue #32）。这里停下，还能把「缺什么、怎么重建」说清楚。
  # 试运行不拦：这时候容器可能压根还没建，而那正是 -n 要演示的正常起点。
  if [[ $DRY_RUN -eq 0 ]] && ! mipl_container_guard "$CONTAINER_DIR" "${MIPL_CMD} build"; then
    die "与其进去撞 execv，不如在这里停下。"
  fi

  # profile 的挂载点先备好：老版本 systemd 不会自动创建 nspawn 的目的路径。
  if [[ -n "$PROFILE_HOST" ]]; then
    run mkdir -p "${CONTAINER_DIR}${PROFILE_INNER}"
  fi

  if [[ "$AUTO_BUILD" -eq 1 ]]; then
    info "在容器内构建（${PROFILE_DESC}）"
    write_inner_script
    ensure_clean_work_dir
    # 只量「进容器到构建结束」这一段：报告里的两个耗时在 A7 里要分开看。
    local _nspawn_start=$SECONDS
    run "${NSPAWN_ARGS[@]}" /root/baseline-build.sh
    NSPAWN_SECONDS=$(( SECONDS - _nspawn_start ))
  else
    # 交互模式下容器里到底该敲哪个 profile，取决于这次有没有挂载：
    # repo 模式挂在 /profile，baseline 模式用容器自带的那份。
    local hint_profile hint_note
    if [[ -n "$PROFILE_HOST" ]]; then
      hint_profile="$PROFILE_INNER"
      hint_note="# 构建。仓库的 profile 已经只读挂载在 ${PROFILE_INNER}，
  # 原版 releng 在 ${BASELINE_PROFILE}
  # 想确认这两份是不是一份（A1 的验收）：
  #   diff -r --no-dereference ${PROFILE_INNER} ${BASELINE_PROFILE}"
    else
      hint_profile="$BASELINE_PROFILE"
      hint_note="# 构建。这次用容器自带的原版 releng（没有挂载 profile）"
    fi

    # 交互模式不自动清（你进去就是要动手的），但坑 1 一样会咬人 —— 说清楚。
    warn "交互模式不会替你清工作目录：${WORK_DIR}（容器内）"
    wnote "里面有上次的 _run_once 标记时，mkarchiso 会跳过装包 / 拷 airootfs /"
    wnote "生成 ISO，给你一个旧产物。手工重建前先删掉它：rm -rf ${WORK_DIR}"
    wnote "（一条龙的 sudo ./scripts/mipl.sh build 会自动清，不用管这件事）"

    info "进入容器。请在容器内执行："
    cat <<HINT

  # 首次需要先初始化密钥环
  pacman-key --init && pacman-key --populate archlinux

  # 安装构建工具链
  pacman -S archiso

  ${hint_note}
  mkarchiso -v -w ${WORK_DIR} -o /out ${hint_profile}

HINT
    run "${NSPAWN_ARGS[@]}"
  fi
}

# ── 主流程 ──────────────────────────────────────────────────────────
main() {
  parse_args "$@"

  # 试运行不碰任何东西，所以普通用户也能跑 —— root 检查留给真要动手的时候。
  if [[ $DRY_RUN -eq 0 ]]; then
    require_root
    command -v systemd-nspawn >/dev/null 2>&1 || die "找不到 systemd-nspawn"
  fi

  resolve_profile
  info "构建 profile： ${PROFILE_DESC}"
  if [[ "$MODE" == "baseline" ]]; then
    note "基线构建：用它分开「环境坏了」和「自己改坏了」"
  fi

  step_download
  step_extract
  step_enter

  if [[ "${AUTO_BUILD}" -eq 1 ]]; then
    # 耗时 / 体积 / sha256 —— A7 要的数字（试运行里只列现有产物）。
    report_artifacts
    echo
    info "下一步：QEMU 引导验证"
    cat <<EOF

  cd ${REPO_ROOT}
  sudo ./scripts/mipl.sh qemu

  它会自己探测 OVMF 固件路径、每次重新复制一份变量文件，再启动 QEMU。
  只想看它准备执行什么： sudo ./scripts/mipl.sh -n qemu

  预期结果：出现 [root@archiso ~]# 提示符
  （官方 releng 没有桌面环境，命令行提示符就是成功）

  这次构建挂了的话，跑一次基线做对照：

  sudo ./scripts/mipl.sh build --baseline

  基线能过 → 问题在自己改的 profile；基线也过不了 → 问题在环境。

EOF
  fi
}

main "$@"
