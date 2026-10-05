#!/usr/bin/env bash
# pr-acceptance-context.sh 的回归测试：夹具取自四个真实历史回合，断言「该抑制的抑制住、该报的报得出」。
#
# 为什么有它：C 的两侧都是人写的散文，匹配规则稍一放宽就会把「数字对不上」洗成 ✅
# （实测：判据「42 项断言全过」与 PR「84 项断言全过」共享词面「项断言全」，一度被判成 ✅）。
# 反过来收得太紧，就会像第一版那样把整片判据报成缺口（#81 五条全 ⚠️）。
# 两边都要有夹具钉住。
#
# 夹具全部在临时目录里，**不联网、不碰真实仓库**。
# 不需要 root。用法：./scripts/pr-acceptance-context.test.sh
# 退出码：0 = 全过；1 = 有失败项。

set -uo pipefail
export LC_ALL=C

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$SELF_DIR/pr-acceptance-context.sh"

FAIL=0
pass() { printf '✅ %s\n' "$1"; }
bad()  { printf '❌ %s\n' "$1"; FAIL=1; }
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
[ -f "$SCRIPT" ] || { echo "错误：读不到 $SCRIPT" >&2; exit 1; }

# ── 夹具 1：#92 ↔ PR #96 的真实文案（8 条判据，四类信号都有）───────────────────
mk_case_92() {
  local d=$1
  mkdir -p "$d/issues"
  printf 'number\t96\ntitle\t无头自动安装：真后端 + 真盘接线\nhead\t3064e79cafe\nstate\tMERGED\n' >"$d/meta.tsv"
  cat >"$d/pr-body.md" <<'EOF'
## 改了什么

装盘链路接真后端。

## 验证方式

| 项 | 结果 |
|---|---|
| 构建 `sudo ./scripts/mipl.sh build` | 维护者 2026-10-04 构建：`out/miplinux-2026.10.04-x86_64.iso` **2.67 GiB**（比 10-02 的 2.57 GiB **+104.5 MiB**）|
| QEMU `sudo ./scripts/mipl.sh qemu` | 维护者逐屏点过（普通 8 步 + 高级 12 步）；**修复后的版本未重新验** |
| 静态检查 | 单测 30/30 · 文案 138 键 × 2 语言 · 色板三方一致 · 对比度 46/46 · 纯函数 56/56 · **Electron 离屏探针 84 项断言全过** |

**仍未实测**：V3 键盘全流程 · V4 首帧预算 · V5 视觉基线 · V7/V8 真机缩放。
EOF
  printf '92\t安装器前端换 Electron\n' >"$d/issues.tsv"
  cat >"$d/issues/92.md" <<'EOF'
### 目标

夹具。

### 实现

改 `installer/frontend/app/main.js`。

### 验收

- `node --test "installer/frontend/app/tests/*.test.mjs"` → **30/30 通过**。
- `python3 installer/frontend/app/tools/i18n.py --check` → **138 键 × 2 语言**与 tech/09 逐字一致。
- `gen-tokens.py --check` / `gen-icons.py --check` → 生成物与源一致（不许手改）。
- `check-tokens.py` → 品牌色板三方一致（color.json ↔ palette.css）+ 设计 token 结构合规。
- `check-contrast.py` → **46 组全过**。
- `python3 -m unittest discover -s installer/frontend/theme/tests` → 51 项通过。
- `node installer/frontend/app/tools/probe-render.js` → **42 项断言全过**，并落 15 张截图。
- **未实测**：ISO 构建、`cage` 里起窗与观感（V3 / V4 / V5 / V7 / V8）需要 `mipl build` + `qemu`（要 root），由维护者跑。

### 回报

无
EOF
  : >"$d/other-prs.tsv"
}

# ── 夹具 2：一条 issue 被两个 PR 关，证据在另一个 PR 里（R7）───────────────────
mk_case_multi() {
  local d=$1
  mkdir -p "$d/issues" "$d/other-prs"
  printf 'number\t83\ntitle\t补回 Live 入口\nhead\tfe3a867aaaa\nstate\tMERGED\n' >"$d/meta.tsv"
  printf '## 验证方式\n\n| 项 | 结果 |\n|---|---|\n| 静态检查 | `./scripts/check-identity.sh` → 0 |\n' >"$d/pr-body.md"
  printf '79\tMD3 阶段 0\n' >"$d/issues.tsv"
  cat >"$d/issues/79.md" <<'EOF'
### 验收

- `python3 installer/frontend/qml/Mipl/tokens/tools/check-contrast.py` → 期望 28 组全过、0 组不合格。
- `sudo ./scripts/mipl.sh build` → 期望构建成功（要 root，由维护者执行）。

### 回报

无
EOF
  printf '80\tfeat(installer)：MD3 阶段 0\n' >"$d/other-prs.tsv"
  printf '## 验证方式\n\n| 项 | 结果 |\n|---|---|\n| V2 对比度 | `check-contrast.py` → exit 0，**28 组全过** |\n' >"$d/other-prs/80.md"
}

run() { # $1=夹具目录 $2=输出目录
  "$SCRIPT" --from-dir "$1" --out "$2" >"$1/log" 2>&1
}
counts() { grep -o '判据 [0-9]* 条（机械信号）：.*' "$1" | head -1; }

# ── 跑夹具 1 ───────────────────────────────────────────────────────────────────
D="$T/c92"; mk_case_92 "$D"
if run "$D" "$D/out"; then pass "夹具 1 退出码 0"; else bad "夹具 1 失败：$(tail -2 "$D/log")"; fi
F="$D/out/facts.md"
[ -f "$F" ] && pass "facts.md 已生成" || bad "facts.md 没生成"

grep -q '判据 8 条' "$F" && pass "判据条数 = 8（与 issue #92 的验收条数一致）" || bad "判据条数不对：$(counts "$F")"

# R1/R5：数字对不上必须是 ❓，不许被共享词面洗成 ✅（42 项 vs 84 项就是这条）
grep -E '^\| 7 ' "$F" | grep -q '❓' && pass "R5：42 项 vs 84 项判成 ❓（没被词面洗成 ✅）" || bad "R5：数字对不上的那条判错了"
grep -E '^\| 6 ' "$F" | grep -q '❓' && pass "R5：51 项 vs 56 项判成 ❓" || bad "R5：51/56 那条判错了"

# 同值命中
grep -E '^\| 1 ' "$F" | grep -q '✅.*30/30' && pass "同值 30/30 命中 ✅" || bad "同值信号没生效"
grep -E '^\| 2 ' "$F" | grep -q '✅.*138' && pass "同值 138 命中 ✅" || bad "138 键没命中"

# 词面命中（两边都没数字）
grep -E '^\| 4 ' "$F" | grep -q '✅' && pass "词面信号：品牌色板三方一致 ↔ 色板三方一致" || bad "词面信号没生效"

# R3：判据自带「要 root，由维护者跑」→ ➖
grep -E '^\| 8 ' "$F" | grep -q '➖' && pass "R3：自带「要 root / 由维护者」的判据被抑制成 ➖" || bad "R3 抑制没生效"

# 真缺口：PR 正文里确实没写的判据要报出来（脚本没有一律说 OK）
grep -E '^\| 3 ' "$F" | grep -q '⚠️' && pass "真缺口（gen-tokens / gen-icons 没写进 PR）报成 ⚠️" || bad "真缺口没报出来"

# 表里不许出现被切碎的 UTF-8（grep 会把整份文件当二进制：实测踩到）
if grep -q '二进制文件' "$D/log" 2>/dev/null; then bad "输出里有被切碎的 UTF-8（grep 报二进制）"; else pass "截断没有切碎 UTF-8"; fi

# ── 夹具 1 的反例：把 PR 里对应的声称删掉，那条必须翻成 ⚠️ ────────────────────
D2="$T/c92b"; cp -r "$D" "$D2"; rm -rf "$D2/out" "$D2/log"
sed -i 's/单测 30\/30 · //' "$D2/pr-body.md"
run "$D2" "$D2/out"
grep -E '^\| 1 ' "$D2/out/facts.md" | grep -q '⚠️' && pass "反例：把声称删掉后，对应判据从 ✅ 翻成 ⚠️" || bad "反例失败：删掉声称也没翻成 ⚠️（会变成「永远说 OK」）"

# ── 夹具 2：R7 多对多 ──────────────────────────────────────────────────────────
D3="$T/cmulti"; mk_case_multi "$D3"
run "$D3" "$D3/out"
grep -q 'PR #80' "$D3/out/facts.md" && pass "R7：证据在另一个 PR 里时被认到（点名 PR #80）" || bad "R7：没认到另一个 PR 里的证据"
grep -E '^\| 2 ' "$D3/out/facts.md" | grep -q '➖' && pass "R7 + R3：自带「要 root」的那条仍被抑制" || bad "R3 在多 PR 夹具里失效"

# ── 夹具 3：没有 Closes 关联 → 必须是「无法判定」而不是「对上了」────────────────
D4="$T/cnolink"; mkdir -p "$D4"
printf 'number\t900\ntitle\t没有关联的 PR\nhead\tdeadbeef000\nstate\tOPEN\n' >"$D4/meta.tsv"
printf '## 验证方式\n\n| 项 | 结果 |\n|---|---|\n| 静态检查 | 全过 |\n' >"$D4/pr-body.md"
: >"$D4/issues.tsv"
run "$D4" "$D4/out"
grep -q '无法判定' "$D4/out/facts.md" && pass "没关联 issue 的 PR 判成「无法判定」" || bad "没关联 issue 时没说「无法判定」"
grep -q '判据 0 条' "$D4/out/facts.md" && bad "0 条判据被说成了「判据 0 条」（会被读成没缺口）" || pass "0 条判据没被报成「判据 0 条」"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "结论：该抑制的抑制得住，该报的报得出。"
  exit 0
fi
echo "结论：有失败项。"
exit 1
