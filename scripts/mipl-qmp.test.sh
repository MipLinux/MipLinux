#!/usr/bin/env bash
# mipl-qmp.sh 的离线回归：假 QMP server（python3 标准库）+ 临时目录，不碰真实仓库。
#
# 为什么有它：QMP 客户端是「替人敲键、替人看屏」的东西，一次静默的握手顺序错、
# 键名映射错，都要到真 VM 上才现形。所以把 QMP 线协议在本地先验一遍：
# 握手、命令 JSON、键名映射、type 逐键、shot 的 PNG/PPM 两条路、
# wait-for 的命中与超时退出码、连接失败的两句人话。
#
# **不需要 root / QEMU / ISO**。用法：./scripts/mipl-qmp.test.sh
# 退出码：0 = 全过；1 = 有失败项。

set -uo pipefail

SELF_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CLIENT="$SELF_DIR/mipl-qmp.sh"
[ -x "$CLIENT" ] || { echo "错误：$CLIENT 不可执行" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "错误：需要 python3" >&2; exit 1; }

FAIL=0
pass() { printf '✅ %s\n' "$1"; }
bad()  { printf '❌ %s\n' "$1"; FAIL=1; }

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
SOCK="$T/qmp.sock"
REQ="$T/requests.log"
OUT="$T/out"
mkdir -p "$OUT" "$T/empty"

# ── 假 QMP server ──────────────────────────────────────────────────────
# 场景（$1）：echo=万事回 return:{}；status=query-status 回 running；
# shot=按 screendump 的 filename/format 落一个假文件再回 return:{}；
# nopng=png 回 error、ppm 落假文件；quit=收到 quit 就关连接不回包。
# 每个收到的请求原样追加进 $REQ（一行一条 JSON）。
start_fake_qmp() {
  python3 - "$SOCK" "$REQ" "$1" <<'PY' &
import json, os, socket, sys

sock_path, req_log, scenario = sys.argv[1], sys.argv[2], sys.argv[3]
if os.path.exists(sock_path):
    os.unlink(sock_path)
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(sock_path)
srv.listen(4)

GREETING = (b'{"QMP":{"version":{"qemu":{"major":11,"minor":1,"micro":1},'
            b'"package":""},"capabilities":["oob"]}}\r\n')

def send(conn, obj):
    conn.sendall((json.dumps(obj) + "\r\n").encode())

while True:
    try:
        conn, _ = srv.accept()
    except OSError:
        break
    with conn:
        f = conn.makefile("rb")
        conn.sendall(GREETING)
        while True:
            line = f.readline()
            if not line:
                break
            with open(req_log, "a") as lh:
                lh.write(line.decode())
            try:
                req = json.loads(line)
            except ValueError:
                continue
            exe = req.get("execute")
            if exe == "qmp_capabilities":
                send(conn, {"return": {}})
                continue
            if scenario == "quit" and exe == "quit":
                f.close()      # makefile 拿着 fd 的 dup，不关它客户端等不到 EOF
                break          # 真 QEMU 的 quit 不回包，直接关连接
            if scenario == "status" and exe == "query-status":
                send(conn, {"return": {"status": "running", "singlestep": False,
                                       "running": True}})
                continue
            if exe == "screendump":
                args = req.get("arguments", {})
                fmt = args.get("format")
                if scenario == "nopng" and fmt == "png":
                    send(conn, {"error": {"class": "GenericError",
                                          "desc": "Image format 'png' is not supported"}})
                    continue
                with open(args["filename"], "wb") as fh:
                    if fmt == "ppm":
                        fh.write(b"P6\n# fake\n1 1\n255\n\x00\x00\x00")
                    else:
                        fh.write(b"\x89PNG\r\n\x1a\nfakefakefake")
                send(conn, {"return": {}})
                continue
            send(conn, {"return": {}})
PY
  QMP_PID=$!
  local i
  for i in $(seq 1 100); do
    [[ -S "$SOCK" ]] && return 0
    sleep 0.05
  done
  echo "错误：假 QMP server 没起来" >&2
  return 1
}

stop_fake_qmp() {
  [[ -n "${QMP_PID:-}" ]] && kill "$QMP_PID" 2>/dev/null || true
  wait "$QMP_PID" 2>/dev/null || true
  QMP_PID=""
  # kill 不清理 socket 文件：不删掉，下一个 start 的等待循环会被旧文件骗过，
  # 客户端连上去就是 Connection refused。
  rm -f "$SOCK"
  : > "$REQ"    # 每个用例从空的请求日志出发
}

# ── 断言工具 ──────────────────────────────────────────────────────────
# 请求日志第 N 行（1 起）与期望 JSON 逐字段相等。
assert_request() { # $1=用例名 $2=行号 $3=期望 JSON
  if python3 - "$REQ" "$2" "$3" <<'PY'
import json, sys
lines = [l.strip() for l in open(sys.argv[1]) if l.strip()]
idx = int(sys.argv[2])
want = json.loads(sys.argv[3])
got = json.loads(lines[idx - 1]) if len(lines) >= idx else None
sys.exit(0 if got == want else 1)
PY
  then pass "$1"
  else bad "$1（第 $2 行与期望不符。请求日志：$(tr '\n' ' ' < "$REQ")）"; fi
}

# 跑一条客户端命令，断言退出码与输出里必须出现的片段。
expect_rc() { # $1=用例名 $2=期望退出码 $3=输出必须包含的片段；后面是命令
  local name="$1" want="$2" pat="$3" out rc
  shift 3
  out="$("$@" 2>&1)" && rc=0 || rc=$?
  if [[ $rc -eq $want ]] && { [[ -z "$pat" ]] || [[ "$out" == *"$pat"* ]]; }; then
    pass "$name"
  else
    bad "$name（退出码 $rc，期望 $want${pat:+，输出缺「$pat」}。输出：$(printf '%s' "$out" | tail -3 | tr '\n' ' ')）"
  fi
}

# ── 1. 握手与命令 JSON ────────────────────────────────────────────────
start_fake_qmp echo
expect_rc "status：握手先于动作" 0 "QMP 通道" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" status
assert_request "第 1 行是 qmp_capabilities" 1 '{"execute":"qmp_capabilities"}'
assert_request "第 2 行是 query-status" 2 '{"execute":"query-status"}'
stop_fake_qmp

# ── 2. 键名映射 ───────────────────────────────────────────────────────
start_fake_qmp echo
expect_rc "key ctrl-alt-f2 退出码 0" 0 "已发送" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" key ctrl-alt-f2
assert_request "ctrl-alt-f2 → ctrl/alt/f2" 2 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"ctrl"},{"type":"qcode","data":"alt"},{"type":"qcode","data":"f2"}]}}'
expect_rc "key ret 退出码 0" 0 "" env MIPL_QMP_SOCK="$SOCK" "$CLIENT" key ret
assert_request "ret → ret" 4 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"ret"}]}}'
expect_rc "key down 退出码 0" 0 "" env MIPL_QMP_SOCK="$SOCK" "$CLIENT" key down
assert_request "down → down" 6 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"down"}]}}'
expect_rc "key shift-f5 退出码 0" 0 "" env MIPL_QMP_SOCK="$SOCK" "$CLIENT" key shift-f5
assert_request "shift-f5 → shift/f5" 8 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"shift"},{"type":"qcode","data":"f5"}]}}'
expect_rc "大写键名折叠成小写" 0 "" env MIPL_QMP_SOCK="$SOCK" "$CLIENT" key CTRL-ALT-DEL
assert_request "CTRL-ALT-DEL → ctrl/alt/delete" 10 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"ctrl"},{"type":"qcode","data":"alt"},{"type":"qcode","data":"delete"}]}}'
expect_rc "不认识的键名报错且不发命令" 1 "不认识" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" key ctrl-foo
stop_fake_qmp

# ── 3. type 逐键 ──────────────────────────────────────────────────────
start_fake_qmp echo
expect_rc "type 'Hi!' 退出码 0" 0 "已敲入 3" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" type 'Hi!'
assert_request "H → shift+h" 2 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"shift"},{"type":"qcode","data":"h"}]}}'
assert_request "i → i" 4 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"i"}]}}'
assert_request "! → shift+1" 6 \
  '{"execute":"send-key","arguments":{"keys":[{"type":"qcode","data":"shift"},{"type":"qcode","data":"1"}]}}'
expect_rc "多参数拼成一句话" 0 "已敲入 5" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" type ls -l
expect_rc "不支持的字符报错" 1 "不支持" env MIPL_QMP_SOCK="$SOCK" "$CLIENT" type '好'
stop_fake_qmp

# ── 4. shot：PNG 直通、PPM 回落、默认路径 ─────────────────────────────
start_fake_qmp shot
expect_rc "shot 指定路径 PNG 退出码 0" 0 "PNG" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" shot "$OUT/qmp-boot.png"
if [[ -s "$OUT/qmp-boot.png" ]] \
   && [[ "$(head -c 1 "$OUT/qmp-boot.png" | od -An -tx1 | tr -d ' ')" == 89 ]]; then
  pass "PNG 文件落盘、非空、文件头是 PNG"
else
  bad "PNG 文件落盘、非空、文件头是 PNG"
fi
expect_rc "shot 默认落 out/qmp-shot.png" 0 "qmp-shot.png" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" shot
[[ -s "$OUT/qmp-shot.png" ]] && pass "默认路径的截图文件在" \
                              || bad "默认路径的截图文件在"
stop_fake_qmp

start_fake_qmp nopng
expect_rc "PNG 不可用回 PPM，退出码 0 并打印 PPM" 0 "PPM" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" shot "$OUT/qmp-fallback.png"
if [[ -s "$OUT/qmp-fallback.ppm" && ! -e "$OUT/qmp-fallback.png" ]]; then
  pass "回落产物是 .ppm 且没有冒名的 .png"
else
  bad "回落产物是 .ppm 且没有冒名的 .png"
fi
stop_fake_qmp

# ── 5. wait-for：命中与超时 ───────────────────────────────────────────
printf 'booting kernel\narchiso login: root (automatic login)\ntail marker here\n' \
  > "$OUT/installer-serial.log"
expect_rc "wait-for 命中退出码 0" 0 "命中" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" wait-for 'archiso login:'
expect_rc "wait-for 超时非 0 且打印日志尾部" 1 "tail marker here" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" \
  wait-for 'never-match-xyz' --timeout 2
expect_rc "wait-for 日志不存在时也是超时非 0" 1 "日志文件还不存在" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$T/empty" "$CLIENT" \
  wait-for 'anything' --timeout 2
expect_rc "wait-for 非法正则立即报错" 1 "正则不合法" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" wait-for '('
# ── 6. serial-tail ────────────────────────────────────────────────────
expect_rc "serial-tail 打印日志尾部" 0 "tail marker here" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$OUT" "$CLIENT" serial-tail
expect_rc "serial-tail 没有日志时报错" 1 "串口日志不存在" \
  env MIPL_QMP_SOCK="$SOCK" MIPL_OUT_DIR="$T/empty" "$CLIENT" serial-tail

# ── 7. status / quit ──────────────────────────────────────────────────
start_fake_qmp status
expect_rc "status 打印 running" 0 "running" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" status
stop_fake_qmp
start_fake_qmp quit
expect_rc "quit 不回包也算成功" 0 "已发送 quit" \
  env MIPL_QMP_SOCK="$SOCK" "$CLIENT" quit
stop_fake_qmp

# ── 8. 连不上的两句人话 ───────────────────────────────────────────────
expect_rc "socket 不存在 → 通道没开，退出码 2" 2 "通道没开" \
  env MIPL_QMP_SOCK="$T/nope.sock" "$CLIENT" status
printf 'stale leftover\n' > "$T/stale.sock"
expect_rc "残留文件连不上 → 通道没开，非 0" 4 "通道没开" \
  env MIPL_QMP_SOCK="$T/stale.sock" "$CLIENT" status

# 权限不足 → 「这条要用 sudo」。root 跑测试时 EACCES 拦不住 root，这个用例跳过。
if [[ $EUID -ne 0 ]]; then
  python3 - "$T/noperm.sock" <<'PY' &
import os, socket, sys, time
p = sys.argv[1]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(p)
os.chmod(p, 0)          # 任何非 root 都连不上：EACCES
s.listen(1)
time.sleep(60)
PY
  PERM_PID=$!
  i=0
  for i in $(seq 1 50); do [[ -S "$T/noperm.sock" ]] && break; sleep 0.05; done
  expect_rc "socket 权限不够 → 这条要用 sudo，退出码 3" 3 "这条要用 sudo" \
    env MIPL_QMP_SOCK="$T/noperm.sock" "$CLIENT" status
  kill "$PERM_PID" 2>/dev/null || true
  wait "$PERM_PID" 2>/dev/null || true
else
  printf '（以 root 跑测试，跳过「这条要用 sudo」用例 —— root 不受 EACCES 拦）\n'
fi

# ── 收尾 ──────────────────────────────────────────────────────────────
echo
if [[ $FAIL -eq 0 ]]; then
  echo "全部通过 ✅"
  exit 0
else
  echo "有 $FAIL 处失败 ❌"
  exit 1
fi
