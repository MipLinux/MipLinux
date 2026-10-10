#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# mipl-qmp · QEMU QMP 回归驱动客户端（一条命令一个动作）
#
# VM 起来之后，人（以及提不了权的 AI Agent）用**普通用户身份**就能驱动它：
# 代发按键、截图、等串口判据 —— 不必每轮现搓 socat 和临时 python。
#
#   ./scripts/mipl-qmp.sh status                        QEMU 状态
#   ./scripts/mipl-qmp.sh key ctrl-alt-f2               组合键（QMP send-key）
#   ./scripts/mipl-qmp.sh type 'lsblk'                  ASCII 逐键敲入
#   ./scripts/mipl-qmp.sh shot out/qmp-boot.png         截图（PNG 优先，失败回 PPM）
#   ./scripts/mipl-qmp.sh wait-for 'archiso login:'     轮询 out/installer-serial.log
#   ./scripts/mipl-qmp.sh serial-tail [N]               串口日志尾部
#   ./scripts/mipl-qmp.sh quit                          QMP 关机
#
# 通道：默认 out/qemu-qmp.sock（mipl.sh qemu/installer --qmp 开的），
#       MIPL_QMP_SOCK 可顶掉。
#
# **普通用户连得上，是这条工作的硬要求** —— 用它的大头是 AI Agent，
# 提权那条路它们走不了。因此：
#
#   1. 本脚本自己不提权。连不上就打印「通道没开」或「这条要用 sudo」，
#      退出码非 0 —— 拒绝 sudo 是行为，不是提示语。
#
#   2. socket 权限为什么走「mipl.sh 在 socket 出现后 chmod 0666」，
#      而不走 tcp:127.0.0.1:<port>（两条候选的选型记录）：
#      实测 QEMU 11 的 -qmp 与 -chardev socket 都不收 mode=（报
#      Invalid parameter 'mode'），而 root 起的 QEMU 出的 unix socket
#      默认 0755、非属主连不上 —— 所以两条路都需要「绕」。
#      选 chmod 0666：通道地址是 out/ 里的**固定路径**，客户端与 mipl.sh
#      只说一个名字就对齐；tcp 要另约端口 —— 固定端口两台 VM 会撞车，
#      动态端口又得多一份「端口写在哪」的协议。安全性两条等价：都是
#      本机可达（tcp 绑 127.0.0.1、socket 落在 out/），暴露面都是
#      「这台机器上的任何用户都能操作这台测试 VM」，而这正是工具要的。
#      chmod 由 mipl.sh 在**主流程**里做：QEMU 放后台、等 socket 一出现
#      （bind 完成）就 chmod 0666、再 wait 回前台，不挂独立的后台盯梢进程 ——
#      盯梢和 QEMU 同进程组，用户 Ctrl+Z 拿回终端时整个组一起停，盯梢会被
#      冻在 chmod 之前（Issue #125 实测过这种死法：socket 一直是 0755）。
#
#   3. 只用 python3 标准库做 socket I/O —— 宿主机依赖不新增：socat 不在
#      mipl.sh deps 清单里，不能拿来当硬依赖（Issue #125 的约束）。
#
# 截图只有文本控制台可信：cage 用 KMS 接手显示后 screendump 是纯黑
# （docs/work/tech/04 §4.4 实测），别拿黑屏当失败。
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── 自身定位（循环解引用软链，同 mipl.sh）────────────────────────────
mipl_qmp_self_dir() {
  local src="${BASH_SOURCE[0]}" dir
  while [[ -L "$src" ]]; do
    dir="$(cd -P "$(dirname "$src")" >/dev/null && pwd)"
    src="$(readlink "$src")"
    [[ "$src" == /* ]] || src="${dir}/${src}"
  done
  cd -P "$(dirname "$src")" >/dev/null && pwd
}

SCRIPT_DIR="$(mipl_qmp_self_dir)"
REPO_ROOT="${MIPL_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
# 与 mipl.sh 同一套产物目录约定：MIPL_OUT_DIR 顶掉后，串口日志、默认截图、
# 默认 socket 都跟着走，两边才不会各说各的路径。
OUT_DIR="${MIPL_OUT_DIR:-${REPO_ROOT}/out}"
QMP_SOCK="${MIPL_QMP_SOCK:-${OUT_DIR}/qemu-qmp.sock}"
SERIAL_LOG="${OUT_DIR}/installer-serial.log"

# ── 共用库（颜色与输出约定）──────────────────────────────────────────
MIPL_LIB="${SCRIPT_DIR}/mipl-lib.sh"
if [[ ! -r "$MIPL_LIB" ]]; then
  printf '[错误] 缺少共用库：%s —— 仓库不完整或脚本被单独拷走了\n' "$MIPL_LIB" >&2
  exit 1
fi
# shellcheck source=scripts/mipl-lib.sh
MIPL_LIB_COLORS=1 . "$MIPL_LIB"

have() { command -v "$1" >/dev/null 2>&1; }
have python3 || die "需要 python3（仓库本来就用它跑测试，不算新增依赖）"

# ── QMP 一次事务 ──────────────────────────────────────────────────────
# 连 socket → 收 greeting → qmp_capabilities → 发 $1 → 打印响应。
# 退出码约定（bash 按它翻译成人话）：
#   0  成功，响应打在 stdout 上（--allow-eof 时 QEMU 不回包也当成功）
#   2  socket 文件不存在        → 「通道没开」
#   3  权限不够（EACCES/EPERM） → 「这条要用 sudo」
#   4  拒绝连接 / 握手或响应落空 → 「通道没开」（QEMU 已退出 / 没在听）
#   5  读响应超时
#   6  QMP 回了 error（响应仍打在 stdout 上）
_qmp() {
  local req="$1" allow_eof=0
  [[ "${2:-}" == "--allow-eof" ]] && allow_eof=1
  python3 - "$QMP_SOCK" "$req" "$allow_eof" <<'PY'
import os, socket, sys

sock_path, request, allow_eof = sys.argv[1], sys.argv[2], sys.argv[3] == "1"

def out(rc, msg):
    print(msg, file=sys.stderr)
    sys.exit(rc)

if not os.path.exists(sock_path):
    out(2, "通道没开：%s 不存在 —— VM 没起，或没带 --qmp" % sock_path)

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(sock_path)
except PermissionError:
    out(3, "这条要用 sudo：%s 连不上（socket 权限没放开）。\n"
           "别 sudo —— 用新脚本重起 VM：sudo ./scripts/mipl.sh qemu --qmp" % sock_path)
except FileNotFoundError:
    out(4, "通道没开：%s 连不上（QEMU 已退出？）" % sock_path)
except socket.timeout:
    out(5, "通道没响应：%s（connect 超时，QEMU 卡住了？）" % sock_path)
except OSError as e:
    out(4, "通道没开：%s 连不上：%s" % (sock_path, e))

resp = b""
try:
    f = s.makefile("rb")
    greeting = f.readline()
    if not greeting:
        out(4, "通道没开：%s 没有 QMP greeting（QEMU 已退出？）" % sock_path)
    s.sendall(b'{"execute":"qmp_capabilities"}\r\n')
    if not f.readline():
        out(4, "通道没开：握手没回包（QEMU 已退出？）" % sock_path)
    s.sendall(request.encode() + b"\r\n")
    resp = f.readline()
except socket.timeout:
    out(5, "通道没响应：%s（QEMU 卡住了？）" % sock_path)
finally:
    s.close()

if not resp:
    if allow_eof:
        sys.exit(0)          # quit：QEMU 关机，不回包是正常行为
    out(4, "通道没开：命令没回包（QEMU 已退出？）" % sock_path)

sys.stdout.write(resp.decode())
sys.exit(6 if b'"error"' in resp else 0)
PY
}

# 跑一次事务，结果放 QMP_LAST_RESP / QMP_LAST_RC，返回 rc。
run_qmp() {
  local resp rc
  resp="$(_qmp "$@")" && rc=0 || rc=$?
  QMP_LAST_RESP="$resp"
  QMP_LAST_RC=$rc
  return "$rc"
}

# 统一错误出口：rc=6 是 QMP 业务错误，把响应打出来；2–5 是连接类错误，
# _qmp 已经打印过人话，原样带退出码出去。
fail_qmp() {
  if [[ $QMP_LAST_RC -eq 6 ]]; then
    die "QMP 报错：${QMP_LAST_RESP}"
  fi
  exit "$QMP_LAST_RC"
}

# ── 键名映射 ──────────────────────────────────────────────────────────
# 组合键用 - 连（ctrl-alt-f2），每个 token 翻成 QMP 的 QKeyCode。
# 不在表里就报错退出：静默发错键比报错更坏。
qcode() {
  case "$1" in
    ctrl|control)       printf 'ctrl\n' ;;
    alt)                printf 'alt\n' ;;
    shift)              printf 'shift\n' ;;
    ret|enter)          printf 'ret\n' ;;
    esc|escape)         printf 'esc\n' ;;
    tab)                printf 'tab\n' ;;
    spc|space)          printf 'spc\n' ;;
    up)                 printf 'up\n' ;;
    down)               printf 'down\n' ;;
    left)               printf 'left\n' ;;
    right)              printf 'right\n' ;;
    backspace|bsp)      printf 'backspace\n' ;;
    delete|del)         printf 'delete\n' ;;
    insert|ins)         printf 'insert\n' ;;
    home)               printf 'home\n' ;;
    end)                printf 'end\n' ;;
    pgup|pageup)        printf 'pgup\n' ;;
    pgdn|pagedown)      printf 'pgdn\n' ;;
    minus|'-')          printf 'minus\n' ;;
    equal|'=')          printf 'equal\n' ;;
    comma|',')          printf 'comma\n' ;;
    dot|'.'|period)     printf 'dot\n' ;;
    slash|'/')          printf 'slash\n' ;;
    backslash)          printf 'backslash\n' ;;
    semicolon)          printf 'semicolon\n' ;;
    apostrophe)         printf 'apostrophe\n' ;;
    grave|grave_accent) printf 'grave_accent\n' ;;
    bracket_left)       printf 'bracket_left\n' ;;
    bracket_right)      printf 'bracket_right\n' ;;
    *)
      if [[ "$1" =~ ^f([1-9]|1[0-2])$ ]]; then
        printf '%s\n' "$1"
      else
        return 1
      fi ;;
  esac
}

# send-key 请求的 JSON（一个元素 = 一个键）。
keys_json() { # $@ = qcode 列表
  local code out=""
  for code in "$@"; do
    out+="${out:+,}{\"type\":\"qcode\",\"data\":\"$code\"}"
  done
  printf '{"execute":"send-key","arguments":{"keys":[%s]}}' "$out"
}

cmd_key() {
  [[ $# -eq 1 ]] || die "key 只接受一个组合键（如 ctrl-alt-f2、ret、down）"
  local combo="$1" tok code
  local -a parts=() codes=()
  IFS='-' read -r -a parts <<< "$combo"
  for tok in "${parts[@]}"; do
    tok="$(printf '%s' "$tok" | tr '[:upper:]' '[:lower:]')"
    code="$(qcode "$tok" || true)"
    [[ -n "$code" ]] || die "不认识键名：$tok（组合键：$combo）"
    codes+=("$code")
  done
  run_qmp "$(keys_json "${codes[@]}")" || fail_qmp
  ok "已发送：$combo"
}

# ── type：ASCII 逐键敲入 ──────────────────────────────────────────────
# 每个字符一个 send-key：大写与标点带 shift（US 布局）。超出映射表就报错
# —— 发错键会把密码敲错地方，宁可停下。
char_codes() { # $1=单字符 → 每行一个 qcode；空输出=不支持
  local ch="$1" base=""
  case "$ch" in
    [a-z]|[0-9]) printf '%s\n' "$ch" ;;
    [A-Z])       printf 'shift\n%s\n' "${ch,,}" ;;
    ' ')         printf 'spc\n' ;;
    '!') base=1 ;; '@') base=2 ;; '#') base=3 ;; '$') base=4 ;; '%') base=5 ;;
    '^') base=6 ;; '&') base=7 ;; '*') base=8 ;; '(') base=9 ;; ')') base=0 ;;
    '-') printf 'minus\n' ;;
    '_') printf 'shift\nminus\n' ;;
    '=') printf 'equal\n' ;;
    '+') printf 'shift\nequal\n' ;;
    '[') printf 'bracket_left\n' ;;
    '{') printf 'shift\nbracket_left\n' ;;
    ']') printf 'bracket_right\n' ;;
    '}') printf 'shift\nbracket_right\n' ;;
    '\') printf 'backslash\n' ;;
    '|') printf 'shift\nbackslash\n' ;;
    ';') printf 'semicolon\n' ;;
    ':') printf 'shift\nsemicolon\n' ;;
    "'") printf 'apostrophe\n' ;;
    '"') printf 'shift\napostrophe\n' ;;
    ',') printf 'comma\n' ;;
    '<') printf 'shift\ncomma\n' ;;
    '.') printf 'dot\n' ;;
    '>') printf 'shift\ndot\n' ;;
    '/') printf 'slash\n' ;;
    '?') printf 'shift\nslash\n' ;;
    '`') printf 'grave_accent\n' ;;
    '~') printf 'shift\ngrave_accent\n' ;;
    *)   return 1 ;;
  esac
  [[ -n "$base" ]] && printf 'shift\n%s\n' "$base"
  return 0
}

cmd_type() {
  [[ $# -ge 1 ]] || die "type 后面要跟要敲的 ASCII 文本"
  local text="$*" i ch count=0
  local -a codes=()
  for (( i = 0; i < ${#text}; i++ )); do
    ch="${text:i:1}"
    mapfile -t codes < <(char_codes "$ch")
    [[ ${#codes[@]} -gt 0 ]] || die "type 不支持这个字符：$ch（只能敲 ASCII）"
    run_qmp "$(keys_json "${codes[@]}")" || fail_qmp
    count=$((count + 1))
    sleep 0.02   # 键与键之间留间隔：连着灌，慢的客机会掉键
  done
  ok "已敲入 $count 个按键"
}

# ── shot：截图，PNG 优先、失败回 PPM ─────────────────────────────────
# QMP 的 screendump 把文件写到 **QEMU 的工作目录**相对路径下，所以一律先
# 转成绝对路径再发。写完后嗅文件头，把实际格式打印出来 —— 不靠文件名猜。
sniff_format() {
  local magic text
  magic="$(head -c 4 -- "$1" 2>/dev/null | od -An -tx1 | tr -d ' \n')"
  case "$magic" in
    89504e47*) printf 'PNG\n' ;;
    *)
      text="$(head -c 2 -- "$1" 2>/dev/null)"
      case "$text" in
        P6|P3) printf 'PPM\n' ;;
        *)     printf '未知（前 4 字节 %s）\n' "$magic" ;;
      esac ;;
  esac
}

shot_one() { # $1=绝对路径 $2=format → 0 成功；6=QMP 报错；7=QMP 说成功但文件空
  local abs="$1" fmt="$2" req
  req="{\"execute\":\"screendump\",\"arguments\":{\"filename\":\"$abs\",\"format\":\"$fmt\"}}"
  run_qmp "$req" || return "$?"
  if [[ ! -s "$abs" ]]; then
    warn "QMP 说成功了，但截图文件是空的：$abs"
    return 7
  fi
  return 0
}

cmd_shot() {
  [[ $# -le 1 ]] || die "shot 只接受一个可选文件名"
  local target="${1:-}" fmt="png" dir abs rc=0 saved=""
  [[ -n "$target" ]] || target="${OUT_DIR}/qmp-shot.png"
  case "$target" in
    *.png) fmt="png" ;;
    *.ppm) fmt="ppm" ;;   # 显式点名 PPM 就照办，不折腾 png
    *) die "shot 的文件名要带 .png 或 .ppm 扩展名（默认 out/qmp-shot.png）：$target" ;;
  esac

  mkdir -p "$(dirname -- "$target")"
  dir="$(cd "$(dirname -- "$target")" && pwd)"
  abs="${dir}/$(basename -- "$target")"

  shot_one "$abs" "$fmt" || rc=$?
  if [[ $rc -eq 6 || $rc -eq 7 ]] && [[ "$fmt" == png ]]; then
    # PNG 优先、失败回 PPM：QEMU 没编 PNG 支持时 screendump 回 error，
    # 偶尔也会「报成功但落空文件」—— 两条都按「PNG 路没成」处理。
    # 落盘路径换成 .ppm，格式如实打印，不拿 PPM 冒充 PNG。
    local ppm="${abs%.png}.ppm"
    warn "PNG 截图失败（QEMU 没编进 PNG 支持？），回落到 PPM：$(basename -- "$ppm")"
    # 成功要显式把 rc 清回 0：|| 只在失败时跑，成功时 rc 还是第一次的失败码。
    shot_one "$ppm" ppm && rc=0 || rc=$?
  fi
  case $rc in
    0) : ;;
    6) die "截图失败。QMP 报错：${QMP_LAST_RESP}" ;;
    7) die "截图失败：QMP 报成功但文件是空的" ;;
    *) exit "$rc" ;;
  esac

  if [[ -s "$abs" ]]; then saved="$abs"
  elif [[ -s "${abs%.png}.ppm" ]]; then saved="${abs%.png}.ppm"
  else die "截图文件不存在：$abs（QMP 报成功但没落盘）"; fi
  ok "截图已保存：${saved}（格式 $(sniff_format "$saved")，$(file_size "$saved")）"
}

# ── status / quit ─────────────────────────────────────────────────────
cmd_status() {
  run_qmp '{"execute":"query-status"}' || fail_qmp
  local st human
  st="$(printf '%s' "$QMP_LAST_RESP" | sed -n 's/.*"status": *"\([a-z-]*\)".*/\1/p')"
  case "${st:-}" in
    running)   human="运行中" ;;
    paused)    human="已暂停" ;;
    prelaunch) human="还没启动" ;;
    shutdown)  human="已关机" ;;
    *)         human="未知状态" ;;
  esac
  info "QMP 通道：${QMP_SOCK}"
  ok "状态：${st:-解析失败}（${human}）"
}

cmd_quit() {
  run_qmp '{"execute":"quit"}' --allow-eof || fail_qmp
  ok "已发送 quit（QEMU 正在关机）"
}

# ── wait-for / serial-tail（纯日志侧，不走 QMP）──────────────────────
# 看的是 out/installer-serial.log：mipl.sh qemu/installer 要带 --serial file。
cmd_wait_for() {
  [[ $# -ge 1 ]] || die "wait-for 后面要跟正则"
  local pattern="$1" timeout=60 deadline
  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --timeout)
        [[ -n "${2:-}" ]] || die "--timeout 后面要跟秒数"
        timeout="$2"; shift 2 ;;
      *) die "未知选项：$1（wait-for 只支持 --timeout N）" ;;
    esac
  done
  [[ "$timeout" =~ ^[0-9]+$ ]] || die "--timeout 要跟正整数秒，收到：$timeout"
  # 正则先验一遍：不合法就现在报，别等轮询结束才吐一句「超时」误导人。
  # grep 的退出码：0=有匹配，1=没匹配，2=正则本身不合法 —— 只有 2 才算「不合法」。
  # 管道要显式接住：pipefail 下 grep 的 1/2 会直接触发 errexit。
  local re_rc=0
  printf '' | grep -qE "$pattern" 2>/dev/null || re_rc=$?
  [[ $re_rc -le 1 ]] || die "正则不合法：$pattern"

  info "等待串口出现：$pattern（最多 ${timeout}s，看 ${SERIAL_LOG}）"
  deadline=$(( $(date +%s) + timeout ))
  while :; do
    if [[ -f "$SERIAL_LOG" ]] && grep -qE "$pattern" "$SERIAL_LOG"; then
      ok "命中：$pattern"
      note "匹配行（最后 5 行）："
      grep -E "$pattern" "$SERIAL_LOG" | tail -5 | sed 's/^/    /'
      return 0
    fi
    if (( $(date +%s) >= deadline )); then break; fi
    sleep 1
  done

  warn "超时（${timeout}s）没等到：$pattern"
  echo "串口日志尾部（${SERIAL_LOG}）：" >&2
  if [[ -f "$SERIAL_LOG" ]]; then
    tail -n 20 "$SERIAL_LOG" >&2
  else
    echo "（日志文件还不存在 —— VM 没带 --serial file 起吗？）" >&2
  fi
  return 1
}

cmd_serial_tail() {
  [[ $# -le 1 ]] || die "serial-tail 只接受一个可选行数"
  local n=20
  if [[ -n "${1:-}" ]]; then
    [[ "$1" =~ ^[0-9]+$ ]] || die "serial-tail 的行数要是正整数，收到：$1"
    n="$1"
  fi
  [[ -f "$SERIAL_LOG" ]] || die "串口日志不存在：${SERIAL_LOG}
  VM 没起，或没带 --serial file（wait-for / serial-tail 看的是这份日志）"
  info "串口日志尾部（${SERIAL_LOG}）："
  tail -n "$n" "$SERIAL_LOG"
}

# ── 帮助 ──────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
mipl-qmp · QEMU QMP 回归驱动客户端（一条命令一个动作，不需要 root）

用法： ./scripts/mipl-qmp.sh <动作> [参数]

  status                         QEMU 状态（query-status）
  key <组合>                     组合键：ctrl-alt-f2 / ret / down / shift-f5 …
  type <ASCII 文本>              逐键敲入（空格分隔的参数会拼起来）
  shot [文件.png|.ppm]           截图。默认 out/qmp-shot.png；PNG 优先，
                                 失败自动回落 PPM（实际格式会打印出来）
  wait-for <正则> [--timeout N]  轮询 out/installer-serial.log（默认最多 60s）。
                                 命中退出码 0；超时非 0 并打印日志尾部
  serial-tail [行数]             串口日志尾部（默认 20 行）
  quit                           QMP 关机（VM 立刻停，与关窗口同级）

通道： 默认 out/qemu-qmp.sock，MIPL_QMP_SOCK 可顶掉。
       先由 sudo ./scripts/mipl.sh qemu --qmp（或 installer --qmp）开通道。
       脚本自己不提权：连不上就报「通道没开」/「这条要用 sudo」，退出码非 0。

截图： cage 用 KMS 接手显示后 screendump 是纯黑（tech/04 §4.4 实测），
       截图判据只用文本控制台，别拿黑屏当失败。

详情： docs/work/tech/12-QEMU自动化驱动.md
EOF
}

# ── 主流程 ────────────────────────────────────────────────────────────
main() {
  local cmd="${1:-}"
  [[ -n "$cmd" ]] || { usage >&2; exit 1; }
  case "$cmd" in
    -h|--help) usage; exit 0 ;;
    key)         shift; cmd_key "$@" ;;
    type)        shift; cmd_type "$@" ;;
    shot)        shift; cmd_shot "$@" ;;
    wait-for)    shift; cmd_wait_for "$@" ;;
    serial-tail) shift; cmd_serial_tail "$@" ;;
    status)      cmd_status ;;
    quit)        cmd_quit ;;
    *) die "未知动作：$cmd（用 --help 看用法）" ;;
  esac
}

main "$@"
