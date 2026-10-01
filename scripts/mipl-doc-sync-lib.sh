#!/usr/bin/env bash
# 两个仓库之间「进度表那一格」的规范变换 —— 由 check-doc-sync.sh 与 sync-profile-progress.sh 共用。
#
# 为什么必须共用：组织主页是**另一个仓库**，所以它那一格里的仓库内相对链接（`docs/x.md`）
# 点了是 404，必须写成指向项目仓库的绝对链接；而 Issue 链接又只该出现一次。
# 于是「项目侧那一格」与「主页那一格」在**链接形态**上必然不同 —— 但语义必须完全相同。
# 规则写两份就会漂，所以只写在这里一份：同步脚本用它生成，守卫用它比对，谁也别自己实现一遍。
#
# 这里只做**形态**变换，不做缩写、不改措辞：
#   1. `(docs/…)` 这类仓库内相对链接 → `(https://github.com/MipLinux/MipLinux/blob/main/…)`
#      （已经是 http(s) 绝对链接的、纯锚点 `#…` 的、站内绝对路径 `/…` 的都不动）
#   2. `见 [Issue #23](…)` 与 `（[Issue #23](…)）` → 统一成 `（Issue #23）`，避免同一链接写两遍
#
# 用法（在脚本里）：
#   . "$SELF_DIR/mipl-doc-sync-lib.sh"
#   canonical_cell "$cell"
# 不允许 set -e 之外的特殊环境；本文件只定义函数与常量。

# 项目仓库在 GitHub 上的位置：换仓库/换默认分支只需要改这两行。
MIPL_REPO_SLUG="MipLinux/MipLinux"
MIPL_REPO_BRANCH="main"
MIPL_REPO_BLOB="https://github.com/${MIPL_REPO_SLUG}/blob/${MIPL_REPO_BRANCH}"

# 把一格进度状态规范成「组织主页该有的样子」。
canonical_cell() {
  sed -E \
    -e "s@\]\(([^)#/][^):]*)\)@](${MIPL_REPO_BLOB}/\1)@g" \
    -e 's@见 \[(Issue #[0-9]+)\]\([^)]*\)@\1@g' \
    -e 's@（\[(Issue #[0-9]+)\]\([^)]*\)）@（\1）@g' \
    -e 's@\[(Issue #[0-9]+)\]\([^)]*\)@（\1）@g'
}

# 比较用的归一化：去链接目标、去强调与代码符号、去所有空白。
# 两格允许在 markdown 修饰上不同（`**M0**` 对 `M0`），不允许在文字与状态上不同。
normalize_cell() {
  sed -E \
    -e 's/\[([^]]*)\]\([^)]*\)/\1/g' \
    -e 's/[`*_]//g' \
    -e 's/<[^>]*>//g' \
    -e 's/[[:space:]]//g'
}

# 抽 README 里「阶段 | 状态」表的行，输出 `阶段<TAB>状态`。
# 优先找 `<!-- BEGIN:progress-table -->` 标记；没有标记时退回「第一张以 `| 阶段 |` 开头的表」。
# 只认第一张这样的表：项目 README 的进度表之后还有别的表，不能一路吞下去。
extract_progress_table() { # $1=文件
  awk '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    /<!--[[:space:]]*BEGIN:progress-table[[:space:]]*-->/ { inmark = 1; next }
    /<!--[[:space:]]*END:progress-table[[:space:]]*-->/ { inmark = 0; next }
    inmark && /^\|[[:space:]]*阶段[[:space:]]*\|/ { intable = 1; next }
    inmark && intable && /^\|[[:space:]]*-+/ { next }
    inmark && intable && /^\|/ {
      n = split($0, c, "|")
      if (n >= 4) { print trim(c[2]) "\t" trim(c[3]) }
      next
    }
    inmark && intable { next }
    !inmark && /^\|[[:space:]]*阶段[[:space:]]*\|/ { intable = 2; next }
    intable == 2 && /^\|[[:space:]]*-+/ { next }
    intable == 2 && /^\|/ {
      n = split($0, c, "|")
      if (n >= 4) { print trim(c[2]) "\t" trim(c[3]) }
      next
    }
    intable == 2 { exit }
  ' "$1"
}

# 抽进度表的整块（表头 + 分隔行 + 数据行），供同步脚本替换使用。
extract_progress_block() { # $1=文件
  awk '
    /<!--[[:space:]]*BEGIN:progress-table[[:space:]]*-->/ { inmark = 1; next }
    /<!--[[:space:]]*END:progress-table[[:space:]]*-->/ { inmark = 0; next }
    inmark && /^\|/ { print; next }
    inmark { next }
    /^\|[[:space:]]*阶段[[:space:]]*\|/ { intable = 1 }
    intable {
      if ($0 !~ /^\|/) exit
      print
    }
  ' "$1"
}
