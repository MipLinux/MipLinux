#!/usr/bin/env bash
# README 的可点性检查：重写 README 最容易跑出来的不是错字，是**死链**与**死锚点**。
#
# 为什么单独一个脚本：README 是给外人看的，一个 404 的「文档导航」比没有导航更伤；
# 而 GitHub 上渲染出来才发现的死链，改起来要再来一轮 PR。这里在提交前就查掉。
#
# 查四件事：
#   1. 仓库内相对链接（`docs/x.md`、`scripts/y.sh`…）在本仓库里存在
#   2. 指向另一个仓库的绝对链接（github.com/MipLinux/...）在**本地另一份检出**里存在
#      —— 两份仓库都在这台机器上，没有理由放过
#   3. `#锚点` 在本文件里能对应到一个标题（GitHub 的 slug 规则：小写、空格换 `-`、去标点）
#   4. 进度表标记成对出现，且表头是 `| 阶段 | 状态 |`
#
# **不需要 root**，只读，不联网（外部链接只做格式检查，不抓取）。
# 用法：./scripts/check-readme-links.sh
# 退出码：0 = 干净；1 = 有死链/死锚点/标记问题。

set -euo pipefail

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)
ORG_ROOT=$(cd -- "$PROJECT_ROOT/.." && pwd)/.github

problems=0
fail() { printf '❌ %s\n' "$1"; problems=$((problems + 1)); }

# GitHub 的标题 slug：去 markdown 修饰与标点，空格换 `-`，转小写；中文原样保留。
slugify() {
  printf '%s' "$1" | sed -E \
    -e 's/\[([^]]*)\]\([^)]*\)/\1/g' \
    -e 's/[`*_]//g' \
    -e 's/[[:punct:]]//g' \
    -e 's/^[[:space:]]+|[[:space:]]+$//g' \
    -e 's/[[:space:]]+/-/g' | tr '[:upper:]' '[:lower:]'
}

check_file() { # $1=README 路径 $2=它所属仓库根
  local readme="$1" root="$2" rel
  rel=${readme#"$root"/}
  echo "── $rel"

  # 4. 标记成对
  local begin end
  begin=$(grep -c 'BEGIN:progress-table' "$readme" || true)
  end=$(grep -c 'END:progress-table' "$readme" || true)
  if [ "$begin" != "$end" ]; then
    fail "$rel 进度表标记不成对（BEGIN $begin 个 / END $end 个）"
  fi
  if grep -q 'BEGIN:progress-table' "$readme" && ! grep -q '^| 阶段 | 状态 |' "$readme"; then
    fail "$rel 有进度表标记，但表头不是「| 阶段 | 状态 |」，同步脚本会认不出来"
  fi

  # 3. 锚点
  local anchors headings
  anchors=$(grep -oE '\]\(#[^)]+\)' "$readme" | sed -E 's/\]\(#(.*)\)/\1/' | sort -u || true)
  headings=$(grep -E '^#{1,6} ' "$readme" | sed -E 's/^#{1,6} //' | while IFS= read -r h; do slugify "$h"; done | sort -u || true)
  while IFS= read -r a; do
    [ -n "$a" ] || continue
    if ! printf '%s\n' "$headings" | grep -qxF "$a"; then
      fail "$rel 锚点 #$a 在本文件里找不到对应标题（死锚点）"
    fi
  done <<<"$anchors"

  # 1+2. 链接目标
  local link
  while IFS= read -r link; do
    [ -n "$link" ] || continue
    case "$link" in
      '#'*|'mailto:'*) continue ;;
      http*)
        case "$link" in
          *github.com/MipLinux/MipLinux/blob/main/*)
            local p="${link#*blob/main/}"; p="${p%%#*}"; p="${p%%\?*}"
            [ -e "$PROJECT_ROOT/$p" ] || fail "$rel → 项目仓库里没有这个文件：$p"
            ;;
          *github.com/MipLinux/.github/blob/main/*)
            local q="${link#*blob/main/}"; q="${q%%#*}"; q="${q%%\?*}"
            [ -e "$ORG_ROOT/$q" ] || fail "$rel → 组织仓库里没有这个文件：$q"
            ;;
          *github.com/MipLinux/MipLinux/issues/*|*github.com/MipLinux/MipLinux*) ;;
          *) : ;;   # 外部站点不抓取，只保证写的是绝对链接
        esac
        ;;
      *)
        local t="${link%%#*}"
        [ -e "$root/$t" ] || fail "$rel → 仓库内死链：$t"
        ;;
    esac
  done < <(grep -oE '\]\([^)]+\)' "$readme" | sed -E 's/\]\((.*)\)/\1/' | sort -u)
}

check_file "$PROJECT_ROOT/README.md" "$PROJECT_ROOT"
check_file "$ORG_ROOT/profile/README.md" "$ORG_ROOT"
echo

if [ "$problems" -eq 0 ]; then
  echo "结论：两份 README 的链接、锚点、进度表标记都干净。"
  exit 0
fi
printf '结论：发现 %d 处问题。\n' "$problems"
exit 1
