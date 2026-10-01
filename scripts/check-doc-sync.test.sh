#!/usr/bin/env bash
# check-doc-sync.sh 的回归测试：造一份夹具，逐个把「漂」的情形塞进去，看它抓不抓得住。
#
# 为什么有它：一个「永远说 OK」的守卫比没有守卫更坏 —— 它会让人以为同步是自动的。
# 所以守卫本身也要有实测证据：基线必须通过，每一种漂移必须被抓到并点名。
# 夹具全部在临时目录里，**不碰真实仓库**（同步脚本会真的写盘，所以测试只对它跑 --dry-run）。
#
# 夹具的构造原则：**不依赖 README 的具体措辞与版式**。
# 2026-10-01 重写 README 时，T2/T3 因为靠 `sed` 改某一行旧文案而假失败 ——
# 断言应该盯「机制」（标记块、提交时间、副本头），不盯「当时那句话怎么写」。
#
# **不需要 root**。用法：./scripts/check-doc-sync.test.sh
# 退出码：0 = 全过；1 = 有失败项。

set -uo pipefail

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SELF_DIR/.." && pwd)
ORG_SOURCE=$(cd -- "$PROJECT_ROOT/.." && pwd)/.github
# shellcheck source=mipl-doc-sync-lib.sh
. "$SELF_DIR/mipl-doc-sync-lib.sh"

FAIL=0
pass() { printf '✅ %s\n' "$1"; }
bad()  { printf '❌ %s\n' "$1"; FAIL=1; }

[ -f "$ORG_SOURCE/profile/README.md" ] || { echo "错误：找不到并列的组织仓库 $ORG_SOURCE" >&2; exit 1; }

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/repo" "$T/.github"
(cd "$PROJECT_ROOT" && tar -c --exclude=.git .) | tar -x -C "$T/repo"
(cd "$ORG_SOURCE" && tar -c --exclude=.git .)     | tar -x -C "$T/.github"

CHECK="$T/repo/scripts/check-doc-sync.sh"
SYNC="$T/repo/scripts/sync-profile-progress.sh"
ORG_README="$T/.github/profile/README.md"

git -C "$T/repo" init -q
git -C "$T/repo" -c user.email=t@t -c user.name=t add -A
# 夹具的提交日期取真源 README 进度表的「截至」日期：守卫的新鲜度检查就是拿这两个数比，
# 夹具取「今天」会让基线本身判漂移 —— 那一次是夹具错、守卫对（2026-10-01 头一回跑就撞上了）。
STAMP=$(grep -oE '截至 \*\*[0-9]{4}-[0-9]{2}-[0-9]{2}\*\*' "$T/repo/README.md" | head -1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')
if [ -z "$STAMP" ]; then
  echo "错误：夹具的项目 README 里没有「截至 **YYYY-MM-DD**」—— 守卫的第一个检查就没法做" >&2
  exit 1
fi
GIT_AUTHOR_DATE="${STAMP}T12:00:00+08:00" GIT_COMMITTER_DATE="${STAMP}T12:00:00+08:00" \
  git -C "$T/repo" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm fixture
# 记下基线提交：复位时要连**提交历史**一起退回，否则 T3 造的未来提交会活到 T7
# （2026-10-01 第三次踩到：T7 的同步被 T3 的 2099 提交判成「真源过期」而回滚）。
BASE_COMMIT=$(git -C "$T/repo" rev-parse HEAD)

# 把组织主页恢复成「出厂状态」：每个用例从干净状态出发，否则前一个用例的改动会污染后一个。
# 表的内容退回占位状态 —— 这里测的是守卫，不是「同步脚本有没有填过表」。
reset_all() {
  # 项目仓库：退回基线提交、清掉未提交改动与新文件。
  # 夹具在 $T 这个临时目录里，`reset --hard` 只影响它 —— 真实仓库一个字都碰不到。
  git -C "$T/repo" -c core.hooksPath=/dev/null reset -q --hard "$BASE_COMMIT" 2>/dev/null || true
  git -C "$T/repo" -c core.hooksPath=/dev/null clean -qfd 2>/dev/null || true
  # 组织主页：还原成真实那份（**表格保留原样** —— 基线必须是「真实状态」，
  # 2026-10-01 我在复位里顺手把表清成占位，结果 T1 基线自己就少了七行，白查了一轮）
  cp "$ORG_SOURCE/profile/README.md" "$ORG_README"
}

# 把组织主页的进度表清成「占位」状态（只有表头与分隔行）—— 只有 T6/T7 需要这个前置条件。
blank_org_table() {
  awk '
    /<!--[[:space:]]*BEGIN:progress-table[[:space:]]*-->/ {
      print; print "| 阶段 | 状态 |"; print "|---|---|"; skip = 1; next
    }
    /<!--[[:space:]]*END:progress-table[[:space:]]*-->/ { print; skip = 0; next }
    !skip { print }
  ' "$ORG_README" >"$ORG_README.tmp" && mv "$ORG_README.tmp" "$ORG_README"
  grep -q 'END:progress-table' "$ORG_README" || { echo "错误：清表时把 END 标记吃掉了" >&2; exit 1; }
}

echo "── T1 基线：真实内容必须判为一致"
reset_all
if "$CHECK" >"$T/t1.log" 2>&1; then pass "T1 一致"; else bad "T1 误报漂移"; cat "$T/t1.log"; fi

echo "── T2 组织主页残留旧口径"
reset_all
# 结构化注入：把旧口径塞进正文，不依赖当时那句话是怎么写的。
printf '\n> 安装器的界面尚未接后端，修复后的 ISO 待重建。\n' >>"$ORG_README"
if "$CHECK" >"$T/t2.log" 2>&1; then bad "T2 旧口径没被抓到"; else
  grep -q '已被推翻的口径' "$T/t2.log" && pass "T2 抓到旧口径残留" || { bad "T2 报错内容不对"; cat "$T/t2.log"; }
fi

echo "── T3 真源落后于仓库提交"
reset_all
# 用一个**明确的未来日期**做提交：不要拿「今天」跟真源日期赛跑 —— 真源日期一旦推到今天，
# `stamp < last` 就不再成立，测试会假失败（2026-10-01 第二次踩到）。
GIT_AUTHOR_DATE="2099-01-01T10:00:00+08:00" GIT_COMMITTER_DATE="2099-01-01T10:00:00+08:00" \
  git -C "$T/repo" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -q --allow-empty -m "未来的一次提交"
if "$CHECK" >"$T/t3.log" 2>&1; then bad "T3 真源过期没被抓到"; else
  grep -q '有新进展没写进进度表' "$T/t3.log" && pass "T3 抓到真源过期" || { bad "T3 报错内容不对"; cat "$T/t3.log"; }
fi

echo "── T4 共享文件副本漂移"
reset_all
printf '\n# 多出来的一行\n' >>"$T/repo/.github/ISSUE_TEMPLATE/bug-report.yml"
if "$CHECK" >"$T/t4.log" 2>&1; then bad "T4 副本漂移没被抓到"; else
  grep -q 'bug-report.yml 两边内容不一致' "$T/t4.log" && pass "T4 抓到副本漂移" || { bad "T4 报错内容不对"; cat "$T/t4.log"; }
fi

echo "── T5 组织仓库路径不存在"
reset_all
if "$CHECK" --org "$T/nope" >"$T/t5.log" 2>&1; then bad "T5 路径不存在却返回 0"; else
  grep -q '读不到' "$T/t5.log" && pass "T5 明确报错" || { bad "T5 错误信息不对"; cat "$T/t5.log"; }
fi

echo "── T6 --dry-run 不许落盘"
reset_all
blank_org_table       # 占位状态才看得出「有没有落盘」
before=$(md5sum "$ORG_README" | cut -d' ' -f1)
"$SYNC" --dry-run >/dev/null 2>&1 || true
after=$(md5sum "$ORG_README" | cut -d' ' -f1)
[ "$before" = "$after" ] && pass "T6 --dry-run 没落盘" || bad "T6 --dry-run 改了文件"

echo "── T7 同步脚本必须真能把占位表填上，并自校验通过"
reset_all
blank_org_table
if "$SYNC" >"$T/t7.log" 2>&1 && "$CHECK" >"$T/t7b.log" 2>&1; then
  # 判据用「七个阶段名在表区里都在」而不是数行数：状态格里的 `|`（转义）会骗过行数统计。
  missing=""
  while IFS= read -r stage; do
    grep -qF "| $stage |" "$ORG_README" || missing="$missing $stage"
  done < <(extract_progress_table "$T/repo/README.md" | cut -f1)
  if [ -z "$missing" ]; then
    pass "T7 占位表被填成七个阶段，且守卫随后通过"
  else
    bad "T7 表里缺少阶段：$missing"
  fi
else
  bad "T7 同步脚本或其后校验失败"; cat "$T/t7.log" "$T/t7b.log"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "全部通过：守卫抓得住漂移，也没有误报；同步脚本能把占位表填成一致状态。"
  exit 0
fi
echo "有失败项，见上。"
exit 1
