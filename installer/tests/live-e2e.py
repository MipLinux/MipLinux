#!/usr/bin/env python3
"""经 QEMU 串口 socket 驱动 Live 里的安装器 —— 一次真实的端到端取证。

**为什么需要它。** `scripts/mipl.sh installer --serial console` 把串口挂成
`out/installer-serial.sock`，但那只是一根管子；「等提示符 → 敲命令 → 判断结果」
要有人做。人做的话每次口径都不一样（等多久、看到什么算成功），而且没法把
「当时到底发生了什么」原样贴进 `docs/work/tech/`。

所以：**只做三件事** —— 等一个模式、发一段、把一切都逐字记下来。
它不替人下结论（结论在日志里那几行 `*_EXIT=` / `*_COUNT=` 上），
它只保证「看到的和敲下去的，逐字都在日志里」。

用法：

    sudo ./scripts/mipl.sh build                             # 1. 重建含新代码的 ISO
    sudo ./scripts/mipl.sh installer --serial console        # 2. 起 QEMU（另开一个终端）
    python3 installer/tests/live-e2e.py out/installer-serial.sock --log out/live-e2e.log

脚本**不启动也不关闭 QEMU** —— 那是 `mipl.sh` 的事（根文件的红线：命令一律走脚本）；
它只连上去、敲命令、记日志，最后 `poweroff`。

送进去的脚本一律走 `cat > 文件 <<'EOF'`（heredoc）：串口上嵌套引号是自找苦吃，
而 heredoc 让「敲下去的东西」在日志里就是**可读的一整段**，不是一堆转义。
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time
from pathlib import Path

#: 等提示符 / 短命令的上限。
DEFAULT_TIMEOUT = 90.0
#: 等装机（`pacstrap` 在 QEMU 里拉几百个包）的上限。
INSTALL_TIMEOUT = 3600.0

#: Live 里后端的位置：构建脚本把整个 `installer/` 拷到 `/usr/local/lib/mipl-installer/`。
BACKEND = "/usr/local/lib/mipl-installer/backend"
RUN = f"PYTHONPATH={BACKEND} python3 -m mipl_installer"

#: ANSI 控制序列：CSI（`\x1b[...m` 之类）、OSC（`\x1b]3008;...\x1b\\`，systemd 的会话跟踪）、
#: 以及字符集切换（`\x1b(B`）。串口上这些一个都不少 —— 见 `wait_for` 的说明。
_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"      # CSI
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r"|\x1b[()][A-Za-z0-9]"           # 字符集
)


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


#: 等到真正的 shell 提示符。**不要**用 `[#$] ?$` 这种宽松写法：heredoc 的内容会被
#: shell 逐行回显，而脚本里满是 `#` 注释与 `$` 变量 —— 宽松的正则会匹配到**回显**，
#: 于是「等命令跑完」变成「等自己刚发出去的那段文本」，命令根本没跑就往下走了。
#: 带上主机名之后，只有真提示符能匹配。
PROMPT = r"root@archiso[^\n]*#\s*$"


class Serial:
    """一根串口 + 一份逐字日志。"""

    def __init__(self, path: str, log_path: str | None = None) -> None:
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.sock.settimeout(0.2)
        self.log = open(log_path, "w", encoding="utf-8") if log_path else None
        self.log_path = log_path

    # ── 收 ────────────────────────────────────────────────────────────
    def pump(self) -> str:
        fresh = ""
        while True:
            try:
                chunk = self.sock.recv(65536)
            except (socket.timeout, OSError):
                break
            if not chunk:
                break
            fresh += chunk.decode("utf-8", errors="replace")
        if fresh and self.log is not None:
            self.log.write(fresh)
            self.log.flush()
        return fresh

    def wait_for(self, pattern: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
        """等到输出里出现 `pattern`（正则）。返回**这次等待期间**收到的全部原文。

        **匹配前先剥 ANSI**：bash 的提示符长这样 ——
        `root@archiso ~ # \\x1b[K\\x1b[?2004h`，`#` 后面还跟着一串控制序列。
        不剥的话 `[#$] ?$` 这种「提示符在行尾」的写法永远匹配不到 ——
        而它匹配不到时的表现是**超时**，看起来像「对面没反应」，实际是正则太天真。
        """
        rx = re.compile(pattern)
        deadline = time.monotonic() + timeout
        collected = ""
        while time.monotonic() < deadline:
            collected += self.pump()
            if rx.search(strip_ansi(collected)):
                return collected
            time.sleep(0.1)
        raise TimeoutError(
            f"等了 {timeout:.0f}s 也没等到 {pattern!r}\n"
            f"——最后收到的 3000 字（已剥 ANSI）：\n{strip_ansi(collected)[-3000:]}"
        )

    def drain(self, seconds: float = 2.0) -> str:
        """把接下来 `seconds` 秒的输出收干净（用于「命令跑完了，把结果收一下」）。"""
        deadline = time.monotonic() + seconds
        collected = ""
        while time.monotonic() < deadline:
            collected += self.pump()
            time.sleep(0.1)
        return collected

    # ── 发 ────────────────────────────────────────────────────────────
    def send(self, text: str) -> None:
        # 串口有回声，敲下去的东西本来就会回显一遍；这里只把**成段的脚本**额外记一笔，
        # 免得日志里出现一段没人知道是谁敲的代码
        self.sock.sendall(text.encode("utf-8"))

    def line(self, text: str) -> None:
        if self.log is not None:
            self.log.write(f"\n<<< {text}\n")
            self.log.flush()
        self.send(text + "\n")

    def script(self, name: str, body: str) -> None:
        """把一段脚本送进 Live 的 `/tmp/<name>`（heredoc，不做任何转义）。

        **送完必须等提示符回来。** 不等的话，heredoc 的回显还在路上，紧接着的
        `wait_for(哨兵)` 就会匹配到「脚本源码里那一行 `echo 哨兵`」的回显 ——
        命令一个都没跑，驱动却以为跑完了。这一条是实测踩出来的：
        第一轮就是这么在装机中途把 `poweroff` 发下去的。
        """
        if self.log is not None:
            self.log.write(f"\n<<< --- /tmp/{name} ---\n{body}<<< --- 结束 ---\n")
            self.log.flush()
        self.send(f"cat > /tmp/{name} <<'MIPL_EOF'\n{body}MIPL_EOF\n")
        self.wait_for(PROMPT, timeout=DEFAULT_TIMEOUT)
        self.drain(0.3)

    def run_script(self, name: str, sentinel: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        """跑 `/tmp/<name>`，等它的**真输出**里出现哨兵。

        到这里回显已经被 `script()` 消费干净了，所以哨兵只可能来自脚本的运行结果
        （`sh 文件` 本身不回显文件内容）。
        """
        self.line(f"sh /tmp/{name}")
        self.wait_for(sentinel, timeout=timeout)

    def close(self) -> None:
        if self.log is not None:
            self.log.close()
            self.log = None
        self.sock.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="经串口 socket 驱动 Live 里的安装器")
    parser.add_argument("socket", help="out/installer-serial.sock")
    parser.add_argument("--log", default=None, help="把串口上的每个字节记到这里")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"等提示符的超时（默认 {DEFAULT_TIMEOUT:.0f}s）")
    parser.add_argument("--probe-only", action="store_true",
                        help="只做只读取证（数据面 + 键位对账），不装盘")
    parser.add_argument("--verify-target", action="store_true",
                        help="不装盘，只把装好的目标盘只读挂上验一遍（检查点 5 的静态面）")
    parser.add_argument("--skip-cancel", action="store_true", help="跳过取消那一轮")
    return parser.parse_args(argv)


# ── 步骤 ──────────────────────────────────────────────────────────────
def wait_for_login(serial: Serial, timeout: float) -> None:
    """进 root shell —— **两种情况都要接得住**。

    串口上的 getty 由 systemd 的 getty-generator 按引导命令行里的 `console=ttyS0,115200`
    自动起 —— **没有** autologin（那份 drop-in 只挂在 `getty@tty1` 上），所以要自己登。
    Live 的 root 没有密码（`/etc/shadow` 里密码字段是空的），回车即可。

    为什么要「两种情况」：脚本连上去的时候，开机可能**早就开完了**，`login:` 那次输出
    在连接之前就过去了 —— 串口是流，不是文件，等一个已经发生过的模式等于永远等下去。
    所以先敲一个回车让对面重画提示符，再看它画出来的是 `login:` 还是 `#`。
    """
    serial.send("\n")
    deadline = time.monotonic() + timeout
    collected = ""
    while time.monotonic() < deadline:
        collected += serial.pump()
        plain = strip_ansi(collected)                # 提示符后面跟着控制序列，见 wait_for
        if re.search(r"[#$] ?$", plain):
            return                                   # 已经在一个 shell 里了
        if re.search(r"login:", plain):
            serial.line("root")
            time.sleep(1.0)
            serial.send("\n")                        # 空密码：有的 login 会问一次，有的不问
            serial.wait_for(PROMPT, timeout=timeout)
            return
        time.sleep(0.1)
    raise TimeoutError(
        f"等了 {timeout:.0f}s 也没等到 login: 或 shell 提示符\n"
        f"——收到的最后 3000 字（已剥 ANSI）：\n{strip_ansi(collected)[-3000:]}"
    )


PROBE_SCRIPT = f"""#!/bin/sh
# 只读取证：这一轮会看到哪几块盘、四份名单各多少条、键位解析对不对。
# 这些是**真机（Live）上的真数据** —— 验收要的正是「逐条能在真机上找到」。
#
# 头一段是**检查点 2 的证据**：安装器界面是不是自己起来了（不碰键盘就出来）。
# 它跑在 tty1 上，而我们在 ttyS0 上干活，所以两者互不打扰。
echo "PROBE-GUI-BEGIN"
echo "installer-active=$(systemctl is-active mipl-installer.service 2>&1)"
echo "installer-result=$(systemctl show -p Result --value mipl-installer.service 2>&1)"
echo "--- journalctl -u mipl-installer（末 30 行）---"
journalctl -u mipl-installer.service --no-pager -n 30 2>&1 | tail -30
echo "PROBE-GUI-END"
echo "PROBE-DISKS-BEGIN"
{RUN} --print-disks
echo "PROBE-DISKS-END"
echo "PROBE-COUNTS-BEGIN"
echo "lsblk=$(lsblk -dn -o NAME | wc -l)"
# 数**列表项**，不是「含引号的行」—— 后者会把 `"keymaps": [` 那一行也算进去，
# 于是每条都多 1。差一不影响「同量级」的判断，但会让人对着 253 和 252 查半天。
count() {{ {RUN} "$1" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['$2']))"; }}
echo "keymaps=$(count --print-keymaps keymaps)"
echo "locales=$(count --print-locales locales)"
echo "timezones=$(count --print-timezones timezones)"
echo "PROBE-COUNTS-END"
# 键位：解析结果与原文逐字对得上（Issue #65 的验收口径）
{RUN} --print-keymap de > /tmp/km.json
python3 -c "import json;print(chr(10).join(json.load(open('/tmp/km.json'))['lines']))" > /tmp/km.txt
zcat /usr/share/kbd/keymaps/i386/qwertz/de.map.gz > /tmp/km.raw
if diff -q /tmp/km.txt /tmp/km.raw > /dev/null; then echo "KEYMAP-VERBATIM=OK"; else echo "KEYMAP-VERBATIM=DIFF"; diff /tmp/km.txt /tmp/km.raw | head -20; fi
echo "PROBE-DONE"
"""

CANCEL_SCRIPT = f"""#!/bin/sh
# 取消那一轮：**装到 packages 阶段**再举手。
#
# 为什么挑 packages：那时盘已经擦过、也挂上了 —— 取消要是没走失败收尾那条路，
# /mnt 底下会留着一堆挂载点，而那正是最难查的现场（pipeline.run 的注释写着这条）。
echo "CANCEL-BEFORE-FINDMNT=[$(findmnt /mnt)]"
printf '%s\\n' mipltest | {RUN} --disk /dev/vda --yes --password-stdin --json-events \\
  --locale ja_JP.UTF-8 --keymap de --timezone Asia/Tokyo --hostname mipl-e2e \\
  > /tmp/cancel.jsonl 2> /tmp/cancel.err &
PID=$!
i=0
while [ $i -lt 900 ]; do
  if grep -q '"phase": "packages"' /tmp/cancel.jsonl 2>/dev/null; then break; fi
  i=$((i+1)); sleep 2
done
echo "CANCEL-PHASE-REACHED=$i"
sleep 5
kill -USR1 $PID && echo "CANCEL-SIGNAL-SENT"
wait $PID
echo "CANCEL-EXIT=$?"
echo "CANCEL-AFTER-FINDMNT=[$(findmnt /mnt)]"
echo "CANCEL-EVENTS-TAIL"
tail -8 /tmp/cancel.jsonl
echo "CANCEL-DONE"
"""

INSTALL_SCRIPT = f"""#!/bin/sh
# 真装一次：高级安装的三项都用**非默认值**，好让装后系统验得出差别
# （默认是 zh_CN.UTF-8 / us / Asia/Shanghai，验不出「选择真的写进去了」）。
printf '%s\\n' mipltest | {RUN} --disk /dev/vda --yes --password-stdin --json-events \\
  --log /tmp/ev.jsonl \\
  --locale ja_JP.UTF-8 --keymap de --timezone Asia/Tokyo --hostname mipl-e2e
echo "INSTALL-EXIT=$?"
echo "INSTALL-TARGET-FILES-BEGIN"
grep -H . /mnt/etc/locale.conf /mnt/etc/vconsole.conf /mnt/etc/hostname 2>&1
echo "INSTALL-TARGET-FILES-END"
# 事件流的**逐字**副本。串口会把非 ASCII 打成 U+FFFD（guest tty 层的锅，不是安装器的），
# 所以整份 base64 —— base64 是纯 ASCII，串口毁不掉。日志在 /tmp 里，重启就没了，
# 所以必须**这一轮**取出来。
echo "INSTALL-EVENTLOG-B64-BEGIN"
base64 -w0 /tmp/ev.jsonl
echo ""
echo "INSTALL-EVENTLOG-B64-END"
echo "INSTALL-DONE"
"""


def probe(serial: Serial, timeout: float) -> None:
    serial.script("probe.sh", PROBE_SCRIPT)
    serial.run_script("probe.sh", r"PROBE-DONE", timeout=timeout)


def cancel(serial: Serial) -> None:
    serial.script("cancel.sh", CANCEL_SCRIPT)
    serial.run_script("cancel.sh", r"CANCEL-DONE", timeout=INSTALL_TIMEOUT)


def install(serial: Serial) -> None:
    serial.script("install.sh", INSTALL_SCRIPT)
    serial.run_script("install.sh", r"INSTALL-DONE", timeout=INSTALL_TIMEOUT)


VERIFY_SCRIPT = f"""#!/bin/sh
# 检查点 5：把装好的目标盘**只读**挂上，直接读它写了什么。
#
# 为什么不用 `guestmount`：那要装 libguestfs（新增依赖，得先过维护者）。
# 而「回到 Live 把盘挂上看看」既不需要新东西，又是真机上人本来就会做的事。
# `-o ro` 是硬要求：这一步只读，一个字节都不该改。
mkdir -p /mnt
if mount -o ro /dev/vda2 /mnt; then
  echo "VERIFY-MOUNT=ok"
else
  echo "VERIFY-MOUNT=FAILED"
fi
echo "VERIFY-FILES-BEGIN"
for f in etc/locale.conf etc/vconsole.conf etc/hostname etc/locale.gen; do
  echo "--- /$f ---"
  cat "/mnt/$f" 2>&1 | head -5
done
echo "VERIFY-LOCALTIME=$(readlink /mnt/etc/localtime 2>&1)"
echo "VERIFY-JA-ENABLED=$(grep -c '^ja_JP.UTF-8' /mnt/etc/locale.gen 2>&1)"
echo "VERIFY-FSTAB-BEGIN"
cat /mnt/etc/fstab 2>&1
echo "VERIFY-FSTAB-END"
# ESP 是**另一个分区**（vda1）：只挂 root 的话 `/mnt/boot` 只是个空目录，
# 于是 `ls /mnt/boot/loader/entries/` 会报「没有那个文件」—— 那看着像缺陷，
# 其实是脚本自己没挂 ESP。引导项与 root UUID 的对照必须在这里做。
echo "VERIFY-BOOTLOADER"
mkdir -p /mnt/boot
if mount -o ro /dev/vda1 /mnt/boot; then
  echo "VERIFY-ESP=ok"
  ls /mnt/boot/loader/entries/ 2>&1
  cat /mnt/boot/loader/entries/miplinux.conf 2>&1
  # 引导项里的 root UUID 必须与实际 root 分区的 UUID 一致 —— 对不上就是「装完起不来」
  echo "VERIFY-ROOT-UUID=$(blkid -s UUID -o value /dev/vda2 2>&1)"
  umount /mnt/boot && echo "VERIFY-ESP-UMOUNT=ok"
else
  echo "VERIFY-ESP=FAILED"
fi
echo "VERIFY-FILES-END"
umount /mnt && echo "VERIFY-UMOUNT=ok"
# 事件流的**逐字**副本：串口会把非 ASCII 打成 U+FFFD（tty 层的锅，不是安装器的），
# 所以整个文件 base64 出来 —— base64 是纯 ASCII，串口毁不掉它。
echo "VERIFY-EVENTLOG-BEGIN"
if [ -f /tmp/ev.jsonl ]; then base64 -w0 /tmp/ev.jsonl; else echo "(没有 /tmp/ev.jsonl)"; fi
echo ""
echo "VERIFY-EVENTLOG-END"
echo "VERIFY-DONE"
"""


def verify_target(serial: Serial) -> None:
    """检查点 5 的静态面：读装好的盘（只读挂载），以及一份逐字的日志副本。"""
    serial.script("verify.sh", VERIFY_SCRIPT)
    serial.run_script("verify.sh", r"VERIFY-DONE", timeout=INSTALL_TIMEOUT)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not Path(args.socket).exists():
        print(f"[失败] 串口 socket 不存在：{args.socket}\n"
              f"  先起 QEMU： sudo ./scripts/mipl.sh installer --serial console", file=sys.stderr)
        return 2

    serial = Serial(args.socket, args.log)
    try:
        wait_for_login(serial, args.timeout)
        serial.line("uname -a; echo LIVE-READY")
        serial.wait_for(r"LIVE-READY", timeout=args.timeout)
        if args.verify_target:
            verify_target(serial)
            serial.line("poweroff")
            serial.drain(3.0)
            return 0
        probe(serial, args.timeout)
        if not args.probe_only:
            if not args.skip_cancel:
                cancel(serial)
            install(serial)
        serial.line("poweroff")
        serial.drain(3.0)
    except TimeoutError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    finally:
        serial.close()
    if args.log:
        print(f"串口逐字日志：{args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
