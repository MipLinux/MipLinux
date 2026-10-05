#!/usr/bin/env bash
# 受理前质检的上下文生成器 —— **脚本只算集合，语义判断交给模型**。
#
# 为什么要有它（Issue #98）：
#   docs/work/README.md 写着「守卫查不到发出去之后的 issue……这件事只在草案阶段拦得住，发布之后靠人看」。
#   要让它自动做，先得把「确定性的事实」从 issue 正文里抠出来：哪些反引号项**真的**是仓库文件路径、
#   两条工作的「实现」有没有撞在同一个文件上。集合运算交给 LLM 会漏报，语义判断脚本又做不了，
#   所以拆开：本脚本算集合，判据质量 / 查重 / 引用有效性交给模型
#   （判据的唯一源是 docs/work/ai-review-rubric.md）。
#
# 为什么不能只靠正则（2026-10-05 实测 #97）：
#   「实现」段 62 条反引号项里**只有 25 条**是所有权，另 37 条是——
#   属性名（`Plan.keymap`）、i18n 键（`keymap.try`）、装后系统路径（`/etc/vconsole.conf`）、
#   commit hash（`1a221bd`）、`out/` 产物、纯命令（`python3 -m mipl_installer`）。
#   直接当全集用，评论会被假警报灌满。两个具体的坑：
#   · **中文名**：仓库 265 个文件里 19 个是中文名，ASCII 正则漏掉 #97 的 7 条精确命中里的 2 条；
#     所以 `git ls-files` 一律带 `-c core.quotePath=false`。
#   · **basename 静默错配**：`/etc/vconsole.conf` 会唯一匹配到 `profile/airootfs/etc/vconsole.conf`，
#     名字对得上但根本不是同一个东西 —— 所以绝对路径一律按「装后系统路径」排除，不做 basename 回退。
#
# 两个模式：
#   --issue <N>      取 GitHub 数据（要 gh 且已登录；联网）+ 本地渲染
#   --from-dir <D>   只渲染（离线），D 里放 collect 写下的那几份文本 —— 回归测试走这条
#
# 产物（写进 --out，默认 /tmp/mipl-ai-review）：
#   facts.md     确定性事实：所有权 / 未计入 / 硬撞 / 软邻近 —— 直接进评论
#   context.md   喂给模型的上下文：事实 + 正文 + 仓库树 + 其它 open task 的「实现」
#
# 不需要 root。退出码：0 = 正常；1 = 用法错误、读不到输入或 gh 失败。

set -euo pipefail
# 集合运算（comm / sort -u）必须在**同一种 collation** 下做，否则 comm 会报「输入没有被正确排序」，
# 而且报得含糊。C locale 是字节序、跨机器一致 —— 中文路径也不会因此被漏掉（只是排序位置不同）。
export LC_ALL=C

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)

MODE=""
ISSUE=""
FROM_DIR=""
OUT_DIR=${MIPL_AI_REVIEW_OUT:-/tmp/mipl-ai-review}

usage() { sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --issue)    [ $# -ge 2 ] || { echo "错误：--issue 需要一个编号" >&2; exit 1; }; MODE=collect; ISSUE=$2; shift 2 ;;
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

# ── collect：把 GitHub 上的数据落成纯文本 ────────────────────────────────────────
# 为什么落成文本而不是 JSON：仓库脚本到现在只用 bash + coreutils + git（没有一处 jq），
# 引 JSON 解析就是**新增依赖**。gh 自带的 -q 足够把数据摊平成 TSV / md。
collect() {
  local n=$1 dir=$2
  echo "── 取 GitHub 数据：issue #$n"
  mkdir -p "$dir/open-tasks"

  # author_association 只能走 REST —— `gh issue view --json` 没有这个字段（只有事件负载里有）。
  # `{owner}/{repo}` 由 gh 按当前仓库替换，不用写死仓库名。
  local assoc
  assoc=$(gh api "repos/{owner}/{repo}/issues/$n" -q .author_association 2>/dev/null || true)
  gh issue view "$n" --json number,title,labels \
      -q '[.number, .title, ([.labels[].name] | join(","))] | @tsv' \
    | awk -F'\t' -v a="$assoc" '{printf "number\t%s\ntitle\t%s\nlabels\t%s\nauthor_association\t%s\n", $1, $2, $3, a}' \
    >"$dir/meta.tsv"
  gh issue view "$n" --json body -q .body >"$dir/body.md"

  # 撞车集合只与 open 的 task 比（已关闭的路径可能已被别的 PR 删掉 —— 见 rubric A8）
  gh issue list --label task --state open --limit 50 --json number,title \
      -q '.[] | [.number, .title] | @tsv' >"$dir/open-tasks.tsv"
  while IFS=$'\t' read -r num _; do
    [ -n "$num" ] || continue
    [ "$num" = "$n" ] && continue
    gh issue view "$num" --json body -q .body >"$dir/open-tasks/$num.md"
  done <"$dir/open-tasks.tsv"

  # 查重与引用有效性要看历史（含已关闭），但只需要标题级别
  gh issue list --state all --limit 200 --json number,state,title \
      -q '.[] | [.number, .state, .title] | @tsv' >"$dir/recent.tsv"

  # 用 **HEAD 的提交树**，不用索引（`git ls-files`）：索引会被暂存的删除/改名带脏，
  # 同一个 issue 在「刚 `git rm` 过的机器」和「干净 checkout」上会算出不同的所有权集合。
  # 实测来源：#97 的 `installer/tests/test_records.py` 在主工作区索引里已消失、在 origin/main 的树里还在。
  git -C "$PROJECT_ROOT" -c core.quotePath=false ls-tree -r --name-only HEAD >"$dir/tree.txt"
  echo "   meta.tsv / body.md / open-tasks.tsv / recent.tsv / tree.txt 已就位"
}

# ── 从正文里切出「实现」段，再把它分成正向陈述与「不做」段 ──────────────────────
# 「不做」不是独立的 ### 小节，而是「实现」里的一段（#87 写「明确**不**做：…不改 `installer/**`」）。
# 若把这一段也当路径来源，那条工作会瞬间「认领」整个 installer/ —— 所以它只进排除集（rubric A5）。
split_impl() { # $1=正文文件 → 写 $2=正向 $3=排除
  local body=$1 pos=$2 neg=$3
  # 必须先清空：awk 的 `print >> file` 是**追加**、不截断 —— 不清空的话，
  # 处理第 N 条 issue 时会把前面几条的正向段累加起来，于是「每条 issue 都认领了别人的路径」。
  : >"$pos"; : >"$neg"
  awk '/^###[[:space:]]*实现/{f=1;next} /^###/{f=0} f' "$body" >"$TMP/impl.md"
  # 先按「列表项」切块：在行首是 `-` / `*` / `+` / `1.` 的行之前插一个空行。
  # 不插的话，紧凑列表（#87 的三条之间**没有空行**）会被 RS="" 当成一整段，
  # 于是「明确不做」那条跟着第一条一起被算成正向，明说「不动 profile/pacman.conf」也照样进了所有权（实测踩到）。
  awk '{ if ($0 ~ /^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]/) print ""; print }' \
    "$TMP/impl.md" >"$TMP/impl.blocks.md"
  # 段落模式：**段首**是「不做 / 不碰 / 不动」才算排除段。
  # 判段首之前要剥掉 markdown 的行首标记：`**不做**：`（#97）与 `- 明确**不**做：`（#87）都得认出来 ——
  # 少剥一个 `-`，整段就被当成正向，#87 里明说「不动 profile/pacman.conf」的那条会漏进所有权（实测踩到）。
  # 不能只看段里出现过这三个字：实测 #97 的 ⑥ 段引用了文档小节名「明确不做」，
  # 那样整段会被误判成排除段，把它自己认领的 5 条路径全削掉（rubric A5 的反面）。
  awk -v p="$pos" -v n="$neg" 'BEGIN{RS="";ORS="\n"} {
      h=$0; sub(/\n.*/,"",h); gsub(/[-*+0-9.[:space:]]/,"",h)
      if (h ~ /^(明确)?不(做|碰|动)/) print >> n; else print >> p
    }' "$TMP/impl.blocks.md"
}

items_of() { grep -o '`[^`]*`' "$1" 2>/dev/null | tr -d '`' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' | sort -u || true; }

# ── 分类：一条反引号项到底是「所有权」还是别的什么 ──────────────────────────────
# 输出 `<kind>\t<值>`；kind ∈ exact / basename / from-command / ignored / unresolved
classify() { # $1=item  $2=tree  $3=basename 索引  $4=目录集合
  local it=$1 tree=$2 bybase=$3 dirs=$4 base cnt tok pdir
  case "$it" in
    '') return 0 ;;
    *'{{'*|*'<'*'>'*) printf 'ignored\t模板占位\n'; return 0 ;;
  esac
  # 先排掉「长得像路径但不是」的那几类 —— 顺序有意：hash 与 issue 引用会骗过 basename 回退
  if printf '%s' "$it" | grep -Eq '^[0-9a-f]{7,64}$'; then printf 'ignored\tcommit / sha256\n'; return 0; fi
  if printf '%s' "$it" | grep -Eq '^#[0-9]+$'; then printf 'ignored\tissue 引用\n'; return 0; fi
  # 绝对路径一律按装后系统路径 —— `/etc/vconsole.conf` 不许回退到 profile 里那个同名文件（静默错配）
  if printf '%s' "$it" | grep -Eq '^/'; then printf 'ignored\t装后系统路径\n'; return 0; fi
  # 通配 / 目录范围不是「一个文件」，别当新建文件算（`renderer/i18n/*.json` 这种）
  if printf '%s' "$it" | grep -Eq '[*?]'; then printf 'ignored\t通配 / 目录范围\n'; return 0; fi
  case "$it" in
    out/*|*.iso|*.qcow2|*.fd) printf 'ignored\t构建产物\n'; return 0 ;;
    */) printf 'ignored\t目录范围\n'; return 0 ;;
  esac
  if grep -Fxq -- "$it" "$tree"; then printf 'exact\t%s\n' "$it"; return 0; fi
  base=${it##*/}
  cnt=$(awk -F'\t' -v b="$base" '$1==b{c++} END{print c+0}' "$bybase")
  if [ "$cnt" -eq 1 ]; then printf 'basename\t%s\n' "$(awk -F'\t' -v b="$base" '$1==b{print $2; exit}' "$bybase")"; return 0; fi
  # 「命令 + 参数」：剥掉参数再试一次（#97 的 `tools/i18n.py --write` 里藏着一条真路径）
  if printf '%s' "$it" | grep -q ' '; then
    tok=${it%% *}
    if grep -Fxq -- "$tok" "$tree"; then printf 'from-command\t%s\n' "$tok"; return 0; fi
    base=${tok##*/}
    cnt=$(awk -F'\t' -v b="$base" '$1==b{c++} END{print c+0}' "$bybase")
    if [ "$cnt" -eq 1 ]; then printf 'from-command\t%s\n' "$(awk -F'\t' -v b="$base" '$1==b{print $2; exit}' "$bybase")"; return 0; fi
    printf 'ignored\t命令 / 散文\n'; return 0
  fi
  # A4：树里没有、但**父目录在树里** → 新建候选，不是「找不到」。
  # 这条不能省：#98 与 #99 都点名了同一个新文件 docs/work/ai-review-rubric.md，
  # 若新建文件一律判成 unresolved，这两条工作的真撞车就报不出来。
  # 反过来，没有 `/` 的项（`Plan.keymap` / `keymap.try` / `HOSTNAME_RE`）不算新建候选 —— 它们不是路径。
  if printf '%s' "$it" | grep -q '/'; then
    pdir=${it%/*}
    if grep -qxF -- "$pdir" "$dirs"; then printf 'new\t%s\n' "$it"; return 0; fi
  fi
  printf 'unresolved\t%s\n' "$it"
}

# ── 一条 issue 的所有权集合 ────────────────────────────────────────────────────
# 写 $2：`<path>\t<kind>`；$3：未计入明细；$4：排除集。$5=标记（"task" 或别的）
ownership_of() { # $1=正文 $2=out.tsv $3=ignored.tsv $4=excluded.tsv $5=tree $6=bybase $7=dirs
  local body=$1 out=$2 ign=$3 exc=$4 tree=$5 bybase=$6 dirs=$7
  : >"$out"; : >"$ign"; : >"$exc"
  split_impl "$body" "$TMP/pos.md" "$TMP/neg.md"
  local it kind val
  while IFS= read -r it; do
    [ -n "$it" ] || continue
    IFS=$'\t' read -r kind val < <(classify "$it" "$tree" "$bybase" "$dirs") || true
    case "$kind" in
      exact|basename|from-command) printf '%s\t%s\n' "$val" "$kind" >>"$out" ;;
      new) printf '%s\t新建\n' "$val" >>"$out" ;;
      unresolved) printf '%s\t未解析\n' "$it" >>"$ign" ;;
      *) printf '%s\t%s\n' "$it" "$val" >>"$ign" ;;
    esac
  done < <(items_of "$TMP/pos.md")
  while IFS= read -r it; do
    [ -n "$it" ] || continue
    IFS=$'\t' read -r kind val < <(classify "$it" "$tree" "$bybase" "$dirs") || true
    case "$kind" in
      exact|basename|from-command|new) printf '%s\n' "$val" >>"$exc" ;;
      *) printf '%s\n' "$it" >>"$exc" ;;
    esac
  done < <(items_of "$TMP/neg.md")
  # 排除集用于**削减**所有权：排除项本身、以及 `dir/**` 形态的前缀
  sort -u -o "$exc" "$exc"
  if [ -s "$exc" ]; then
    awk -F'\t' -v OFS='\t' '
      NR==FNR { if ($0 ~ /\*\*$/) { p=$0; sub(/\*\*$/,"",p); pre[++n]=p } else exact[$0]=1; next }
      { drop=0
        if (exact[$1]) drop=1
        for (i=1;i<=n;i++) if (index($1, pre[i])==1) drop=1
        if (!drop) print }
    ' "$exc" "$out" >"$TMP/kept.tsv"
    mv "$TMP/kept.tsv" "$out"
  fi
  sort -u -o "$out" "$out"
  # 同一个文件可能被两种写法各解析一次（#87 的 `profile/airootfs/etc/pacman.d/mirrorlist-archlinuxcn`
  # 既以全路径出现、又以裸名出现）→ 按路径去重，保留证据最强的那种 kind。
  awk -F'\t' '{ r = ($2=="exact" ? 1 : ($2=="from-command" ? 2 : ($2=="basename" ? 3 : 4)))
                if (!($1 in best) || r < best[$1]) { best[$1] = r; line[$1] = $0 } }
              END { for (p in line) print line[p] }' "$out" | LC_ALL=C sort >"$TMP/dedup.tsv"
  mv "$TMP/dedup.tsv" "$out"
  sort -u -o "$ign" "$ign"
}

# ── render：把事实写成两份 markdown ────────────────────────────────────────────
render() {
  local dir=$1 out=$2
  local tree="$dir/tree.txt" bybase="$TMP/bybase.tsv"
  for f in meta.tsv body.md tree.txt; do
    [ -f "$dir/$f" ] || { echo "错误：读不到 $dir/$f（先用 --issue <N> 取数据，或检查 --from-dir）" >&2; exit 1; }
  done
  awk -F/ 'NF>1{print $NF"\t"$0}' "$tree" | LC_ALL=C sort >"$bybase"
  # 所有祖先目录（新建候选的判据：父目录在树里就算「新建」而不是「找不到」）
  awk -F/ 'NF>1 { s=""; for (i=1;i<NF;i++) s = (i==1 ? $i : s"/"$i); print s }' "$tree" \
    | LC_ALL=C sort -u >"$TMP/dirs.txt"

  local number title labels assoc
  number=$(awk -F'\t' '$1=="number"{print $2}' "$dir/meta.tsv")
  title=$(awk -F'\t' '$1=="title"{print $2}' "$dir/meta.tsv")
  labels=$(awk -F'\t' '$1=="labels"{print $2}' "$dir/meta.tsv")
  assoc=$(awk -F'\t' '$1=="author_association"{print $2}' "$dir/meta.tsv")

  local is_task=0
  case ",$labels," in *,task,*) is_task=1 ;; esac

  ownership_of "$dir/body.md" "$TMP/own.tsv" "$TMP/ign.tsv" "$TMP/exc.tsv" "$tree" "$bybase" "$TMP/dirs.txt"
  local n_own n_ign n_new
  n_own=$(wc -l <"$TMP/own.tsv")
  n_ign=$(wc -l <"$TMP/ign.tsv")
  n_new=$(awk -F'\t' '$2=="新建"{c++} END{print c+0}' "$TMP/own.tsv")

  # ── 硬撞 / 软邻近：只与其它 open task 比
  : >"$TMP/hard.tsv"; : >"$TMP/soft.tsv"
  if [ "$is_task" = 1 ] && [ -f "$dir/open-tasks.tsv" ] && [ -d "$dir/open-tasks" ]; then
    local num other_own other_ign other_exc
    while IFS=$'\t' read -r num _; do
      [ -n "$num" ] || continue
      [ "$num" = "$number" ] && continue
      [ -f "$dir/open-tasks/$num.md" ] || continue
      ownership_of "$dir/open-tasks/$num.md" "$TMP/o.tsv" "$TMP/oi.tsv" "$TMP/oe.tsv" "$tree" "$bybase" "$TMP/dirs.txt"
      # 硬撞：同一个文件
      comm -12 <(cut -f1 "$TMP/own.tsv" | LC_ALL=C sort -u) <(cut -f1 "$TMP/o.tsv" | LC_ALL=C sort -u) \
        | sed "s/$/\t#$num/" >>"$TMP/hard.tsv"
      # 软邻近：同一目录、但不是硬撞。硬撞文件所在的目录不再单独报 ——
      # 「同一个文件撞了」已经蕴含「同一个目录」，再报一次是纯噪音（rubric §7 短是硬要求）。
      #
      # 这里**不能**写成一条长管道：`grep -v` 在一条都没选中时返回 1，配上 `set -o pipefail`
      # 会把整个脚本带崩 —— 只有在「两个 issue 没有任何共同目录」时才触发（实测 #97↔#99 撞上）。
      # 所以显式判空、每步 `|| true`。
      comm -12 \
        <(awk -F'\t' '$1 ~ /\//{p=$1; sub(/\/[^\/]*$/,"",p); print p}' "$TMP/own.tsv" | LC_ALL=C sort -u) \
        <(awk -F'\t' '$1 ~ /\//{p=$1; sub(/\/[^\/]*$/,"",p); print p}' "$TMP/o.tsv"  | LC_ALL=C sort -u) \
        >"$TMP/dirs.tsv" || true
      cut -f1 "$TMP/hard.tsv" | sed 's|/[^/]*$||' | LC_ALL=C sort -u >"$TMP/harddirs.tsv" || true
      if [ -s "$TMP/dirs.tsv" ]; then
        if [ -s "$TMP/harddirs.tsv" ]; then
          grep -vxF -f "$TMP/harddirs.tsv" "$TMP/dirs.tsv" >"$TMP/dirs.soft.tsv" || true
        else
          cp "$TMP/dirs.tsv" "$TMP/dirs.soft.tsv"
        fi
        sed "s|\$|\t#$num|" "$TMP/dirs.soft.tsv" >>"$TMP/soft.tsv"
      fi
    done <"$dir/open-tasks.tsv"
    sort -u -o "$TMP/hard.tsv" "$TMP/hard.tsv"
    sort -u -o "$TMP/soft.tsv" "$TMP/soft.tsv"
  fi
  local n_hard n_soft
  n_hard=$(wc -l <"$TMP/hard.tsv"); n_soft=$(wc -l <"$TMP/soft.tsv")

  # ── facts.md：确定性的那部分，直接进评论
  {
    echo "## 受理前质检（机器 · issue #$number · 正文 $(sha256sum "$dir/body.md" | cut -c1-8)）"
    echo
    if [ "$is_task" != 1 ]; then
      echo "**所有权雷达** ➖ 跳过：本 issue 的 label 是「${labels:-无}」，没有「实现」段（rubric §0.2 按 label 分流）。"
    else
      if [ "$n_own" -eq 0 ]; then
        # 「认领 0 个文件 · 硬撞 0」会被读成「查过了，没重叠」—— 而实际是压根没法判。
        # 这两件事必须一眼分得开（rubric §9 的反例断言）。
        echo "**所有权雷达** ⚠️ 无法判定：「实现」段里没有解析出任何仓库文件路径。"
        echo
        echo "（这**不等于**「查过了、没有重叠」—— 是判不了。）"
      else
        if [ "$n_new" -gt 0 ]; then
          echo "**所有权雷达** 认领 $n_own 个文件（其中 $n_new 个是新建）· 硬撞 $n_hard · 软邻近 $n_soft"
        else
          echo "**所有权雷达** 认领 $n_own 个文件 · 硬撞 $n_hard · 软邻近 $n_soft"
        fi
      fi
      if [ "$n_hard" -gt 0 ]; then
        echo "🔴 **硬撞**（同一条工作线上的两条会在同一个文件上改，撞上就只能整份重建才能验证）："
        while IFS=$'\t' read -r p who; do echo "- \`$p\` —— **$who** 的「实现」里也点了它"; done <"$TMP/hard.tsv"
        echo
      fi
      if [ "$n_soft" -gt 0 ]; then
        echo "🟡 软邻近（同一目录，未撞同一文件）："
        while IFS=$'\t' read -r d who; do echo "- \`$d/\` —— **$who** 也在改这个目录"; done <"$TMP/soft.tsv"
        echo
      fi
      if [ "$n_ign" -gt 0 ]; then
        echo "<details><summary>解析回显：另有 $n_ign 项未计入所有权（点开看机器人忽略了什么）</summary>"
        echo
        while IFS=$'\t' read -r it why; do echo "- \`$it\` —— $why"; done <"$TMP/ign.tsv"
        echo
        echo "</details>"
      fi
      if [ "$n_own" -gt 0 ]; then
        # 认领清单也要回显：机器人对「这条工作要改哪些文件」的理解必须可被纠正（rubric §3.3）
        echo "<details><summary>我认领了这 $n_own 个文件（解析回显：精确 / 裸名解析 / 从命令里剥出）</summary>"
        echo
        while IFS=$'\t' read -r p kind; do echo "- \`$p\` —— $kind"; done <"$TMP/own.tsv"
        echo
        echo "</details>"
      fi
      if [ -s "$TMP/exc.tsv" ]; then
        # 「不做」段被当成了什么也要看得见 —— 否则「少认领了」和「多认领了」都查不出来
        echo "<details><summary>按「不做 / 不碰 / 不动」段排除的 $(wc -l <"$TMP/exc.tsv") 项</summary>"
        echo
        while IFS= read -r x; do echo "- \`$x\`"; done <"$TMP/exc.tsv"
        echo
        echo "</details>"
      fi
    fi
    # 免责声明与作者关联**不写在这里**：facts.md 只是评论的前半段，免责要落在整条评论的末尾，
    # 由 workflow 拼装时追加。写在这里会让它插在模型那三块前面。
  } >"$out/facts.md"

  # ── context.md：喂给模型的上下文
  {
    echo "# 受理前质检的上下文"
    echo
    echo "## 主体 issue #$number"
    echo "- 标题：$title"
    echo "- labels：${labels:-（无）}"
    echo "- author_association：${assoc:-未知}"
    echo
    echo '### 正文'
    echo '```markdown'
    cat "$dir/body.md"
    echo '```'
    echo
    echo "## 脚本已经算好的确定性事实（**不要重算，也不要推翻**）"
    echo '```markdown'
    cat "$out/facts.md"
    echo '```'
    echo
    echo "## 仓库树（git ls-files，$(( $(wc -l <"$tree") )) 条）"
    echo '```'
    cat "$tree"
    echo '```'
    echo
    if [ "$is_task" = 1 ] && [ -f "$dir/open-tasks.tsv" ]; then
      echo "## 其它 open task issue 的「实现 / 不做」段（撞车集合的来源）"
      while IFS=$'\t' read -r num t; do
        [ -n "$num" ] || continue
        [ "$num" = "$number" ] && continue
        [ -f "$dir/open-tasks/$num.md" ] || continue
        echo "### #$num $t"
        split_impl "$dir/open-tasks/$num.md" "$TMP/p.md" "$TMP/n.md"
        echo '```markdown'
        echo '[实现 · 正向]'; cat "$TMP/p.md"
        echo '[实现 · 不做]'; cat "$TMP/n.md"
        echo '```'
      done <"$dir/open-tasks.tsv"
      echo
    fi
    if [ -f "$dir/recent.tsv" ]; then
      echo "## 历史 issue（含已关闭，最新在前；查重用）"
      echo '```'
      cat "$dir/recent.tsv"
      echo '```'
    fi
  } >"$out/context.md"

  printf '所有权 %s 条 · 未计入 %s 条 · 硬撞 %s · 软邻近 %s\n' "$n_own" "$n_ign" "$n_hard" "$n_soft"
  printf '产物：%s\n' "$out/facts.md"
  printf '      %s\n' "$out/context.md"
}

if [ "$MODE" = collect ]; then
  collect "$ISSUE" "$OUT_DIR"
  render "$OUT_DIR" "$OUT_DIR"
else
  render "$FROM_DIR" "$OUT_DIR"
fi
