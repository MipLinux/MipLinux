#!/usr/bin/env bash
# 把项目仓库 README 的进度表同步到组织主页的进度表：逐行对齐 + 规范链接形态。
#
# 为什么有它：组织主页的进度表刻意与真源**逐行同形**（见 check-doc-sync.sh 的口径说明），
# 于是「同步」不该是手抄 —— 手抄一遍就会漏一格，2026-09-26 那次漏的正是安装器那一行。
# 本项目反对手抄（Issue #7 / #8 / #32 都是抄出来的），进度表同理。
#
# 每次同步做两件事，规则都在 mipl-doc-sync-lib.sh 里定义一次（守卫用同一份规则比对）：
#   1. 逐格做规范变换：仓库内相对链接 → 指向项目仓库的绝对链接（组织主页里相对路径会 404），
#      `见 [Issue #23](…)` 统一成 `（Issue #23）`。**措辞一个字不改** —— 只改链接形态。
#   2. 把组织主页里 `<!-- BEGIN:progress-table --> … <!-- END:progress-table -->` 之间换成新表；
#      没有标记时退回「按第一张 `| 阶段 |` 表整块替换」，兼容旧版式。
#
# 脚本只动这一块，其余一个字不碰；改前备份，写完自己跑一遍 check-doc-sync.sh，不通过就回滚 ——
# 同步脚本不允许留下「改坏了还不知道」的状态。
#
# **不需要 root**，不需要网络。用法：
#   ./scripts/sync-profile-progress.sh --dry-run     # 只看会改成什么，不落盘
#   ./scripts/sync-profile-progress.sh               # 真改（只在两边不一致时才写）
#   ./scripts/sync-profile-progress.sh --org /path
#
# 退出码：0 = 已一致或同步成功且校验通过；1 = 出错（已回滚）或校验不过。

set -euo pipefail

# 一切路径从脚本自身位置推导，不含 $HOME、不写死目录（两台机器的仓库路径不同，见 Issue #7）。
SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)
# shellcheck source=mipl-doc-sync-lib.sh
. "$SELF_DIR/mipl-doc-sync-lib.sh"

ORG_ROOT="${MIPL_ORG_REPO:-}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --org) [ $# -ge 2 ] || { echo "错误：--org 需要一个路径" >&2; exit 1; }; ORG_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "错误：不认识参数 $1（见 --help）" >&2; exit 1 ;;
  esac
done

if [ -z "$ORG_ROOT" ]; then
  if [ -d "$PROJECT_ROOT/../.github/profile" ]; then
    ORG_ROOT=$(cd -- "$PROJECT_ROOT/.." && pwd)/.github
  else
    echo "错误：找不到并列的 .github 仓库；用 --org <路径> 指定。" >&2
    exit 1
  fi
fi

PROJECT_README="$PROJECT_ROOT/README.md"
ORG_README="$ORG_ROOT/profile/README.md"
[ -f "$PROJECT_README" ] || { echo "错误：读不到 $PROJECT_README" >&2; exit 1; }
[ -f "$ORG_README" ]     || { echo "错误：读不到 $ORG_README" >&2; exit 1; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

extract_progress_block "$PROJECT_README" >"$TMP/source.md"
extract_progress_block "$ORG_README" >"$TMP/target.md"
[ -s "$TMP/source.md" ] || { echo "错误：项目 README 里找不到进度表" >&2; exit 1; }
[ -s "$TMP/target.md" ] || { echo "错误：组织主页里找不到进度表" >&2; exit 1; }

# 逐行做规范变换：表头/分隔行原样，数据行的状态列过 canonical_cell。
{
  while IFS= read -r line; do
    case "$line" in
      '| 阶段 |'*|'|---|---|'*) printf '%s\n' "$line" ;;
      '|'*)
        # 字段按 `|` 切：f1 空（行首）、f2 阶段名、f3 起是状态列及其后字段。
        # 用 cut 而不是 shell 前缀剥离 —— 前缀剥离会在阶段名这格上多切一刀。
        name=$(printf '%s' "$line" | cut -d'|' -f2)
        rest=$(printf '%s' "$line" | cut -d'|' -f3-)
        printf '|%s|%s\n' "$name" "$(printf '%s' "$rest" | canonical_cell)"
        ;;
      *) printf '%s\n' "$line" ;;
    esac
  done <"$TMP/source.md"
} >"$TMP/new.md"

if cmp -s "$TMP/new.md" "$TMP/target.md"; then
  echo "组织主页的进度表已经与项目 README 一致，无需改动。"
  exit 0
fi

echo "── 将要写入组织主页的进度表（差异）"
diff -u "$TMP/target.md" "$TMP/new.md" || true
echo

if [ "$DRY_RUN" -eq 1 ]; then
  echo "（--dry-run：没有写盘）"
  exit 0
fi

cp "$ORG_README" "$TMP/org-backup.md"
awk -v newfile="$TMP/new.md" '
  BEGIN { while ((getline l < newfile) > 0) new[++n] = l }
  /<!--[[:space:]]*BEGIN:progress-table[[:space:]]*-->/ && !done {
    print
    for (i = 1; i <= n; i++) print new[i]
    intable = 1; done = 1; next
  }
  intable && /<!--[[:space:]]*END:progress-table[[:space:]]*-->/ { print; intable = 0; next }
  intable { next }
  { intable = 0; print }
' "$TMP/org-backup.md" >"$TMP/org-new.md"

# 没走标记路径（旧版式：没有 BEGIN 标记）时，用「第一张 `| 阶段 |` 表」整块替换。
if ! grep -q 'BEGIN:progress-table' "$TMP/org-new.md"; then
  awk -v newfile="$TMP/new.md" '
    BEGIN { while ((getline l < newfile) > 0) new[++n] = l }
    /^\|[[:space:]]*阶段[[:space:]]*\|/ && !done {
      for (i = 1; i <= n; i++) print new[i]
      intable = 1; done = 1; next
    }
    intable && /^\|/ { next }
    { intable = 0; print }
  ' "$TMP/org-backup.md" >"$TMP/org-new.md"
fi

if ! grep -q '^| 阶段 | 状态 |' "$TMP/org-new.md"; then
  echo "错误：替换后的文件里找不到进度表，放弃写入（未改动原文件）。" >&2
  exit 1
fi
cp "$TMP/org-new.md" "$ORG_README"
echo "已写入 $ORG_README"

# 写回后自己校验：同步脚本不允许产生「校验不过」的状态。不过就回滚，绝不留半成品。
if "$SELF_DIR/check-doc-sync.sh" --org "$ORG_ROOT" >"$TMP/verify.log" 2>&1; then
  echo "校验通过：$(tail -1 "$TMP/verify.log")"
  exit 0
fi

cp "$TMP/org-backup.md" "$ORG_README"
echo "错误：同步后 check-doc-sync.sh 仍报漂移，已回滚 $ORG_README。它说：" >&2
grep '^❌' "$TMP/verify.log" >&2 || true
exit 1
