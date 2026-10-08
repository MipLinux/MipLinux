#!/usr/bin/env bash
# mipl.sh 属主归还逻辑（Issue #93）的回归测试。
#
# 测什么：
#   1. 身份解析：sudo 线索（SUDO_UID/SUDO_GID）与 pkexec 线索（只有 PKEXEC_UID，
#      主组查 passwd）都能解析出调用者 uid/gid；两条线索都没有 → 判「无身份」；
#   2. 归还：root / nobody 属主的文件与目录（模拟容器用户命名空间映射的两种
#      落盘结果）在临时目录里被还给调用者 UID/GID；
#   3. 不递归：顶层 root 目录被归还，它里面的文件原样不动；
#   4. 身份缺失 / 半截身份（只有 PKEXEC_UID 且 passwd 里查不到）不猜属主：
#      一个 chown 都不执行、属主原样，只打告警 —— 不会静默改成错误属主；
#   5. 试运行（DRY_RUN=1）只打印将执行的 chown，不动文件系统。
#
# 夹具全部在 mktemp -d 的临时目录里，**不碰真实 out/、目标盘、构建容器**。
# 特权用例（真以 root 建 root / nobody 夹具再归还）在非 root 会话里经 sudo 重跑
# 本脚本的 --priv 段 —— sudo 会给子进程填好 SUDO_UID/SUDO_GID，与 mipl.sh 经
# sudo 入口的真实环境一样。sudo 不可用或需要密码时如实标注「未实测」，不降级
# 成假断言。
#
# 用法：./scripts/mipl-out-ownership.test.sh
# 退出码：0 = 没有失败项（未实测单独标注）；1 = 有用例失败。

set -uo pipefail

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LIB="$SELF_DIR/mipl-lib.sh"

FAIL=0
SKIP=0
pass() { printf '✅ %s\n' "$1"; }
bad()  { printf '❌ %s\n' "$1"; FAIL=1; }
skip() { printf '⚠️  未实测 %s\n' "$1"; SKIP=1; }

[[ -r "$LIB" ]] || { echo "错误：读不到 $LIB" >&2; exit 1; }
# shellcheck source=scripts/mipl-lib.sh
MIPL_LIB_COLORS=1 . "$LIB"

# 断言一个路径的属主。$1=路径 $2=期望 uid $3=期望 gid
check_stat() {
  local got
  got="$(stat -c '%u:%g' -- "$1")"
  if [[ "$got" == "$2:$3" ]]; then
    pass "属主归还：$1 → $got"
  else
    bad "属主归还：$1 → $got（期望 $2:$3）"
  fi
}

# ── 特权用例：真 root 建夹具 → 归还调用者 ─────────────────────────────
# 需要 root 才能造出 root / nobody 属主的夹具（非特权进程无法 chown 过去）。
priv_cases() {
  # 特权夹具只有 root 造得出来：非 root 时 chown 会静默失败，用例会假通过 ——
  # 先拦身份。
  if [[ "$(id -u)" -ne 0 ]]; then
    skip "特权用例需要 root（当前 uid=$(id -u)），请经 sudo 运行本测试"
    return 0
  fi
  # 调用者线索必须来自 sudo / pkexec —— 与 mipl.sh 的真实入口一致。
  # 直接以 root 跑又没有线索时，不知道归还给谁，特权用例无从验证。
  if [[ -z "${SUDO_UID:-}" && -z "${PKEXEC_UID:-}" ]]; then
    skip "特权用例：没有调用者线索（请经 sudo 运行本测试）"
    return 0
  fi

  local want_uid want_gid
  want_uid="${SUDO_UID:-$PKEXEC_UID}"
  if [[ -n "${SUDO_GID:-}" ]]; then
    want_gid="$SUDO_GID"
  else
    want_gid="$(getent passwd "$want_uid" 2>/dev/null | head -1 | cut -d: -f4)"
  fi

  local dir="$T/priv"
  mkdir -p "$dir"

  # ① root 建的目录（模拟 root 跑过一次命令后的 out/ 本身）
  local d_root="$dir/out-root-owned"
  mkdir -p "$d_root"
  chown 0:0 "$d_root"

  # ② root 建的文件（本进程就是 root，天然 uid 0）
  local f_root="$dir/iso-root.iso"
  printf 'x' > "$f_root"

  # ③ nobody 属主的文件（容器用户命名空间映射到宿主上的样子）
  local f_nobody="$dir/iso-nobody.iso"
  printf 'x' > "$f_nobody"
  chown 65534:65534 "$f_nobody"

  # ④ root 目录里的 root 文件：递归归还会动到它，我们的归还必须不碰它
  local f_deep="$d_root/deep.log"
  printf 'x' > "$f_deep"

  # 经 sudo 重跑时 SUDO_* 就是真实入口的线索，直接用
  ( unset PKEXEC_UID
    mipl_restore_root_owned "$d_root"
    mipl_restore_owner "$f_root" "$f_nobody" )
  check_stat "$d_root"   "$want_uid" "$want_gid"
  check_stat "$f_root"   "$want_uid" "$want_gid"
  check_stat "$f_nobody" "$want_uid" "$want_gid"
  check_stat "$f_deep"   0 0     # 不递归：目录里的文件保持 root

  # pkexec 形态：只有 PKEXEC_UID 线索（真 pkexec 清空环境、不设 SUDO_*）
  local f_pk="$dir/iso-pkexec.iso"
  printf 'x' > "$f_pk"
  chown 65534:65534 "$f_pk"
  ( unset SUDO_UID SUDO_GID SUDO_USER
    PKEXEC_UID="$want_uid"
    mipl_restore_owner "$f_pk" )
  check_stat "$f_pk" "$want_uid" "$want_gid"

  # 命令收尾的顶层扫描：root/nobody 的白名单产物归还、调用者自己的不动、
  # 白名单外的名字不动、不递归进子目录。
  local scandir="$dir/scan"
  mkdir -p "$scandir"
  printf 'x' > "$scandir/root.iso"                                   # 白名单内，root → 归还
  printf 'x' > "$scandir/installer-serial.log"; chown 65534:65534 "$scandir/installer-serial.log"  # nobody → 归还
  printf 'x' > "$scandir/user.txt"; chown "$want_uid:$want_gid" "$scandir/user.txt"                # 白名单外：本来就不动
  mkdir -p "$scandir/rootsub"; chown 0:0 "$scandir/rootsub"
  printf 'x' > "$scandir/rootsub/inner.iso"                          # 子目录里的 root 文件：不递归，必须不动

  ( OUT_DIR="$scandir" mipl_restore_out_dir )
  check_stat "$scandir/root.iso"            "$want_uid" "$want_gid"
  check_stat "$scandir/installer-serial.log" "$want_uid" "$want_gid"
  check_stat "$scandir/user.txt"            "$want_uid" "$want_gid"
  check_stat "$scandir/rootsub"             0 0            # 目录不是白名单名字，不动
  check_stat "$scandir/rootsub/inner.iso"   0 0            # 没被递归动到
}

# ── sudo 重跑的入口（--priv）：只跑特权用例，夹具目录由父进程传进来
# （父进程负责清理）。放在 mktemp 之前 —— 子进程不再建自己的临时目录、
# 不再重复跑 T 组用例；独立进程天然不带父进程里解析过的身份缓存。
if [[ "${1:-}" == "--priv" ]]; then
  T="${2:?--priv 后面要跟夹具目录}"
  priv_cases
  if [[ $FAIL -eq 0 ]]; then exit 0; else exit 1; fi
fi

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
OUT_FIX="$T/out"
mkdir -p "$OUT_FIX"

# 用例全放在子 shell 里跑：mipl_caller_identity 把解析结果缓存在进程级全局里，
# 子 shell 天然隔离，用例之间不会互相污染。

echo "── 共用库：$LIB"
echo

echo "── T1 身份解析 · sudo 线索（SUDO_UID/SUDO_GID）"
(
  wu="${SUDO_UID:-$(id -u)}"          # 经 sudo 整体跑时「调用者」是发起者
  wg="${SUDO_GID:-$(id -g)}"
  unset PKEXEC_UID
  SUDO_UID="$wu" SUDO_GID="$wg"
  mipl_caller_identity \
    && [[ "$MIPL_CALLER_UID" == "$wu" && "$MIPL_CALLER_GID" == "$wg" ]]
) && pass "T1 sudo 线索解析出调用者 uid/gid" || bad "T1 sudo 线索解析失败"
echo

echo "── T2 身份解析 · pkexec 线索（只有 PKEXEC_UID，主组查 passwd）"
(
  wu="${SUDO_UID:-$(id -u)}"
  wg="$(getent passwd "$wu" 2>/dev/null | head -1 | cut -d: -f4)"
  unset SUDO_UID SUDO_GID SUDO_USER
  PKEXEC_UID="$wu"
  mipl_caller_identity \
    && [[ "$MIPL_CALLER_UID" == "$wu" && "$MIPL_CALLER_GID" == "$wg" ]]
) && pass "T2 pkexec 线索解析出调用者 uid/gid" || bad "T2 pkexec 线索解析失败"
echo

echo "── T3 两条线索都没有 → 判「无身份」"
(
  unset SUDO_UID SUDO_GID SUDO_USER PKEXEC_UID
  ! mipl_caller_identity
) && pass "T3 无线索判定为无身份" || bad "T3 无线索没有被判为无身份"
echo

echo "── T4 无身份时一个 chown 都不执行，且告警而不是静默"
(
  unset SUDO_UID SUDO_GID SUDO_USER PKEXEC_UID
  f="$OUT_FIX/noid.txt"
  printf 'x' > "$f"
  before="$(stat -c '%u:%g' -- "$f")"
  out="$(mipl_restore_owner "$f" 2>&1)"
  after="$(stat -c '%u:%g' -- "$f")"
  [[ "$before" == "$after" ]] \
    && grep -qF "不猜测属主" <<<"$out" \
    && grep -qF "SUDO_UID / PKEXEC_UID" <<<"$out"
) && pass "T4 无身份：属主原样、告警可见" || bad "T4 无身份时改了属主或没告警"
echo

echo "── T5 半截身份（PKEXEC_UID 在 passwd 里查不到）→ 不猜、不改"
(
  unset SUDO_UID SUDO_GID SUDO_USER
  PKEXEC_UID=99999999               # 不在系统的用户数据库里
  f="$OUT_FIX/half.txt"
  printf 'x' > "$f"
  before="$(stat -c '%u:%g' -- "$f")"
  out="$(mipl_restore_owner "$f" 2>&1)"
  after="$(stat -c '%u:%g' -- "$f")"
  [[ "$before" == "$after" ]] && grep -qF "不猜测属主" <<<"$out"
) && pass "T5 半截身份：不改属主、告警可见" || bad "T5 半截身份被静默改成了错误属主"
echo

echo "── T6 试运行（DRY_RUN=1）只打印 chown，不创建、不修改"
(
  wu="${SUDO_UID:-$(id -u)}"
  wg="${SUDO_GID:-$(id -g)}"
  unset PKEXEC_UID
  SUDO_UID="$wu" SUDO_GID="$wg"
  DRY_RUN=1
  want="$OUT_FIX/dry.txt"
  out="$(mipl_restore_owner "$want")"
  grep -qF "chown ${wu}:${wg} ${want}" <<<"$out" && [[ ! -e "$want" ]]
) && pass "T6 试运行打印正确的 chown 且不动文件系统" || bad "T6 试运行行为不对"
echo

echo "── T7 收尾扫描：调用者自己的文件一个都不碰（哪怕名字在白名单里）"
(
  d="$T/scan-self"
  mkdir -p "$d"
  wu="${SUDO_UID:-$(id -u)}"          # 「调用者」= 发起者，不是当前进程身份
  wg="${SUDO_GID:-$(id -g)}"
  for f in mirrorlist root.iso installer-serial.log; do
    printf 'x' > "$d/$f"
    # root 会话里刚建出来的是 root 的，先改成调用者的，再验证扫描不动它
    chown "$wu:$wg" "$d/$f" 2>/dev/null || true
  done
  before="$(stat -c '%u:%g' -- "$d/mirrorlist")"
  OUT_DIR="$d" mipl_restore_out_dir
  after="$(stat -c '%u:%g' -- "$d/mirrorlist")"
  [[ "$before" == "$after" && "$before" == "$wu:$wg" ]]
) && pass "T7 扫描跳过调用者自己的文件" || bad "T7 扫描动了调用者自己的文件"
echo

echo "── P 组 · 特权用例（root/nobody 建夹具 → 归还调用者）"
if [[ "$(id -u)" -eq 0 ]]; then
  priv_cases
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  # 有免密 sudo：重跑本脚本的 --priv 段。sudo 会给子进程填 SUDO_UID/SUDO_GID，
  # 正好模拟 mipl.sh 经 sudo 入口的真实环境。用绝对路径，不依赖 sudo 保留 $0。
  if sudo -n bash "$SELF_DIR/mipl-out-ownership.test.sh" --priv "$T"; then
    pass "P 组特权用例（经 sudo 重跑）全部通过"
  else
    bad "P 组特权用例（经 sudo 重跑）有失败，见上方输出"
  fi
else
  skip "P 组特权用例需要 root（root/nobody 夹具只有 root 造得出来）：当前会话不是 root 且 sudo 不可用/需要密码"
fi
echo

echo "────────────────────────"
if [[ $FAIL -eq 0 ]]; then
  if [[ $SKIP -eq 1 ]]; then
    echo "通过，但有用例未实测（见上方 ⚠️）—— 在可提权的会话里重跑以获得完整证据。"
  else
    echo "全部通过：身份解析、归还、不递归、身份缺失不静默改属主，全部有实测证据。"
  fi
  exit 0
fi
echo "有用例失败：属主归还逻辑有问题，先修 scripts/mipl-lib.sh / scripts/mipl.sh。"
exit 1
