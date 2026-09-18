#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# check-identity · 品牌一致性检查（A6 改名的验收工具）
#
# 改名本身只是二十几处文本替换，真正的风险是**漏改**：ISO 里同时出现两种
# 品牌名，或者改了 profiledef.sh 却忘了引导菜单。这个脚本把「改干净了」
# 变成一条能跑的命令 —— 改名前后各跑一次，红 → 绿。
#
#   ./scripts/check-identity.sh                   # 扫 profile/（默认）
#   ./scripts/check-identity.sh --iso out/x.iso   # 扫产物
#
# 它只读，不改任何东西，**也不需要 root**：产物的卷标 / 发布者 / 应用名直接
# 从 ISO9660 的 PVD 里读，不经过 loop 设备。所以两台机器、任何人随时能复现。
#
# 两张清单，各有各的用途：
#
#   期望值   目标态在这里定义一次（MipLinux / miplinux / MIPLINUX_）。
#   豁免清单 命中但不该改的，每条都带理由。**它同时是「还没做」的清单**：
#            motd / hostname 属于线 C，pacman.conf 的注释属于上游，
#            ARCH_ 之外的那些 archiso 名字是内核参数与 hook 的契约。
#            豁免必须写理由 —— 没有理由的豁免就是把断言关掉。
#
# 为什么不用 git grep：工作区里可能有还没 add 的新文件，而漏改恰恰最容易
# 发生在新文件上。所以直接扫磁盘。
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${MIPL_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
PROFILE_DIR="${MIPL_PROFILE_DIR:-${REPO_ROOT}/profile}"

# ── 期望值 ────────────────────────────────────────────────────────────
EXPECT_BRAND="MipLinux"
EXPECT_NAME="miplinux"
EXPECT_LABEL_PREFIX="MIPLINUX_"
LABEL_MAX=32          # ISO9660 卷标上限；超了 xorriso 会截断，卷标就不是你以为的那个

# 「改对了」的样子：这些文件里必须出现 EXPECT_BRAND。
EXPECT_BRANDED=(
  profiledef.sh
  efiboot/loader/entries/01-archiso-linux.conf
  efiboot/loader/entries/02-archiso-speech-linux.conf
  syslinux/archiso_head.cfg
  syslinux/archiso_sys-linux.cfg
  syslinux/archiso_pxe-linux.cfg
  grub/grub.cfg
  grub/loopback.cfg
)

# ── 豁免清单 ──────────────────────────────────────────────────────────
# 格式：正则|理由。正则匹配「profile/路径:行号:内容」整行。
ALLOW_PROFILE=(
  '^profile/airootfs/etc/motd:|线 C 的文件：Live 开机第一眼可见，交接给 C，不在 A6 范围'
  '^profile/airootfs/usr/local/bin/choose-mirror:|线 B 的文件：Live 脚本里的注释'
  '^profile/pacman.conf:|上游注释文本 + pacman 的 Architecture 关键字，不是品牌'
  '^profile/PROFILE.md:|记录 releng 出处与 archiso 包元数据，是历史事实，不能改'
)
# 产物侧：ISO 未压缩区里的残留。
ALLOW_ISO=(
  '\.arch,[0-9]+,Arch Linux,|上游 systemd 包的 ELF 包元数据（.note.package），改名改不到'
)

# ── 输出 ──────────────────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  C_OK=$'\033[1;32m'; C_BAD=$'\033[1;31m'; C_WARN=$'\033[1;33m'
  C_INFO=$'\033[1;34m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_OK=''; C_BAD=''; C_WARN=''; C_INFO=''; C_DIM=''; C_OFF=''
fi

info() { printf '%s==>%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s[ok]%s %s\n' "$C_OK" "$C_OFF" "$*"; }
bad()  { printf '%s[!!]%s %s\n' "$C_BAD" "$C_OFF" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
note() { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_OFF"; }

FAILS=0
fail() { bad "$*"; FAILS=$(( FAILS + 1 )); }

usage() {
  cat <<'EOF'
用法：
  ./scripts/check-identity.sh [选项]

选项：
  --iso <文件>   检查构建出来的 ISO（PVD 卷标/发布者/应用名 + 未压缩区里的残留）
  -h, --help     显示本帮助。

不带参数就检查仓库里的 profile/。两种模式都不需要 root。

退出码：0 = 干净；1 = 有残留或有字段不对。
EOF
}

# ── 通用：按豁免清单过滤命中 ──────────────────────────────────────────
ALLOW=()
ALLOW_HITS=0

is_allowed() {
  local line="$1" rule
  # 必须加引号迭代：豁免规则里有空格（理由那半截），不引就会被词拆开
  if [[ ${#ALLOW[@]} -gt 0 ]]; then
    for rule in "${ALLOW[@]}"; do
      if [[ "$line" =~ ${rule%%|*} ]]; then
        ALLOW_HITS=$(( ALLOW_HITS + 1 ))
        return 0
      fi
    done
  fi
  return 1
}

# 豁免逐条打出来 —— 它是断言的一部分，也是「还没做」的清单，得让人看见
show_allow() {
  local rule
  info "豁免清单（命中但有意保留）"
  if [[ ${#ALLOW[@]} -eq 0 ]]; then
    note "  （空）"
    return 0
  fi
  for rule in "${ALLOW[@]}"; do
    note "  ${rule%%|*}  ← ${rule#*|}"
  done
}

report_hits() {
  # $1 = 标题；其余 = 待检查的命中行（可能为空）
  local title="$1"; shift
  local -a hits=("$@")
  local line
  if [[ ${#hits[@]} -eq 0 ]]; then
    return 0
  fi
  fail "${title}：${#hits[@]} 处"
  for line in "${hits[@]}"; do
    note "  ${line}"
  done
  return 0
}

# ── profile 模式 ──────────────────────────────────────────────────────
read_identity() {
  # 真的 source 一遍 profiledef.sh：iso_label / iso_version 里有 $(date …)，
  # 只有让它们展开，检查的才是构建时会拿到的那个值。
  #
  # declare -A file_permissions 不是多余的：profiledef.sh 里那张表写的是
  # ["/etc/shadow"]="0:0:400"。bash 只有在数组已声明成关联数组时，才把方括号
  # 里的东西当字符串键；否则会拿它做算术求值，直接报
  # 「/etc/shadow: 算术语法错误」。mkarchiso 也是先声明再 source 的。
  (
    # shellcheck disable=SC1091,SC2034
    declare -A file_permissions=()
    # shellcheck source=/dev/null
    source "${PROFILE_DIR}/profiledef.sh"
    printf '%s\n' \
      "${iso_name-}" "${iso_label-}" "${iso_publisher-}" \
      "${iso_application-}" "${iso_version-}"
  )
}

check_profiledef() {
  local -a id=()
  mapfile -t id < <(read_identity)
  local name="${id[0]:-}" label="${id[1]:-}" pub="${id[2]:-}" app="${id[3]:-}" ver="${id[4]:-}"

  info "身份变量（source profile/profiledef.sh 得到的实际值）"
  note "iso_name        = ${name}"
  note "iso_label       = ${label}"
  note "iso_publisher   = ${pub}"
  note "iso_application = ${app}"
  note "iso_version     = ${ver}"

  if [[ "$name" == "$EXPECT_NAME" ]]; then
    ok "iso_name 是 ${EXPECT_NAME}"
  else
    fail "iso_name 应为 ${EXPECT_NAME}，实际：${name:-（空）}"
  fi

  if [[ "$label" == "${EXPECT_LABEL_PREFIX}"* ]]; then
    ok "iso_label 以 ${EXPECT_LABEL_PREFIX} 开头"
  else
    fail "iso_label 应以 ${EXPECT_LABEL_PREFIX} 开头，实际：${label:-（空）}"
  fi
  if [[ -n "$label" && ! "$label" =~ ^[A-Z0-9_]+$ ]]; then
    fail "iso_label 含非法字符（ISO9660 卷标只允许 A-Z 0-9 _）：${label}"
  fi
  if (( ${#label} > LABEL_MAX )); then
    fail "iso_label 超过 ${LABEL_MAX} 字符，会被截断：${label}"
  fi

  local field
  for field in pub app; do
    local val; [[ "$field" == pub ]] && val="$pub" || val="$app"
    if [[ "$val" =~ [Aa][Rr][Cc][Hh] ]]; then
      fail "iso_$([[ $field == pub ]] && echo publisher || echo application) 里还有 arch：${val}"
    else
      ok "iso_$([[ $field == pub ]] && echo publisher || echo application) 不含 arch"
    fi
  done

  [[ "$ver" == "$(date +%Y.%m.%d)" ]] \
    || warn "iso_version 不是今天（SOURCE_DATE_EPOCH 可能来自旧的工作目录，见坑 1）：${ver}"
}

check_branded() {
  local f missing=()
  for f in "${EXPECT_BRANDED[@]}"; do
    if grep -qF -- "$EXPECT_BRAND" "${PROFILE_DIR}/${f}" 2>/dev/null; then
      continue
    fi
    missing+=("$f")
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    ok "该出现 ${EXPECT_BRAND} 的 ${#EXPECT_BRANDED[@]} 个文件都出现了"
  else
    fail "这些文件里没找到 ${EXPECT_BRAND}：${missing[*]}"
  fi
}

check_profile_residue() {
  local -a hits=() lines=()
  local line

  # 品牌文本（忽略大小写）+ 旧卷标前缀（区分大小写：%ARCH% 不带下划线，不会误伤）
  mapfile -t lines < <(
    {
      grep -rnI -i -- "arch linux" "$PROFILE_DIR" 2>/dev/null || true
      grep -rnI -- "ARCH_" "$PROFILE_DIR" 2>/dev/null || true
    } | sed "s|^${REPO_ROOT}/||" | sort -u -t: -k1,1 -k2,2n
  )

  for line in ${lines[@]+"${lines[@]}"}; do
    is_allowed "$line" || hits+=("$line")
  done

  if [[ ${#hits[@]} -eq 0 ]]; then
    ok "profile/ 里没有残留的品牌文本（豁免 ${ALLOW_HITS} 处，逐条有理由）"
  else
    report_hits "profile/ 里还有没改干净的品牌文本" "${hits[@]}"
    note "  改干净，或把它加进脚本顶部的豁免清单并写明理由。"
  fi

  show_allow
}

# ── 产物模式 ──────────────────────────────────────────────────────────
pvd_field() {
  # $1 = ISO；$2 = PVD 内偏移；$3 = 长度（默认 128）
  dd if="$1" bs=1 skip=$(( 32768 + $2 )) count="${3:-128}" 2>/dev/null \
    | tr -d '\0' | sed -e 's/[[:space:]]*$//'
}

check_iso() {
  local iso="$1"
  [[ -f "$iso" ]] || { bad "ISO 不存在：${iso}"; exit 1; }

  info "检查产物 $(basename "$iso")"
  local label pub app
  label="$(pvd_field "$iso" 40 32)"
  pub="$(pvd_field "$iso" 318)"
  app="$(pvd_field "$iso" 574)"
  note "卷标        = ${label}"
  note "publisher   = ${pub}"
  note "application = ${app}"

  if [[ "$label" == "${EXPECT_LABEL_PREFIX}"* ]]; then
    ok "卷标以 ${EXPECT_LABEL_PREFIX} 开头"
  else
    fail "卷标应为 ${EXPECT_LABEL_PREFIX}…，实际：${label:-（读不到）}"
  fi

  # 产物文件名是 iso_name 唯一能被看见的地方（PVD 里没有它）——
  # 验收标准写的就是「改名后产物叫 miplinux-*.iso」，所以在这里断言。
  local base; base="$(basename "$iso")"
  if [[ "$base" == "${EXPECT_NAME}-"*.iso ]]; then
    ok "产物名是 ${EXPECT_NAME}-*.iso"
  else
    fail "产物名应以 ${EXPECT_NAME}- 开头、.iso 结尾，实际：${base}"
  fi

  local v
  for v in "$pub" "$app"; do
    if [[ "$v" =~ [Aa][Rr][Cc][Hh] ]]; then
      fail "ISO 元数据里还有 arch：${v}"
    fi
  done
  [[ "$pub" =~ [Aa][Rr][Cc][Hh] || "$app" =~ [Aa][Rr][Cc][Hh] ]] \
    || ok "publisher / application 里不含 arch"

  # 未压缩区（引导配置、EFI 镜像、PVD）里的残留。squashfs 是压缩的，
  # 里面的东西看不见 —— 所以这里查的是「用户能直接看到的那一层」。
  local -a hits=() lines=()
  local line
  mapfile -t lines < <(
    {
      strings -a -- "$iso" | grep -i -- "arch linux" || true
      strings -a -- "$iso" | grep -- "ARCH_" || true
    } | sort -u
  )
  for line in ${lines[@]+"${lines[@]}"}; do
    is_allowed "$line" || hits+=("$line")
  done

  if [[ ${#hits[@]} -eq 0 ]]; then
    ok "未压缩区里没有残留的品牌文本（豁免 ${ALLOW_HITS} 处）"
  else
    report_hits "ISO 未压缩区里还有旧品牌" "${hits[@]}"
  fi

  show_allow
}

# ── 主流程 ────────────────────────────────────────────────────────────
MODE="profile"
ISO_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iso)
      [[ -n "${2:-}" ]] || { bad "--iso 后面要跟 ISO 文件"; exit 1; }
      MODE="iso"; ISO_FILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) bad "未知参数：$1（用 --help 看用法）"; exit 1 ;;
  esac
done

if [[ "$MODE" == "profile" ]]; then
  [[ -f "${PROFILE_DIR}/profiledef.sh" ]] \
    || { bad "找不到 ${PROFILE_DIR}/profiledef.sh（用 MIPL_PROFILE_DIR 指定别的 profile）"; exit 1; }
  ALLOW=("${ALLOW_PROFILE[@]}")
  printf '%s品牌一致性检查 · profile%s\n' "$C_INFO" "$C_OFF"
  note "profile：${PROFILE_DIR}"
  check_profiledef
  check_branded
  check_profile_residue
else
  ALLOW=("${ALLOW_ISO[@]}")
  printf '%s品牌一致性检查 · 产物%s\n' "$C_INFO" "$C_OFF"
  check_iso "$ISO_FILE"
fi

echo
if [[ $FAILS -eq 0 ]]; then
  ok "干净：没有发现旧品牌残留（$([[ $MODE == profile ]] && echo 'profile' || echo 'ISO')）"
  exit 0
fi
bad "发现 ${FAILS} 项问题 —— 改干净之前不要构建，否则产出的是半改名的 ISO"
exit 1
