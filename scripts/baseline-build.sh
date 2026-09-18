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
#
# 文档：docs/work/tech/01-容器环境搭建.md
#       docs/work/tech/02-构建与QEMU测试.md
set -euo pipefail

# ── 配置 ────────────────────────────────────────────────────────────
CONTAINER_DIR="${MIPL_CONTAINER:-/var/lib/machines/archbuild}"
MACHINE_NAME="${MIPL_MACHINE:-archbuild}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${MIPL_OUT_DIR:-${REPO_ROOT}/out}"
BOOTSTRAP_URL="${MIPL_BOOTSTRAP_URL:-https://mirrors.tuna.tsinghua.edu.cn/archlinux/iso/latest/archlinux-bootstrap-x86_64.tar.zst}"
BOOTSTRAP_FILE="${MIPL_BOOTSTRAP_FILE:-/tmp/archlinux-bootstrap-x86_64.tar.zst}"

# 容器内原版 releng：由容器里的 archiso 包提供，是「基线」的定义。
BASELINE_PROFILE="/usr/share/archiso/configs/releng"
# 仓库里的 profile：默认拿它构建。
DEFAULT_PROFILE="${REPO_ROOT}/profile"
# 挂进容器的固定路径。容器内的命令、文档、脚本都只认这一个位置。
PROFILE_INNER="/profile"

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
# 颜色跟 mipl.sh 用同一套约定：非终端、或设了 NO_COLOR 就不上色。
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  C_INFO=$'\033[1;34m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'
  C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_INFO=''; C_WARN=''; C_ERR=''; C_DIM=''; C_OFF=''
fi

info() { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
warn() { printf '%s警告:%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%s错误:%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }
note() { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF"; }
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

# ── 构建报告（A7 要的数字：耗时 / 体积 / sha256）─────────────────────
# 这些以前得事后从 journal 和 ls 里挖，现在构建完直接打在终端上，
# 粘进文档就行。
fmt_size() {
  awk -v b="${1:-0}" 'BEGIN{
    split("B KB MB GB TB", a, " "); i = 1
    while (b >= 1024 && i < 5) { b /= 1024; i++ }
    if (i == 1) printf "%d %s", b, a[i]; else printf "%.1f %s", b, a[i]
  }'
}

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
build_nspawn_args() {
  NSPAWN_ARGS=(
    systemd-nspawn -D "${CONTAINER_DIR}"
    -u root --machine="${MACHINE_NAME}"
  )

  # 工作目录传进容器。用 --setenv 而不是靠环境继承：nspawn 不会把宿主机的
  # 任意变量透进去（与 mipl.sh 一致）。无条件传：默认值只在 $WORK_DIR 里定一次，
  # 内层脚本自己不再兜底 —— 否则「这次到底用了哪个目录」会有两个答案。
  NSPAWN_ARGS+=(--setenv="MIPL_WORK_DIR=${WORK_DIR}")

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

# ── 步骤 1 · 下载 bootstrap ─────────────────────────────────────────
step_download() {
  if [[ -f "${BOOTSTRAP_FILE}" ]]; then
    info "bootstrap 已存在，跳过下载: ${BOOTSTRAP_FILE}"
    return
  fi
  info "下载 Arch bootstrap…"
  note "${BOOTSTRAP_URL}"
  run curl -L --progress-bar -o "${BOOTSTRAP_FILE}" "${BOOTSTRAP_URL}"
  if [[ $DRY_RUN -eq 1 ]]; then
    note "（试运行，未真的下载）"
    return 0
  fi
  info "下载完成: $(du -h "${BOOTSTRAP_FILE}" | cut -f1)"
}

# ── 步骤 2 · 解压成容器 ─────────────────────────────────────────────
step_extract() {
  if [[ -f "${CONTAINER_DIR}/etc/os-release" ]]; then
    info "容器目录已存在且看起来有效，跳过解压"
    return
  fi
  info "解压到 ${CONTAINER_DIR}…"
  run mkdir -p "${CONTAINER_DIR}"
  # --numeric-owner 保留 uid/gid；--strip-components=1 去掉顶层 root.x86_64/
  run tar --numeric-owner -xpf "${BOOTSTRAP_FILE}" \
      -C "${CONTAINER_DIR}" --strip-components=1

  if [[ $DRY_RUN -eq 1 ]]; then
    note "（试运行，未真的解压；下面按容器已就绪继续演示）"
    return 0
  fi

  [[ -f "${CONTAINER_DIR}/etc/os-release" ]] \
    || die "解压结果异常：找不到 ${CONTAINER_DIR}/etc/os-release"
  info "解压完成"
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

echo "==> 初始化密钥环（若尚未初始化）"
if [[ ! -d /etc/pacman.d/gnupg/private-keys-v1.d ]] || \
   [[ -z "$(ls -A /etc/pacman.d/gnupg/private-keys-v1.d 2>/dev/null)" ]]; then
  pacman-key --init
  pacman-key --populate archlinux
else
  echo "    已初始化，跳过"
fi

echo "==> 安装/确认 archiso"
pacman -S --needed --noconfirm archiso
echo "    archiso 版本：$(pacman -Q archiso 2>/dev/null || echo 未知)"
# 上面这行的版本号是「profile/ 与 releng 零差异」这条验收的参照物：
# profile/ 是照这个版本拷的。不记下来，以后 diff 失败时分不清是
# archiso 升级了，还是自己改坏了。

echo "==> 工具链检查"
for c in mkarchiso pacstrap arch-chroot mkinitcpio mksquashfs xorriso; do
  printf '    %-14s ' "$c"
  command -v "$c" >/dev/null 2>&1 && echo "OK" || { echo "缺失"; exit 1; }
done

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

  build_nspawn_args

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
