#!/usr/bin/env bash
# 工作 issue 草案守卫：`out/issue-drafts/*.md` 里的草案是否符合 docs/work/README.md 的「工作 issue 规范」。
#
# 为什么有它：规范写在文档里没人执行，就会像旧版当日文档那样各写各的 —— 实现范围含糊、验收写成
# 「跑起来了」。分工的载体从当日文档换成 issue 之后，**能在本地拦住的只剩草案阶段**：
# issue 一旦发出去就是 GitHub 上的数据，仓库里没有副本，本地没有任何东西可查（见规范「守卫查到哪、查不到哪」）。
#
# 还查一件本地能查的事：**骨架与表单不许漂移**。`docs/work/TEMPLATE.md` 的 `### 字段` 与
# `.github/ISSUE_TEMPLATE/task.yml` 的 `label:` 必须逐字同序 —— 两份都是人写的，只靠自觉必然漂。
#
# **不需要 root**，只读，不联网。
# 用法：
#   ./scripts/check-work-issue.sh                       # 查 out/issue-drafts/ 里的全部草案 + 骨架/表单比对
#   ./scripts/check-work-issue.sh out/issue-drafts/x.md # 只查指定草案（骨架/表单比对照跑）
# 退出码：0 = 全部合规；1 = 有不合规项。

set -euo pipefail

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)
# 三个路径可以用环境变量顶掉：回归测试（check-work-issue.test.sh）拿临时副本验「漂移抓不抓得住」，
# 不碰仓库里的真文件 —— 守卫自己也得被测，不然它只是个没验过的假设。
DRAFT_DIR=${MIPL_WORK_DRAFTS:-$PROJECT_ROOT/out/issue-drafts}
TEMPLATE=${MIPL_WORK_TEMPLATE:-$PROJECT_ROOT/docs/work/TEMPLATE.md}
FORM=${MIPL_WORK_FORM:-$PROJECT_ROOT/.github/ISSUE_TEMPLATE/task.yml}

# 字段清单与顺序：规范里「表单里每个字段的来历」那张表就是这几个，改哪儿都要一起改。
FIELDS=(目标 实现 验收 回报 依赖)
# 草案行数上限：一个 issue 只留目标/实现/验收/回报/依赖，过程和实测输出进 docs/work/tech/。
MAX_LINES=60
problems=0
fail() { printf '❌ %s\n' "$1"; problems=$((problems + 1)); }
ok()   { printf '✅ %s\n' "$1"; }
note() { printf '   %s\n' "$1"; }

# 取「### <字段>」小节下的内容（到下一个 `### ` 或文件末尾为止）。
section() { # $1=文件 $2=字段
  awk -v want="$2" '
    $0 == "### " want { inside = 1; next }
    /^### / { inside = 0 }
    inside { print }
  ' "$1"
}

# 非空（去掉空白行后至少还有一行）。
nonempty() { [ -n "$(printf '%s' "$1" | tr -d '[:space:]')" ]; }

check_draft() { # $1=草案文件
  local f="$1" rel
  case "$f" in
    "$PROJECT_ROOT"/*) rel=${f#"$PROJECT_ROOT"/} ;;
    *) rel=$f ;;
  esac
  echo "── $rel"

  # 0. 空文件
  if ! nonempty "$(cat "$f")"; then
    fail "$rel 是空的"
    return
  fi

  # 1. issue 正文不是仓库文档：不许带 YAML frontmatter 或 HTML 注释（照抄 TEMPLATE.md 最容易犯）
  if [ "$(head -1 "$f")" = "---" ]; then
    fail "$rel 首行是 ---（YAML frontmatter）—— 那是仓库文档的东西，抄进 issue 正文会在 GitHub 上原样渲染"
  fi
  if grep -q '<!--' "$f"; then
    fail "$rel 含 HTML 注释 —— 抄模板时把用法说明一起抄进来了，issue 正文里要删掉"
  fi

  # 2. 字段齐备且顺序固定（骨架与表单都是这个顺序）
  local want_seq got_seq n_got
  want_seq=$(printf '%s\n' "${FIELDS[@]}")
  got_seq=$(grep -oE '^### .+$' "$f" | sed 's/^### //' || true)
  n_got=$(printf '%s\n' "$got_seq" | grep -c . || true)
  if [ "$got_seq" = "$want_seq" ]; then
    ok "字段齐备且顺序正确（${#FIELDS[@]} 个）"
  else
    fail "$rel 的字段与规范不符 —— 应为「${FIELDS[*]}」各一次、顺序不变，实际是「$(printf '%s ' $got_seq)」（共 $n_got 个 ### 小节）"
  fi

  # 3. 实现：必须写出文件路径，否则所有权切不开
  if section "$f" 实现 | grep -qE '(^|[^[:alnum:]_])(scripts|docs|installer|profile|\.github|out)/'; then
    ok "实现里写了文件路径"
  else
    fail "$rel 的「实现」里没有一条文件路径 —— 所有权按文件切，路径写出来才拦得住撞车"
  fi

  # 4. 验收：命令 + 期望结果
  local accept
  accept=$(section "$f" 验收)
  if printf '%s' "$accept" | grep -q '`' && printf '%s' "$accept" | grep -qE '期望|→'; then
    ok "验收含命令与期望结果"
  else
    fail "$rel 的「验收」要写成命令 + 期望结果（含反引号包住的命令，并写出期望）——「跑起来了」不是判据"
  fi

  # 5. 其余字段不许空（依赖没有就写「无」）
  local field
  for field in 回报 依赖; do
    nonempty "$(section "$f" "$field")" || fail "$rel 的「$field」是空的"
  done

  # 6. AI 起草声明与开工命令（草案是人发给维护者过目的，读者有权知道来源）
  grep -q 'AI 起草' "$f" || fail "$rel 缺「本 issue 由 AI 起草」声明"
  grep -q 'git switch main' "$f" || fail "$rel 缺「开工前请执行」里的 git switch main"

  # 7. 行数
  local lines
  lines=$(wc -l <"$f")
  if [ "$lines" -gt "$MAX_LINES" ]; then
    fail "$rel 有 $lines 行，超过 $MAX_LINES 行上限 —— 过程和实测输出请进 docs/work/tech/ 或 archive/"
  else
    ok "$lines 行（上限 $MAX_LINES）"
  fi
}

# 骨架（TEMPLATE.md）与表单（task.yml）的字段必须逐字同序。
check_templates() {
  echo "── 骨架 ↔ 表单"
  local skeleton labels
  skeleton=$(grep -oE '^### .+$' "$TEMPLATE" | sed 's/^### //' || true)
  # 表单里只有 textarea / input / dropdown 带 label；type: markdown 的说明块没有 label。
  labels=$(grep -oE '^[[:space:]]*label: .+$' "$FORM" | sed 's/^[[:space:]]*label: //' || true)

  local want_seq
  want_seq=$(printf '%s\n' "${FIELDS[@]}")
  if [ "$skeleton" = "$want_seq" ]; then
    ok "TEMPLATE.md 的字段与规范一致"
  else
    fail "TEMPLATE.md 的字段应为「${FIELDS[*]}」，实际是「$(printf '%s ' $skeleton)」"
  fi
  if [ "$labels" = "$want_seq" ]; then
    ok "task.yml 的字段与规范一致"
  else
    fail "task.yml 的 label 应为「${FIELDS[*]}」，实际是「$(printf '%s ' $labels)」—— 骨架改了表单没改？"
  fi

  grep -q '^title: "\[工作\] "' "$FORM" || fail "task.yml 的标题前缀不是「[工作] 」"
  grep -q '^labels: \["task"\]' "$FORM" || fail "task.yml 没有 labels: [\"task\"]（工作 issue 靠这个标签筛）"
  [ "$(grep -c 'required: true' "$FORM" || true)" -eq "${#FIELDS[@]}" ] \
    || fail "task.yml 的必填字段数不等于 ${#FIELDS[@]} —— 每个字段都要 required: true"
}

echo "── 草案目录：${DRAFT_DIR#"$PROJECT_ROOT"/}"
if [ $# -gt 0 ]; then
  for f in "$@"; do
    [ -f "$f" ] || { echo "错误：读不到 $f" >&2; exit 1; }
    check_draft "$(cd -- "$(dirname -- "$f")" && pwd)/$(basename -- "$f")"
  done
elif [ -d "$DRAFT_DIR" ]; then
  found=0
  for f in "$DRAFT_DIR"/*.md; do
    [ -e "$f" ] || continue
    found=$((found + 1))
    check_draft "$f"
  done
  [ "$found" -gt 0 ] || note "没有草案（out/issue-drafts/ 是空的）—— 只比对骨架与表单"
else
  note "没有草案目录（$DRAFT_DIR 不存在，out/ 是构建产物区）—— 只比对骨架与表单"
fi
echo

for t in "$TEMPLATE" "$FORM"; do
  [ -f "$t" ] || { echo "错误：读不到 $t" >&2; exit 1; }
done
check_templates

echo
if [ "$problems" -eq 0 ]; then
  echo "结论：草案符合规范，骨架与表单没有漂移。"
  exit 0
fi
printf '结论：发现 %d 处不合规。规范见 docs/work/README.md 的「工作 issue 规范」。\n' "$problems"
exit 1
