#!/usr/bin/env bash
# 文档同步守卫：项目仓库 README 的进度口径，与 MipLinux/.github 组织主页的摘要是否还一致。
#
# 为什么有它：同一件事在两个仓库各存一份，就会漂 —— 2026-09-26 项目侧把「安装器 M2 已接入
# 真实后端并验收通过」写进 README，组织主页晚了整轮还在说「前端未接后端、ISO 待重建」。
# 这个脚本把「两边不许再漂」变成一条可执行的断言，供定时任务每日跑一次。
#
# 口径（谁是唯一真源）：项目仓库 MipLinux/README.md 的进度表。
#   组织主页是面向外人的摘要，不是第二份真相；不一致时改组织主页，不改项目侧去迁就它。
#   组织主页的进度表刻意与真源**逐行同形**（同阶段名、同状态），所以这里整格逐字比 ——
#   只比关键短句不够：那样两边的表可以同名不同义，漂了也看不出来。
#   两边唯一的合法差异是链接形态（主页是另一个仓库，相对链接会 404），规则在
#   mipl-doc-sync-lib.sh 里定义一次，同步脚本与守卫共用，谁也不自己实现第二遍。
#
# 还需人工维护的只有 check-doc-sync.facts 里的 stale 断言（已被推翻、不许再写回去的旧口径）。
#
# **不需要 root**，只读，不做任何改动，不新增依赖（只用 bash + coreutils + git）。
#
# 用法：
#   ./scripts/check-doc-sync.sh                 # 自动找同级的 .github 仓库
#   ./scripts/check-doc-sync.sh --org /path     # 显式指定 .github 仓库路径
#   MIPL_ORG_REPO=/path ./scripts/check-doc-sync.sh
#
# 退出码：0 = 一致；1 = 发现漂移或用法错误。

set -euo pipefail

# 一切路径从脚本自身位置推导，不含 $HOME、不写死目录（两台机器的仓库路径不同，见 Issue #7）。
# 软链场景只用 ${BASH_SOURCE[0]}，不写 $(dirname "$0")：脚本可能被软链到 ~/.local/bin。
SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)
FACTS_FILE="$SELF_DIR/check-doc-sync.facts"
# shellcheck source=mipl-doc-sync-lib.sh
. "$SELF_DIR/mipl-doc-sync-lib.sh"

ORG_ROOT="${MIPL_ORG_REPO:-}"

usage() { sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --org)
      [ $# -ge 2 ] || { echo "错误：--org 需要一个路径" >&2; exit 1; }
      ORG_ROOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
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

problems=0
fail() { printf '❌ %s\n' "$1"; problems=$((problems + 1)); }
ok()   { printf '✅ %s\n' "$1"; }
note() { printf '   %s\n' "$1"; }

[ -f "$PROJECT_README" ] || { echo "错误：读不到 $PROJECT_README" >&2; exit 1; }
[ -f "$ORG_README" ]     || { echo "错误：读不到 $ORG_README" >&2; exit 1; }
[ -f "$FACTS_FILE" ]     || { echo "错误：读不到断言清单 $FACTS_FILE" >&2; exit 1; }

echo "项目仓库真源：$PROJECT_README"
echo "组织主页摘要：$ORG_README"
echo

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ── 1. 进度表逐行整格比对（唯一合法差异是链接形态，过 canonical_cell）
echo "── 进度口径：项目 README 的每一行 vs 组织主页"
extract_progress_table "$PROJECT_README" >"$TMP/project.tsv"
extract_progress_table "$ORG_README" >"$TMP/org.tsv"

if [ ! -s "$TMP/project.tsv" ]; then
  fail "项目 README 里没找到进度表（应带 <!-- BEGIN:progress-table --> 标记，或一张以「| 阶段 |」开头的表）"
fi
if [ ! -s "$TMP/org.tsv" ]; then
  fail "组织主页里没找到进度表（同上）"
fi

project_rows=0
while IFS=$'\t' read -r name status; do
  [ -n "$name" ] || continue
  project_rows=$((project_rows + 1))
  org_status=$(awk -F'\t' -v n="$name" '$1 == n { print $2; exit }' "$TMP/org.tsv")
  if [ -z "$org_status" ]; then
    fail "组织主页缺少「$name」这一行（项目侧有）"
    continue
  fi
  want=$(printf '%s' "$status" | canonical_cell | normalize_cell)
  have=$(printf '%s' "$org_status" | normalize_cell)
  if [ "$want" = "$have" ]; then
    ok "$name"
  else
    # 差异定位到第一个不同的字符，省得让人在两行长文里肉眼找。
    pos=$(awk -v a="$want" -v b="$have" 'BEGIN {
      n = (length(a) < length(b)) ? length(a) : length(b)
      for (i = 1; i <= n; i++) if (substr(a, i, 1) != substr(b, i, 1)) { print i; exit }
      print n + 1
    }')
    from=$((pos > 40 ? pos - 40 : 1))
    fail "「$name」状态两边不一致 —— 以项目 README 为准改组织主页"
    note "首个差异在第 $pos 个有效字符附近"
    note "项目（规范后）：$(printf '%s' "$want" | cut -c"$from-$((pos + 60))")"
    note "主页（规范后）：$(printf '%s' "$have" | cut -c"$from-$((pos + 60))")"
  fi
done <"$TMP/project.tsv"

if [ "$project_rows" -eq 0 ]; then
  fail "项目 README 的进度表是空的，没有一个阶段可比"
fi

# 清单里没写、主页自己加的阶段行：不一定是错，但必须有人知道它存在。
while IFS=$'\t' read -r name _; do
  [ -n "$name" ] || continue
  if ! awk -F'\t' -v n="$name" '$1 == n { found = 1 } END { exit !found }' "$TMP/project.tsv"; then
    fail "组织主页多出项目侧没有的阶段「$name」—— 要么删掉，要么补进项目 README 的进度表"
  fi
done <"$TMP/org.tsv"
echo

# ── 2. 组织主页不得残留的旧口径
echo "── 组织主页不得残留的旧口径"
stale_facts=0
while IFS='|' read -r kind text; do
  case "$kind" in ''|'#'*) continue ;; esac
  [ "$kind" = "stale" ] || continue
  [ -n "$text" ] || continue
  stale_facts=$((stale_facts + 1))
  if grep -qF -- "$text" "$ORG_README"; then
    fail "组织主页里还写着已被推翻的口径：「$text」"
  fi
done <"$FACTS_FILE"
if [ "$stale_facts" -gt 0 ]; then ok "清单点名的 $stale_facts 条旧口径都没有残留"; fi
echo

# ── 3. 组织级共享文件在项目仓库里的副本
echo "── 共享文件副本：MipLinux/.github ← 组织级 .github"
shared=(
  "ISSUE_TEMPLATE/bug-report.yml"
  "ISSUE_TEMPLATE/documentation.yml"
  "ISSUE_TEMPLATE/feature-request.yml"
  "ISSUE_TEMPLATE/task.yml"
  "ISSUE_TEMPLATE/config.yml"
)
for rel in "${shared[@]}"; do
  o="$ORG_ROOT/$rel"
  p="$PROJECT_ROOT/.github/$rel"
  if [ ! -f "$o" ]; then fail "组织级缺少 $rel"; continue; fi
  if [ ! -f "$p" ]; then
    fail "项目仓库缺少副本 .github/$rel（组织级模板在本仓库实测不生效，副本必须有）"
    continue
  fi
  # 副本头 3 行是「这是副本、改请先改组织级」的说明，允许存在，不参与比较。
  if diff -q <(tail -n +4 "$p") "$o" >/dev/null; then
    ok "$rel 副本一致"
  else
    fail "$rel 两边内容不一致 —— 先改组织级，再同步副本"
    diff <(tail -n +4 "$p") "$o" | head -20 | sed 's/^/     /'
  fi
done
echo

# ── 4. 真源自己的新鲜度：进度表的「截至」日期不能落后于仓库最后一次提交
echo "── 项目 README 的新鲜度"
stamp=$(grep -oE '截至 \*\*[0-9]{4}-[0-9]{2}-[0-9]{2}\*\*' "$PROJECT_README" | head -1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || true)
if [ -z "$stamp" ]; then
  fail "项目 README 的进度表里找不到「截至 **YYYY-MM-DD**」"
else
  last=$(git -C "$PROJECT_ROOT" log -1 --format=%cs 2>/dev/null || true)
  if [ -z "$last" ]; then
    note "读不到 $PROJECT_ROOT 的提交时间，跳过新鲜度比较（进度表截至 $stamp）"
  elif [ "$stamp" \< "$last" ]; then
    fail "进度表停在 $stamp，而仓库已有 $last 的提交 —— 有新进展没写进进度表（先更新真源，再同步主页）"
  else
    ok "进度表截至 $stamp（仓库最后一次提交 $last）"
  fi
fi
echo

if [ "$problems" -eq 0 ]; then
  echo "结论：进度口径一致、旧口径没有残留、共享文件副本一致。"
  exit 0
fi

printf '结论：发现 %d 处漂移。改组织主页去对齐项目 README，不要反过来改项目 README 迁就摘要。\n' "$problems"
exit 1
