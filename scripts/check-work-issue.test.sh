#!/usr/bin/env bash
# check-work-issue.sh 的回归测试：造一份草案夹具，把「不合规」与「骨架/表单漂移」逐个塞进去，看它抓不抓得住。
#
# 为什么有它：一个「永远说 OK」的守卫比没有守卫更坏 —— 它会让人以为草案是自动合规的。
# 所以守卫本身也要有实测证据：基线必须通过，每一种不合规必须被抓到并点名。
# 夹具全部在临时目录里，通过 MIPL_WORK_* 环境变量喂给守卫，**不碰真实仓库**。
#
# **不需要 root**。用法：./scripts/check-work-issue.test.sh
# 退出码：0 = 全过；1 = 有失败项。

set -uo pipefail

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)
GUARD="$SELF_DIR/check-work-issue.sh"
TEMPLATE_SRC="$PROJECT_ROOT/docs/work/TEMPLATE.md"
FORM_SRC="$PROJECT_ROOT/.github/ISSUE_TEMPLATE/task.yml"

FAIL=0
pass() { printf '✅ %s\n' "$1"; }
bad()  { printf '❌ %s\n' "$1"; FAIL=1; }

[ -x "$GUARD" ] || { echo "错误：$GUARD 不可执行" >&2; exit 1; }
[ -f "$TEMPLATE_SRC" ] || { echo "错误：读不到 $TEMPLATE_SRC" >&2; exit 1; }
[ -f "$FORM_SRC" ] || { echo "错误：读不到 $FORM_SRC" >&2; exit 1; }

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/drafts"

# 一份合规草案（照 TEMPLATE.md 的骨架写）。夹具**不依赖规范的具体措辞**，
# 只依赖机制：字段小节、受理人角色、验收里的命令与期望、行数上限。
write_good_draft() {
  cat >"$T/good.md" <<'DRAFT'
### 受理人

维护者

### 目标

让分工的载体从当日文档换成 issue —— 一条工作一个 issue，assignee 就是受理人。

### 实现

- 改 `docs/work/TEMPLATE.md`（骨架）、`docs/work/README.md`（规范）、`scripts/check-work-issue.sh`（守卫）；
- 不碰 `scripts/mipl.sh`。

### 验收

`./scripts/check-work-issue.sh` → 期望退出码 0，且输出「结论：草案符合规范」。

### 回报

把守卫的完整输出贴在 issue 下，@ 维护者过目。

### 依赖

无

---

**开工前请执行：**

```bash
git switch main && git pull origin main
git switch -c docs/<主题>
```

> 🤔 本 issue 由 AI 起草，不同发行版可能有差异，AI 可能出错；如有错误，请直接在本 issue 下回复。
DRAFT
}

# 每个用例从干净状态出发：草案复制自 $T/good.md，骨架与表单复制自真实仓库。
reset_fixture() {
  cp "$T/good.md" "$T/drafts/case.md"
  cp "$TEMPLATE_SRC" "$T/TEMPLATE.md"
  cp "$FORM_SRC" "$T/task.yml"
}

# 跑守卫（只查 case.md），断言退出码与输出里点名的内容。
expect() { # $1=名字 $2=期望退出码 $3=输出里必须出现的片段
  local name="$1" want="$2" pat="$3" out rc
  out=$(MIPL_WORK_DRAFTS="$T/drafts" MIPL_WORK_TEMPLATE="$T/TEMPLATE.md" MIPL_WORK_FORM="$T/task.yml" \
        "$GUARD" "$T/drafts/case.md" 2>&1) && rc=0 || rc=$?
  if [ "$rc" -ne "$want" ]; then
    bad "$name（退出码 $rc，期望 $want）"
    printf '%s\n' "$out" | sed 's/^/     /'
    return
  fi
  if [ -n "$pat" ] && ! printf '%s' "$out" | grep -qF -- "$pat"; then
    bad "$name（输出里没有点出「$pat」）"
    printf '%s\n' "$out" | sed 's/^/     /'
    return
  fi
  pass "$name"
}

echo "── 守卫：$GUARD"
echo

write_good_draft
reset_fixture
echo "── T1 基线：合规草案必须判为通过"
expect "T1 合规草案通过" 0 "结论：草案符合规范"
echo

echo "── T2 缺字段（删掉「回报」小节）"
reset_fixture
awk 'BEGIN{skip=0} /^### 回报$/{skip=1; next} /^### /{skip=0} !skip{print}' "$T/drafts/case.md" >"$T/x" && mv "$T/x" "$T/drafts/case.md"
expect "T2 抓到字段缺失" 1 "字段与规范不符"
echo

echo "── T3 受理人写人名（不许写 handle）"
reset_fixture
sed -i 's/^维护者$/LaT-SKY/' "$T/drafts/case.md"
expect "T3 抓到受理人写人名" 1 "人名"
echo

echo "── T4 验收写成「跑起来了」"
reset_fixture
awk 'BEGIN{skip=0} /^### 验收$/{print; skip=1; next} /^### /{skip=0} skip&&!done{print "界面能起来，跑一次就成。"; done=1; next} !skip{print}' \
  "$T/drafts/case.md" >"$T/x" && mv "$T/x" "$T/drafts/case.md"
expect "T4 抓到验收没有命令与期望" 1 "命令 + 期望结果"
echo

echo "── T5 超行数（把过程塞进 issue）"
reset_fixture
for i in $(seq 1 45); do printf '备注 %s：这一条本该写进 docs/work/tech/。\n' "$i"; done >>"$T/drafts/case.md"
expect "T5 抓到超行数" 1 "行上限"
echo

echo "── T6 把 TEMPLATE.md 的 frontmatter 抄进了 issue 正文"
reset_fixture
{ printf '%s\n' '---'; cat "$T/drafts/case.md"; } >"$T/x" && mv "$T/x" "$T/drafts/case.md"
expect "T6 抓到 frontmatter 混入" 1 "frontmatter"
echo

echo "── T7 表单漂移（task.yml 的 label 改了，骨架没改）"
reset_fixture
sed -i 's/^\([[:space:]]*\)label: 实现$/\1label: 实现步骤/' "$T/task.yml"
expect "T7 抓到表单漂移" 1 "task.yml 的 label"
echo

echo "── T8 骨架漂移（TEMPLATE.md 的字段改了，表单没改）"
reset_fixture
sed -i 's/^### 回报$/### 交付/' "$T/TEMPLATE.md"
expect "T8 抓到骨架漂移" 1 "TEMPLATE.md 的字段"
echo

echo "── T9 真实仓库的骨架与表单不误报"
mkdir -p "$T/empty"
out=$(MIPL_WORK_DRAFTS="$T/empty" "$GUARD" 2>&1) && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then
  pass "T9 真实骨架/表单判为一致"
else
  bad "T9 真实骨架/表单被判漂移（守卫或仓库其一有问题）"
  printf '%s\n' "$out" | sed 's/^/     /'
fi
echo

if [ "$FAIL" -eq 0 ]; then
  echo "全部通过：草案不合规抓得住，骨架与表单的漂移也抓得住，真实文件没有误报。"
  exit 0
fi
echo "有用例失败：守卫抓不住（或误报）某种情形，改守卫或改夹具。"
exit 1
