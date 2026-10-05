#!/usr/bin/env bash
# 验收对账的上下文生成器 —— 与 ai-review-context.sh 同一条思路：**脚本算能算准的，语义交给模型**。
#
# 为什么要有它（Issue #99）：
#   PR 正文里的「验证方式」与它关掉的那条 issue 的「验收」是两份人写的文本，
#   哪条判据没写进 PR、哪个数字已经过期，全靠人逐条比。2026-10-05 拿四个历史回合
#   （#92↔PR#96、#81↔PR#82、#79↔PR#80+PR#83、#73↔PR#78，共 24 条判据）量过：
#   朴素逐条比对会标出 8 条（33%），**其中没有一条是「真做了没验」** ——
#   全是量纲不同、判据被更强的证据替代、判据自带「要 root」、数字随实现增长这类。
#   所以这个脚本**不判定真伪**，只把两侧摊平、给出机械信号，档位由 rubric 的规则定。
#
# 为什么机械信号只到「同值 / 同量纲异值 / 无信号」为止：
#   人的 PR 正文不会重复命令（#92 的判据写 `node --test …`，PR 只写「单测 30/30」），
#   命令级的对齐做不到可靠 —— 硬做只会制造误报。可靠的那几种信号留给脚本，
#   剩下的（尤其「判据被更强的证据替代」）交给模型按 rubric 判。
#
# 两个模式：
#   --pr <N>       取 GitHub 数据（要 gh 且已登录；联网）+ 本地渲染
#   --from-dir <D> 只渲染（离线），回归测试走这条
#
# 产物（写进 --out，默认 /tmp/mipl-pr-acceptance）：
#   facts.md     判据清单 + 机械信号 + 计数（评论的前半段）
#   context.md   喂给模型的上下文（两侧全文 + 其它关闭同一 issue 的 PR + 历史口径）
#
# 不需要 root。退出码：0 = 正常；1 = 用法错误、读不到输入或 gh 失败。

set -euo pipefail
export LC_ALL=C

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)

MODE=""; PR=""; FROM_DIR=""
OUT_DIR=${MIPL_PR_ACCEPTANCE_OUT:-/tmp/mipl-pr-acceptance}

usage() { sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --pr)       [ $# -ge 2 ] || { echo "错误：--pr 需要一个编号" >&2; exit 1; }; MODE=collect; PR=$2; shift 2 ;;
    --from-dir) [ $# -ge 2 ] || { echo "错误：--from-dir 需要一个目录" >&2; exit 1; }; MODE=render; FROM_DIR=$2; shift 2 ;;
    --out)      [ $# -ge 2 ] || { echo "错误：--out 需要一个目录" >&2; exit 1; }; OUT_DIR=$2; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "错误：不认识参数 $1（见 --help）" >&2; exit 1 ;;
  esac
done
[ -n "$MODE" ] || { usage; exit 1; }

mkdir -p "$OUT_DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ── collect ───────────────────────────────────────────────────────────────────
collect() {
  local n=$1 dir=$2
  echo "── 取 GitHub 数据：PR #$n"
  mkdir -p "$dir/issues" "$dir/other-prs"

  local assoc
  assoc=$(gh api "repos/{owner}/{repo}/pulls/$n" -q .author_association 2>/dev/null || true)
  gh pr view "$n" --json number,title,headRefOid,state \
      -q '[.number, .title, .headRefOid, .state] | @tsv' \
    | awk -F'\t' -v a="$assoc" '{printf "number\t%s\ntitle\t%s\nhead\t%s\nstate\t%s\nauthor_association\t%s\n", $1, $2, $3, $4, a}' \
    >"$dir/meta.tsv"
  gh pr view "$n" --json body -q .body >"$dir/pr-body.md"

  # 关联关系必须**多对多**：一个 PR 可关多条 issue；一条 issue 可被多个 PR 关（#79 ← PR#80 + PR#83）。
  # 只按「一个 PR 一条 issue」取数，必然把 #80 判成「build 没跑」。
  grep -Eio 'close[sd]?[[:space:]]+#[0-9]+|fixe[sd]?[[:space:]]+#[0-9]+|resolves?[[:space:]]+#[0-9]+' "$dir/pr-body.md" \
    | grep -Eo '[0-9]+' | sort -un >"$dir/issue-numbers.txt" || true
  : >"$dir/issues.tsv"
  local inum
  while IFS= read -r inum; do
    [ -n "$inum" ] || continue
    gh issue view "$inum" --json number,title -q '[.number, .title] | @tsv' >>"$dir/issues.tsv"
    gh issue view "$inum" --json body -q .body >"$dir/issues/$inum.md"
  done <"$dir/issue-numbers.txt"

  # 其它 PR：同一批 issue 可能还有别的 PR 也在验（R7 —— 判据的证据可能在另一个 PR 里）
  : >"$dir/other-prs.tsv"
  while IFS=$'\t' read -r inum _; do
    [ -n "$inum" ] || continue
    # 先按编号搜，再**核一遍它真的声明关闭这条 issue** —— 只按「正文提到过编号」会捞进一堆
    # 只是引用了一下编号的 PR（实测 #79 捞到 #82，那是一条纯文档 PR）。
    local cand
    cand=$(gh pr list --state all --limit 20 --search "#$inum in:body" --json number,title \
             -q '.[] | [.number, .title] | @tsv' 2>/dev/null || true)
    [ -n "$cand" ] || continue
    while IFS=$'\t' read -r pnum ptitle; do
      [ -n "$pnum" ] || continue
      gh pr view "$pnum" --json body -q .body 2>/dev/null \
        | grep -Eqi "close[sd]?[[:space:]]+#$inum([^0-9]|$)|fixe[sd]?[[:space:]]+#$inum([^0-9]|$)|resolves?[[:space:]]+#$inum([^0-9]|$)" \
        && printf '%s\t%s\n' "$pnum" "$ptitle" >>"$dir/other-prs.tsv" || true
    done <<<"$cand"
  done <"$dir/issues.tsv"
  sort -u -o "$dir/other-prs.tsv" "$dir/other-prs.tsv"
  while IFS=$'\t' read -r pnum _; do
    [ -n "$pnum" ] || continue
    [ "$pnum" = "$n" ] && continue
    gh pr view "$pnum" --json body -q .body >"$dir/other-prs/$pnum.md" || true
  done <"$dir/other-prs.tsv"

  echo "   关联 issue：$(cut -f1 "$dir/issues.tsv" 2>/dev/null | tr '\n' ' ')"
  echo "   其它相关 PR：$(cut -f1 "$dir/other-prs.tsv" 2>/dev/null | tr '\n' ' ')"
}

# ── 切段：`## <名>` / `### <名>` 到下一个同级或更高级的标题 ───────────────────────
# 层级不能写死：**issue 的字段是 h3（`### 验收`），而 PR 模板的字段是 h2（`## 验证方式`）**。
# 只认 `###` 的话 PR 那一侧一条都抽不到，于是每条判据都被判成「没有对应声称」——
# 实测踩到：修之前 #92 的 8 条判据全报 ⚠️（正是 rubric 要压掉的那种误报）。
section_of() { # $1=文件 $2=段名
  awk -v want="$2" '
    /^#+[[:space:]]/ {
      n = 0; tmp = $0
      while (substr(tmp, n + 1, 1) == "#") n++
      line = $0; sub(/^#+[[:space:]]*/, "", line); sub(/[[:space:]]*$/, "", line)
      if (f && n <= lvl) f = 0
      if (!f && line == want) { f = 1; lvl = n; next }
    }
    f { print }
  ' "$1"
}

# 把一段切成条目：列表项各算一条，空行也算分隔（与 ai-review-context.sh 同一套切法）
blocks_of() { # $1=文件
  awk '{ if ($0 ~ /^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]/) print ""; print }' "$1" \
    | awk 'BEGIN{RS="";ORS="\n"} {gsub(/^[[:space:]]+|[[:space:]]+$/,""); if (length($0)) print $0"\n"}'
}

# ── 条目分型（rubric §3.1）────────────────────────────────────────────────────
type_of() { # $1=条目
  local t=$1 h
  h=$(printf '%s' "$t" | head -1 | tr -d '*[:space:]')
  case "$h" in 现状*|口径*) printf 'STATUS'; return 0 ;; esac
  # R3：判据自带「要 root / 由维护者执行」—— 本仓库口径里这类本来就该由维护者另跑
  if printf '%s' "$t" | grep -Eq '要[[:space:]]*root|需[[:space:]]*root|由维护者|需维护者|真机'; then printf 'DEFERRED'; return 0; fi
  if printf '%s' "$t" | grep -q '`'; then printf 'CMD'; return 0; fi
  printf 'NARRATIVE'
}

# ── 数字与量纲（rubric R1 / R5 的判据）────────────────────────────────────────
# 只认**带量纲**的数字（或 `数字/数字` 比例）—— 实测教训：单位可选的写法会捞出
# 「2」「10」「12」这种裸数字，然后在哪里都能 grep 到，于是每条判据都成了 ✅。
# 值要求 ≥2 位：一位数的「8 步」这类不构成有辨识度的信号。
numbers_of() { # $1=文本 → `<值>\t<量纲>`
  printf '%s' "$1" \
    | grep -oE '[0-9]{2,}/[0-9]{2,}|[0-9]{2,}(\.[0-9]+)?[[:space:]]*(项|组|键|条|张|个|次|轮|字节|MiB|KiB|GiB|%)' \
    | awk '{
        if ($0 ~ /^[0-9]+\/[0-9]+$/) { print $0"\t比例"; next }
        v=$0; u=""
        if (match($0, /[^0-9.[:space:]]+$/)) { u=substr($0, RSTART); v=substr($0, 1, RSTART-1) }
        gsub(/[[:space:]]/,"",v); gsub(/[[:space:]]/,"",u)
        if (v != "") print v"\t" u
      }' | sort -u || true
  # 没有数字时 grep 返回 1；`set -e` + `pipefail` 会把调用点直接带崩（实测踩到）——
  # 所以这个函数**永远返回 0**，「没信号」是一种正常结果。
}

# 词面信号：从判据里挖出**连续中文片段**，再切成 12 字节（≈4 个汉字）的滑窗。
# 为什么需要它：判据 4 写「品牌色板三方一致」，PR 只写「色板三方一致」，两边一个数字都没有 ——
# 只有词面能对上。C locale 下按字节处理，UTF-8 汉字正好 3 字节，所以滑窗步长取 3。
#
# 字符类的两个坑（都实测踩到，写了注释免得被「顺手清理」回去）：
#   1. **`]` 必须放首位、`[` 直接字面写**：写成 `\[\]` 会让 GNU sed 在 C locale 下整个字符类失效
#      （整行原样穿过去，且不报错 —— 于是词面信号静默全灭）。
#   2. **类里不许出现多字节字符**（`×` `→` `↔`）：同样会让整个类失效。这些符号两侧本来就有空格，
#      空格已经在类里，所以不需要它们。
cjk_phrases() { # $1=文本 → 每行一个 ≥12 字节的中文片段
  printf '%s' "$1" \
    | sed 's/[]A-Za-z0-9_ ./`*(){}<>:;,!?+=|"#@$%^~[-]/\n/g' \
    | awk 'length($0) >= 12 { print }'
}
windows_of() { # $1=中文片段 → 12 字节滑窗
  # 注意：`local s=$1 n=${#s}` 这种一行连写在 bash 里会先展开 `${#s}` 再赋值，
  # 配 `set -u` 直接报 unbound variable —— 而且错在 stderr，调用点只会静默拿到空输入
  # （实测踩到：词面信号一次都没生效过，整片判据被误报成缺口）。必须分两行。
  local s=$1
  local n=${#s} i
  for ((i = 0; i + 12 <= n; i += 3)); do printf '%s\n' "${s:i:12}"; done
}
# 太常见的四字窗不许当证据（否则「期望结果」「全部通过」这种会到处命中）
STOP_WINDOWS='期望结果 命令输出 退出码 全部通过 全部一致 逐字一致 期望全绿 以上都是'

window_hit() { # $1=窗口 $2=声称文件 → 命中则打印命中的行号
  case " $STOP_WINDOWS " in *" $1 "*) return 0 ;; esac
  grep -nF -- "$1" "$2" | head -1 || true
}

# ASCII token 信号：反引号片段里的**文件路径 / 脚本名**。
# 文档类判据（#81 那种「grep 三处 → 期望 0 命中」）两边一个数字都没有，
# 能对上的就是路径名本身 —— 少了这一路，那类 PR 会整片报成缺口（实测 #82 五条全 ⚠️）。
tokens_of() { # $1=文本 → 每行一个有辨识度的 token
  grep -o '`[^`]*`' <<<"$1" 2>/dev/null | tr -d '`' | tr ' ' '\n' \
    | sed -e "s/^[\"']*//" -e "s/[\"']*\$//" \
    | grep -E '/|\.(py|sh|md|json|yml|yaml|mjs|js|css|conf|hook|fd|iso)$' \
    | awk 'length($0) >= 6' | sort -u || true
}

# 按字节截断但**不切碎 UTF-8 字符**：`cut -c` 在 C locale 下按字节切，切在汉字中间会留下
# 非法字节序列 —— 之后 `grep` 会把整份 facts.md 当二进制文件（实测：「匹配到二进制文件」，
# 表格直接没法读）。iconv -c 丢掉不完整的尾部序列，是 glibc 自带、无需新依赖。
trunc_bytes() { # $1=文本 $2=字节上限
  printf '%s' "$1" | head -c "$2" | iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || true
}

# PR 正文的「验证方式」→ 每行一条声称（表格行与列表项都清洗过）
claims_of() { # $1=PR 正文文件
  section_of "$1" 验证方式 \
    | grep -vE '^[[:space:]]*\|?[[:space:]]*-{2,}' \
    | grep -vE '^[[:space:]]*\|[[:space:]]*项[[:space:]]*\|' \
    | while IFS= read -r line; do
        line=$(printf '%s' "$line" | sed 's/^[[:space:]]*|[[:space:]]*//; s/[[:space:]]*|[[:space:]]*$//; s/^[[:space:]]*[-*][[:space:]]*//')
        [ -n "$line" ] || continue
        printf '%s\n' "$line"
      done || true
}

# ── render ────────────────────────────────────────────────────────────────────
render() {
  local dir=$1 out=$2
  [ -f "$dir/meta.tsv" ] || { echo "错误：读不到 $dir/meta.tsv" >&2; exit 1; }
  [ -f "$dir/pr-body.md" ] || { echo "错误：读不到 $dir/pr-body.md" >&2; exit 1; }

  local pr title head
  pr=$(awk -F'\t' '$1=="number"{print $2}' "$dir/meta.tsv")
  title=$(awk -F'\t' '$1=="title"{print $2}' "$dir/meta.tsv")
  head=$(awk -F'\t' '$1=="head"{print $2}' "$dir/meta.tsv")

  : >"$TMP/criteria.tsv"; : >"$TMP/claims.tsv"
  local inum
  while IFS=$'\t' read -r inum _; do
    [ -n "$inum" ] || continue
    [ -f "$dir/issues/$inum.md" ] || continue
    section_of "$dir/issues/$inum.md" 验收 >"$TMP/acc.md"
    blocks_of "$TMP/acc.md" | while IFS= read -r blk; do
      [ -n "$blk" ] || continue
      printf '%s\t%s\t%s\n' "$inum" "$(type_of "$blk")" "$(trunc_bytes "$(printf '%s' "$blk" | tr '\n' ' ')" 200)" >>"$TMP/criteria.tsv"
    done
  done <"$dir/issues.tsv"

  # PR 侧的声称：验证方式段的每一行算一条
  claims_of "$dir/pr-body.md" >"$TMP/claims.md"
  # R7：**其它也声明关闭同一 issue 的 PR** 的声称并进来一起对 ——
  # #79 那条 issue 是 #80 与 #83 两个 PR 一起关的，只对当前 PR，另一条 PR 里的证据就看不见了。
  cp "$TMP/claims.md" "$TMP/claims_all.md"
  if [ -f "$dir/other-prs.tsv" ]; then
    local op
    while IFS=$'\t' read -r op _; do
      [ -n "$op" ] || continue
      [ -f "$dir/other-prs/$op.md" ] || continue
      claims_of "$dir/other-prs/$op.md" | sed "s|^|[PR #$op] |" >>"$TMP/claims_all.md"
    done <"$dir/other-prs.tsv"
  fi

  # 其它 PR 的验证方式（R7 的证据来源）
  : >"$TMP/other.md"
  if [ -f "$dir/other-prs.tsv" ]; then
    local pnum
    while IFS=$'\t' read -r pnum _; do
      [ -n "$pnum" ] || continue
      [ -f "$dir/other-prs/$pnum.md" ] || continue
      printf '### PR #%s\n%s\n\n' "$pnum" "$(section_of "$dir/other-prs/$pnum.md" 验证方式)" >>"$TMP/other.md"
    done <"$dir/other-prs.tsv"
  fi

  # ── 机械信号：同值 / 同量纲异值 / 无信号 ──────────────────────────────────────
  : >"$TMP/table.tsv"
  local n_total=0 n_ok=0 n_na=0 n_q=0 n_warn=0
  local i=0
  while IFS=$'\t' read -r inum ctype text; do
    [ -n "$text" ] || continue
    i=$((i + 1)); n_total=$((n_total + 1))
    local hint note
    if [ "$ctype" = "STATUS" ]; then
      hint="➖"; note="口径行（现状 / 口径），不参与对账"; n_na=$((n_na + 1))
    elif [ "$ctype" = "DEFERRED" ]; then
      hint="➖"; note="按 R3 抑制：判据自带「要 root / 由维护者执行」"; n_na=$((n_na + 1))
    else
      # ① 数字同值（带词边界：`46` 不许匹配到 `1046`）
      local hit="" vals v
      vals=$(numbers_of "$text" | cut -f1 | sort -u || true)
      for v in $vals; do
        case "$v" in
          */*) grep -qF -- "$v" "$TMP/claims_all.md" && { hit="$v"; break; } ;;
          *)   grep -qE "(^|[^0-9])$(printf '%s' "$v" | sed 's/\./\\./g')([^0-9]|$)" "$TMP/claims_all.md" && { hit="$v"; break; } ;;
        esac
      done
      # ② 同量纲异值 —— **必须排在词面之前**：实测 #92 的判据写「42 项断言全过」，
      # PR 写「84 项断言全过」，共享「项断言全」这个词面但数字完全不同；
      # 先看词面就会把「数字对不上」误报成 ✅（正是 R1/R5 要挡的那种）。
      local dif=""
      if [ -z "$hit" ]; then
        local dv du cand
        while IFS=$'\t' read -r dv du; do
          [ -n "$du" ] || continue
          cand=$(grep -nF -- "$du" "$TMP/claims_all.md" | head -1 || true)
          [ -n "$cand" ] && { dif="${dv}${du} → $(sed -n "${cand%%:*}p" "$TMP/claims_all.md" | cut -c1-30)"; break; }
        done < <(numbers_of "$text" || true)
      fi
      # ③ ASCII token 命中（路径 / 脚本名）
      local tok=""
      if [ -z "$hit" ] && [ -z "$dif" ]; then
        while IFS= read -r t; do
          [ -n "$t" ] || continue
          grep -qF -- "$t" "$TMP/claims_all.md" && { tok="$t"; break; }
        done < <(tokens_of "$text")
      fi
      # ③ 词面命中（两边都没数字、也没路径时唯一能对上的信号）
      local phrase=""
      if [ -z "$hit" ] && [ -z "$dif" ] && [ -z "$tok" ]; then
        local p w
        while IFS= read -r p; do
          while IFS= read -r w; do
            [ -n "$w" ] || continue
            if window_hit "$w" "$TMP/claims_all.md" | grep -q .; then phrase="$w"; break; fi
          done < <(windows_of "$p")
          [ -n "$phrase" ] && break
        done < <(cjk_phrases "$text")
      fi
      local where=""
      [ -n "$hit" ] && where=$(grep -nF -- "$hit" "$TMP/claims_all.md" | head -1 | cut -d: -f1)
      [ -n "$tok" ] && [ -z "$where" ] && where=$(grep -nF -- "$tok" "$TMP/claims_all.md" | head -1 | cut -d: -f1)
      [ -n "$phrase" ] && [ -z "$where" ] && where=$(grep -nF -- "$phrase" "$TMP/claims_all.md" | head -1 | cut -d: -f1)
      if [ -n "$where" ]; then
        local line; line=$(sed -n "${where}p" "$TMP/claims_all.md")
        case "$line" in
          "[PR #"*) note="证据在 **${line%%]*}]** 的声称里：$(printf '%s' "$line" | sed 's/^\[PR #[0-9]*\] //' | cut -c1-40)" ;;
          *)        note="命中本 PR 的声称：$(printf '%s' "$line" | cut -c1-40)" ;;
        esac
      fi
      if [ -n "$hit" ]; then
        note="同值 $hit —— $note"; hint="✅"; n_ok=$((n_ok + 1))
      elif [ -n "$dif" ]; then
        note="同量纲异值：${dif}"; hint="❓"; n_q=$((n_q + 1))
      elif [ -n "$tok" ]; then
        note="同名对象 \`$tok\` —— $note"; hint="✅"; n_ok=$((n_ok + 1))
      elif [ -n "$phrase" ]; then
        note="词面「$phrase」—— $note"; hint="✅"; n_ok=$((n_ok + 1))
      else
        note="机械层面没有找到对应声称"; hint="⚠️"; n_warn=$((n_warn + 1))
      fi
    fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$i" "$ctype" "$hint" "$note" "$(trunc_bytes "$text" 60)" >>"$TMP/table.tsv"
  done <"$TMP/criteria.tsv"

  # ── facts.md ────────────────────────────────────────────────────────────────
  {
    # 没有关联 issue 时不要把「判据来自 issue 」后面留空 —— 实测第一次真跑就出现了这个空列表
    local label
    label=$(cut -f1 "$dir/issues.tsv" 2>/dev/null | tr '\n' ' ' | sed 's/ $//' || true)
    if [ -n "$label" ]; then
      echo "## 验收对账（机器 · PR #$pr · head ${head:0:7} · 判据来自 issue $label）"
    else
      echo "## 验收对账（机器 · PR #$pr · head ${head:0:7}）"
    fi
    echo
    if [ "$n_total" -eq 0 ]; then
      echo "⚠️ 无法判定：这条 PR 没有关联到带「验收」段的 issue（或 issue 里读不出判据）。"
      echo
      echo "（这**不等于**「对上了」—— 是没得对。正文里写 \`Closes #<编号>\` 才会被认到。）"
    else
      echo "判据 $n_total 条（机械信号）：✅ $n_ok · ➖ $n_na · ❓ $n_q · ⚠️ $n_warn"
      echo
      echo "| # | 型 | 建议档 | 机械信号（不是判决） | 判据（截断） |"
      echo "|---|---|---|---|---|"
      while IFS=$'\t' read -r idx ctype hint note txt; do
        printf '| %s | %s | %s | %s | `%s` |\n' "$idx" "$ctype" "$hint" "$note" "$txt"
      done <"$TMP/table.tsv"
      echo
      echo "「建议档」只由机械信号得出（同值 / 同量纲异值 / 无信号），**R2「被更强的证据替代」这类判不出来** —— 最终档位由 rubric 的规则定。"
    fi
  } >"$out/facts.md"

  # ── context.md ──────────────────────────────────────────────────────────────
  {
    echo "# 验收对账的上下文"
    echo
    echo "**本次任务：C（验收对账）** —— 按 docs/work/ai-review-rubric.md 第十节的输出契约回答。"
    echo
    echo "## PR #$pr $title"
    echo
    echo '### PR 正文'
    echo '```markdown'; cat "$dir/pr-body.md"; echo '```'
    echo
    echo "## 脚本抽出的判据与机械信号（**不要重算**，可以推翻并说明理由）"
    echo '```markdown'; cat "$out/facts.md"; echo '```'
    echo
    echo "## PR 侧的声称（逐行，编号即上面信号里引用的行号）"
    echo '```'; nl -ba "$TMP/claims_all.md"; echo '```'
    echo
    local inum
    while IFS=$'\t' read -r inum it; do
      [ -n "$inum" ] || continue
      [ -f "$dir/issues/$inum.md" ] || continue
      echo "## 关联 issue #$inum $it（全文）"
      echo '```markdown'; cat "$dir/issues/$inum.md"; echo '```'
      echo
    done <"$dir/issues.tsv"
    if [ -s "$TMP/other.md" ]; then
      echo "## 其它 PR 也提到同一批 issue —— 判据的证据可能在它们里面（rubric R7）"
      echo '```markdown'; cat "$TMP/other.md"; echo '```'
    fi
  } >"$out/context.md"

  printf '判据 %s 条：✅ %s · ➖ %s · ❓ %s · ⚠️ %s\n' "$n_total" "$n_ok" "$n_na" "$n_q" "$n_warn"
  printf '产物：%s\n      %s\n' "$out/facts.md" "$out/context.md"
}

if [ "$MODE" = collect ]; then
  collect "$PR" "$OUT_DIR"
  render "$OUT_DIR" "$OUT_DIR"
else
  render "$FROM_DIR" "$OUT_DIR"
fi
