#!/usr/bin/env bash
# PR 代码审查上下文生成器 —— 提取 git diff、计算机械信号、组装模型输入。
#
# 用法：
#   ./scripts/pr-review-context.sh --pr <N> [--out <DIR>]    # 联网取 GitHub PR 数据与 diff
#   ./scripts/pr-review-context.sh --dry-run [--out <DIR>]  # 离线比对本地分支与 main 的 diff（用于自检与回归测试）
#
# 产物（写入 --out，默认 /tmp/mipl-pr-review）：
#   meta.tsv       PR 基础元数据（pr号、head、base、标题等）
#   context.md     组装好、喂给 DeepSeek 的完整上下文（含带行号的 diff 与机械告警）
#
# 不需要 root。退出码：0 = 正常；1 = 参数错误或执行失败。

set -euo pipefail
export LC_ALL=C

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)

MODE=""
PR=""
DRY_RUN=false
OUT_DIR=${MIPL_PR_REVIEW_OUT:-/tmp/mipl-pr-review}

usage() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --pr)
      [ $# -ge 2 ] || { echo "错误：--pr 需要一个编号" >&2; exit 1; }
      MODE=pr
      PR=$2
      shift 2
      ;;
    --dry-run)
      MODE=dryrun
      DRY_RUN=true
      shift
      ;;
    --out)
      [ $# -ge 2 ] || { echo "错误：--out 需要一个目录" >&2; exit 1; }
      OUT_DIR=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "错误：不认识参数 $1（见 --help）" >&2
      exit 1
      ;;
  esac
done

[ -n "$MODE" ] || { usage; exit 1; }

mkdir -p "$OUT_DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# 带行号解析 git diff，便于模型精准输出 line
annotate_diff() {
  local diff_file=$1
  awk '
    /^diff --git / {
      file = $3; sub(/^a\//, "", file);
      print "\n========================================================";
      print "文件: " file;
      print "========================================================";
      in_hunk = 0;
      next;
    }
    /^@@ / {
      # 匹配 @@ -old,len +new,len @@
      split($3, arr, ",");
      new_line = substr(arr[1], 2) + 0;
      in_hunk = 1;
      print $0;
      next;
    }
    in_hunk {
      if ($0 ~ /^\+/) {
        printf "[L%d] %s\n", new_line, $0;
        new_line++;
      } else if ($0 ~ /^-/) {
        print $0;
      } else {
        printf "[L%d] %s\n", new_line, $0;
        new_line++;
      }
    }
  ' "$diff_file"
}

# 提取代码中明显的违规特征（机械信号）
detect_mechanical_signals() {
  local diff_file=$1
  local signals=()

  # 1. 检查新增行是否有裸调底层命令 (pacstrap, mkarchiso, qemu-system-)
  local raw_cmds
  raw_cmds=$(grep -En '^\+[[:space:]]*(sudo[[:space:]]+)?(pacstrap|mkarchiso|qemu-system-[a-z0-9_]+)' "$diff_file" || true)
  if [ -n "$raw_cmds" ]; then
    signals+=("发现直接调用底层构建/虚拟机工具（违反命令封装红线）：\n$raw_cmds")
  fi

  # 2. 检查新增行是否有裸 sudo
  local raw_sudo
  raw_sudo=$(grep -En '^\+[[:space:]]*sudo[[:space:]]+' "$diff_file" || true)
  if [ -n "$raw_sudo" ]; then
    signals+=("发现脚本中调用 sudo（违反权限红线，应走 mipl.sh 或经 pkexec 并捕获 126/127）：\n$raw_sudo")
  fi

  # 3. 检查是否有明确未加双引号的高危变量裸用（如 rm -rf $OUT_DIR 或 cd $TARGET）
  local unquoted_vars
  unquoted_vars=$(grep -En '^\+[[:space:]]*(rm|cp|mv|cd|cat)[[:space:]]+[^\"'\''#]*\$(TARGET|OUT_DIR|IMAGE|FILE)([[:space:]]|$)' "$diff_file" || true)
  if [ -n "$unquoted_vars" ]; then
    signals+=("发现文件操作命令中路径变量未加双引号保护（工程质量隐患）：\n$unquoted_vars")
  fi

  if [ ${#signals[@]} -eq 0 ]; then
    echo "未检测到明显的显式机械违规特征。"
  else
    local s
    for s in "${signals[@]}"; do
      echo -e "- ⚠️ $s"
    done
  fi
}

echo "── 运行模式：$MODE"

if [ "$MODE" = "pr" ]; then
  echo "正在获取 PR #$PR 数据..."
  gh pr view "$PR" --json number,title,headRefOid,baseRefName,body \
    -q '[.number, .title, .headRefOid, .baseRefName] | @tsv' \
    | awk -F'\t' '{printf "number\t%s\ntitle\t%s\nhead\t%s\nbase\t%s\n", $1, $2, $3, $4}' \
    >"$OUT_DIR/meta.tsv"

  gh pr view "$PR" --json body -q .body >"$TMP/pr-body.md"
  gh pr diff "$PR" >"$TMP/raw.diff"
else
  # dry-run 模式：比对当前分支与 main
  BASE_REF=$(git -C "$PROJECT_ROOT" merge-base HEAD origin/main 2>/dev/null || git -C "$PROJECT_ROOT" merge-base HEAD main 2>/dev/null || echo "HEAD~1")
  HEAD_OID=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
  BRANCH_NAME=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD)

  printf "number\tdry-run\ntitle\t本地分支自检 (%s)\nhead\t%s\nbase\t%s\n" \
    "$BRANCH_NAME" "$HEAD_OID" "$BASE_REF" >"$OUT_DIR/meta.tsv"

  echo "本地测试 PR 描述（Dry-run 模式）" >"$TMP/pr-body.md"
  git -C "$PROJECT_ROOT" diff "$BASE_REF" >"$TMP/raw.diff"
fi

# 过滤不需要审查的文件类型（例如二进制、out/ 产物等）
grep -vE '^diff --git a/(out/|\.idea/)' "$TMP/raw.diff" >"$TMP/filtered.diff" || true

# 生成带行号的 diff
annotate_diff "$TMP/filtered.diff" >"$TMP/annotated.diff"

# 提取机械信号
SIGNALS=$(detect_mechanical_signals "$TMP/filtered.diff")

# 组装 context.md
{
  echo "# PR 代码审查上下文"
  echo
  echo "## PR 基本信息"
  echo "- **PR**: $(awk -F'\t' '$1=="number"{print $2}' "$OUT_DIR/meta.tsv")"
  echo "- **标题**: $(awk -F'\t' '$1=="title"{print $2}' "$OUT_DIR/meta.tsv")"
  echo "- **Head SHA**: $(awk -F'\t' '$1=="head"{print $2}' "$OUT_DIR/meta.tsv")"
  echo "- **Base Ref**: $(awk -F'\t' '$1=="base"{print $2}' "$OUT_DIR/meta.tsv")"
  echo
  echo "## PR 正文"
  cat "$TMP/pr-body.md"
  echo
  echo "## 机械信号初筛"
  echo "$SIGNALS"
  echo
  echo "## 代码变更 Diff（含 [L行号] 标记）"
  cat "$TMP/annotated.diff"
} >"$OUT_DIR/context.md"

echo "✅ 上下文生成完成：$OUT_DIR/context.md"
