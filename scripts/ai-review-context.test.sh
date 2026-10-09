#!/usr/bin/env bash
# ai-review-context.sh 的回归测试：造夹具，验「该抓的抓得住、该抑制的抑制得住」。
#
# 为什么有它：一个「永远说 OK」的守卫比没有守卫更坏 —— 它会让人以为检查是自动的
# （同 scripts/check-doc-sync.test.sh 的理由）。这里尤其要防两件事：
#   1) **抑制过头**：把「不做」段当认领（#87 实测踩到）、把绝对路径回退到同名文件（A2 的静默错配）；
#   2) **抑制不足**：段里出现「明确不做」四个字就整段当排除（#97 的 ⑥ 段就是这么被误判的）。
# 两边都必须有夹具盯住 —— 只测一边，另一边的坑会一直躺着。
#
# 夹具全部在临时目录里，**不碰网络、不碰真实仓库**（render 模式只读文本）。
# 不需要 root。用法：./scripts/ai-review-context.test.sh
# 退出码：0 = 全过；1 = 有失败项。

set -uo pipefail
export LC_ALL=C

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$SELF_DIR/ai-review-context.sh"

FAIL=0
pass() { printf '✅ %s\n' "$1"; }
bad()  { printf '❌ %s\n' "$1"; FAIL=1; }
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

[ -f "$SCRIPT" ] || { echo "错误：读不到 $SCRIPT" >&2; exit 1; }

# 夹具共用的假仓库树：故意放两个同名 basename（disk.js 只有一处 → 可解析；
# note.md 两处 → 歧义，必须判不了，不许瞎猜）
fixture_tree() {
  cat <<'EOF'
docs/work/tech/09-安装器界面文案.md
installer/backend/mipl_installer/cli.py
installer/frontend/app/README.md
installer/frontend/app/renderer/js/pages/disk.js
installer/frontend/app/tools/i18n.py
installer/frontend/app/tools/other.py
installer/legacy/old.py
profile/airootfs/etc/pacman.conf
profile/pacman.conf
docs/a/note.md
docs/b/note.md
EOF
}

# ── 夹具 1：正向解析的各种形态 + 「不做」段的两种写法 ──────────────────────────
mk_case_full() {
  local d=$1
  mkdir -p "$d"
  printf 'number\t901\ntitle\t夹具：解析形态\nlabels\ttask\nauthor_association\tMEMBER\n' >"$d/meta.tsv"
  cat >"$d/body.md" <<'EOF'
### 目标

夹具。

### 实现

- 改 `installer/frontend/app/renderer/js/pages/disk.js`，同一件事另写 `disk.js`（两种写法 → 必须去重成 1 条）
- 改 `docs/work/tech/09-安装器界面文案.md`（中文名必须解析得出来）
- 见 `note.md`（同名两处 → 歧义，必须判不了、不许瞎猜）
- `installer/legacy/old.py` 要动（这条会被下面的 `installer/legacy/**` 削掉）
- 键盘选择落进 `/etc/vconsole.conf`（装后系统路径，不许回退到 profile 里那个同名文件）
- 文案走 `tools/i18n.py --write`（命令 + 参数，剥掉参数后是真路径）
- 记录 `1a221bd` 与产物 `out/miplinux-2026.10.02-x86_64.iso`（都不是所有权）
- 见 `Plan.keymap` 与 `keymap.try`（属性名 / i18n 键，不是路径）
- 明确**不**做：不动 `profile/pacman.conf`、不改 `installer/legacy/**`
- ⑥ 善后：`installer/frontend/app/README.md` §7 的「明确不做」按实改（段首不是「不做」→ 仍算正向）

### 验收

- `true` → 期望退出码 0。
EOF
  fixture_tree >"$d/tree.txt"
  printf '900\t另一个 open task\n' >"$d/open-tasks.tsv"
  mkdir -p "$d/open-tasks"
  cat >"$d/open-tasks/900.md" <<'EOF'
### 实现

- 改 `installer/frontend/app/renderer/js/pages/disk.js`（硬撞：同一个文件）
- 改 `installer/frontend/app/tools/other.py`（软邻近：同目录、不同文件）
EOF
  printf '901\tOPEN\t夹具：解析形态\n' >"$d/recent.tsv"
}

# ── 夹具 2：非 task label —— 按 label 分流，所有权整块跳过 ──────────────────────
mk_case_nontask() {
  local d=$1
  mkdir -p "$d"
  printf 'number\t902\ntitle\t夹具：bug\nlabels\tbug\nauthor_association\tMEMBER\n' >"$d/meta.tsv"
  printf '### 问题描述\n\n坏了。\n' >"$d/body.md"
  fixture_tree >"$d/tree.txt"
}

# ── 夹具 3：「实现」段为空 —— 必须是「无法判定」，不是「无重叠」 ────────────────
mk_case_empty() {
  local d=$1
  mkdir -p "$d"
  printf 'number\t903\ntitle\t夹具：空实现\nlabels\ttask\nauthor_association\tMEMBER\n' >"$d/meta.tsv"
  printf '### 目标\n\n夹具。\n\n### 实现\n\n\n\n### 验收\n\n- `true` → 期望退出码 0。\n' >"$d/body.md"
  fixture_tree >"$d/tree.txt"
}

own_block() { sed -n '/我认领了这/,/<\/details>/p' "$1"; }
ign_block() { sed -n '/未计入所有权/,/<\/details>/p' "$1"; }
exc_block() { sed -n '/段排除的/,/<\/details>/p' "$1"; }

# ── 跑夹具 1 ───────────────────────────────────────────────────────────────────
D="$T/full"; mk_case_full "$D"
if "$SCRIPT" --from-dir "$D" --out "$D/out" >"$D/log" 2>&1; then pass "夹具 1 渲染退出码 0"; else bad "夹具 1 渲染失败：$(tail -2 "$D/log")"; fi
F="$D/out/facts.md"

[ -f "$F" ] && pass "facts.md 已生成" || bad "facts.md 没生成"

# A9：中文名必须解析出来（ASCII-only 抽取会漏 —— 实测漏掉 29% 的真阳性）
grep -q '09-安装器界面文案.md' <<<"$(own_block "$F")" && pass "A9 中文名路径进了所有权" || bad "A9 中文名路径没进所有权"

# 命令剥参数：`tools/i18n.py --write` 里藏着一条真路径
grep -q 'tools/i18n.py' <<<"$(own_block "$F")" && pass "命令剥参数后解析出真路径" || bad "命令里的路径没解析出来"

# A2：绝对路径不许回退到 profile 里的同名文件
if grep -q 'profile/airootfs/etc/vconsole.conf' <<<"$(own_block "$F")"; then
  bad "A2 绝对路径被错误回退成了 profile 里的同名文件"
else
  pass "A2 绝对路径未被回退（静默错配拦住了）"
fi
grep -q '/etc/vconsole.conf.*装后系统路径' <<<"$(ign_block "$F")" && pass "A2 绝对路径被标成「装后系统路径」" || bad "A2 绝对路径没被标注"

# 歧义 basename：两处同名 → 不许瞎猜
if grep -q 'note.md' <<<"$(own_block "$F")"; then bad "歧义 basename 被瞎猜成了所有权"; else pass "歧义 basename 没有进所有权"; fi

# A5：列表项形态的「不做」段 —— 整段排除，且 `dir/**` 削减整棵子树
if grep -q 'profile/pacman.conf' <<<"$(own_block "$F")"; then
  bad "A5「不做」段里的全路径漏进了所有权"
else
  pass "A5「不做」段里的全路径被排除"
fi
if grep -q 'installer/legacy/old.py' <<<"$(own_block "$F")"; then
  bad "A5 通配排除 `installer/legacy/**` 没削掉子树里的文件"
else
  pass "A5 通配排除削掉了子树"
fi
grep -q 'profile/pacman.conf' <<<"$(exc_block "$F")" && pass "被「不做」排除的项有回显" || bad "被排除的项没有回显"

# A5 反面：段里出现「明确不做」但段首不是它 → 仍算正向（#97 的 ⑥ 段）
grep -q 'installer/frontend/app/README.md' <<<"$(own_block "$F")" && pass "A5 反面：引用了「明确不做」的段落仍算正向" || bad "A5 反面：正向段被误判成排除段"

# 去重：同一文件两种写法只能算一条
n_disk=$(grep -c 'pages/disk.js' <<<"$(own_block "$F")")
[ "$n_disk" -eq 1 ] && pass "同一文件两种写法去重成 1 条" || bad "去重失败（disk.js 出现 $n_disk 次）"

# A10：hash / 产物 / 属性名 / i18n 键都不进所有权
if grep -Eq '1a221bd|\.iso|Plan\.keymap|keymap\.try' <<<"$(own_block "$F")"; then
  bad "A10 非所有权的东西进了所有权（hash / 产物 / 属性名 / 键）"
else
  pass "A10 hash、产物、属性名、i18n 键都没进所有权"
fi

# 硬撞 / 软邻近
grep -q '硬撞 1' "$F" && pass "硬撞被判出 1 处" || bad "硬撞没判出来"
grep -q '软邻近 1' "$F" && pass "软邻近被判出 1 处（硬撞所在的目录不重复报）" || bad "软邻近计数不对（期望 1）"
grep -q 'installer/frontend/app/tools/' <<<"$(sed -n '/软邻近/,/details/p' "$F")" && pass "软邻近报的是目录级" || bad "软邻近没报到目录级"

# ── 跑夹具 2：非 task label 分流 ───────────────────────────────────────────────
D2="$T/nontask"; mk_case_nontask "$D2"
"$SCRIPT" --from-dir "$D2" --out "$D2/out" >/dev/null 2>&1
grep -q '跳过' "$D2/out/facts.md" && pass "非 task label 跳过所有权雷达（按 label 分流）" || bad "非 task label 没跳过"
grep -q '我认领了这' "$D2/out/facts.md" && bad "非 task label 仍然输出了认领清单" || pass "非 task label 没有输出认领清单"

# ── 跑夹具 3：空「实现」→ 无法判定 ─────────────────────────────────────────────
D3="$T/empty"; mk_case_empty "$D3"
"$SCRIPT" --from-dir "$D3" --out "$D3/out" >/dev/null 2>&1
grep -q '无法判定' "$D3/out/facts.md" && pass "空「实现」判成「无法判定」（不是「无重叠」）" || bad "空「实现」没判成「无法判定」"
grep -q '认领 0 个文件' "$D3/out/facts.md" && bad "空「实现」被说成了「认领 0 个文件」（会被读成没重叠）" || pass "空「实现」没被说成「认领 0 个文件」"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "结论：该抓的抓得住，该抑制的抑制得住。"
  exit 0
fi
echo "结论：有失败项。"
exit 1
