#!/usr/bin/env python3
"""开机取证：逐秒截图 + 进客机取 journal，把「黑屏时间」拆到具体环节。

为什么需要它：只看「等了很久」没法改。这个脚本一次开机同时拿两样东西：

  1. **逐秒截图**（QEMU monitor 的 `screendump`，不是拍宿主窗口）——
     屏幕什么时候从黑变亮，一秒不差；
  2. **客机里的 journal**（`--serial console` 给的是走串口的 root shell，
     Live 的 root 空密码，见 tech/04 §2.1）—— `systemd-analyze`、`blame`、
     `journalctl -u mipl-installer`，以及若干条现场计时。

用法（需要 root；按仓库规矩走 pkexec，不要 sudo）：

    pkexec /usr/bin/python3 installer/frontend/tools/boot-probe.py
    pkexec /usr/bin/python3 installer/frontend/tools/boot-probe.py --seconds 150

产出（默认 `out/boot-probe/`，已 gitignore）：

    000.png …    每一秒一帧
    times.tsv    帧号 / 相对启动秒数 / 平均亮度 / 非白像素比例
    journal.txt  客机里取回来的输出（systemd-analyze / blame / journal）
    qemu.log     qemu 自己的输出

看图：`magick montage out/boot-probe/*.png -tile 12x -geometry +2+2 sheet.png`

2026-09-26 第一次跑出来的结论（用来说明这个脚本值不值）：
    引导菜单 12s 倒计时 → kernel+initramfs+squashfs ≈23s → systemd 用户态 38s
    （time-wait-sync 24.3s、ldconfig 17.7s、pacman-init 9.7s）→ cage 接管 ≈20s
    → fontconfig 第一次扫描 18.3s → 我们的界面 0.36s
    「页面变多导致黑屏变长」是错觉：首帧只解析 Main.qml + LoadingPage.qml。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MON = "/tmp/mipl-boot-mon.sock"

#: 进客机之后跑的命令。`time` 的输出走 stderr，同样会落到串口里。
GUEST_CMDS = [
    "echo === systemd-analyze ===",
    "systemd-analyze",
    "echo === blame ===",
    "systemd-analyze blame | head -12",
    "echo === mipl-installer ===",
    "journalctl -b -u mipl-installer -o short-monotonic --no-pager",
    "echo === 相关单元 ===",
    "journalctl -b -o short-monotonic --no-pager | grep -E 'cage|seatd|mipl' | tail -25",
    "echo === 字体（首次 / 第二次）===",
    "time fc-list > /dev/null",
    "time fc-list > /dev/null",
    "echo PROBE-DONE",
]


def _connect(path: str, deadline: float) -> socket.socket:
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(path)
            time.sleep(0.2)
            try:
                s.recv(1 << 20)          # 读掉 banner
            except socket.timeout:
                pass
            return s
        except OSError as exc:
            last = exc
            time.sleep(0.3)
    raise SystemExit(f"连不上 {path}：{last}")


def _frame_stats(png: Path) -> tuple[float, float]:
    from PIL import Image

    im = Image.open(png).convert("L")
    im.thumbnail((320, 320))
    px = list(im.getdata())
    return sum(px) / len(px), sum(1 for p in px if p > 200) / len(px)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="boot-probe.py", description="一次完整开机的取证")
    ap.add_argument("--seconds", type=int, default=170, help="最多录多少秒（默认 170）")
    ap.add_argument("--out", default="out/boot-probe", help="产出目录（默认 out/boot-probe）")
    ap.add_argument("--no-serial", action="store_true", help="只截图，不进客机取 journal")
    args = ap.parse_args(argv)

    if os.geteuid() != 0:
        raise SystemExit("需要 root：pkexec /usr/bin/python3 " + __file__)

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO / out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    serial_sock = REPO / "out" / "installer-serial.sock"
    for p in (MON, serial_sock):
        if os.path.exists(p):
            os.unlink(p)

    env = dict(os.environ)
    env["MIPL_QEMU_EXTRA"] = f"-display none -monitor unix:{MON},server,nowait"
    serial_arg = "file" if args.no_serial else "console"
    qlog = open(out / "qemu.log", "wb")
    proc = subprocess.Popen(
        ["./scripts/mipl.sh", "qemu", "--serial", serial_arg],
        cwd=REPO, env=env, stdout=qlog, stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    print(f"[probe] qemu pid {proc.pid}，等 monitor…", flush=True)

    mon = _connect(str(MON), time.monotonic() + 60)
    ser = None if args.no_serial else _connect(str(serial_sock), time.monotonic() + 60)
    if ser is not None:
        ser.setblocking(False)

    t0 = time.monotonic()
    deadline = t0 + args.seconds
    print(f"[probe] t0 = 现在，逐秒截图最多 {args.seconds}s", flush=True)

    rows: list[tuple[int, float, float, float]] = []
    buf, stage, i = "", "wait-login", 0
    while time.monotonic() < deadline:
        at = time.monotonic() - t0

        if ser is not None:
            try:
                chunk = ser.recv(1 << 20)
                if chunk:
                    buf += chunk.decode("utf-8", "replace")
                    (out / "serial.log").write_text(buf)
            except (socket.timeout, BlockingIOError, OSError):
                pass

            # 状态机只走一次：`login:` → root → 空密码 → shell → 一串命令
            if stage == "wait-login" and re.search(r"login:\s*$", buf, re.M):
                ser.sendall(b"root\n")
                stage = "wait-password"
                print(f"[probe] t={at:.1f}s 串口出现 login", flush=True)
            elif stage == "wait-password" and re.search(r"@archiso[^\n]*#", buf):
                stage = "wait-shell"          # archiso 的 root 空密码：直接就进去了
            elif stage == "wait-password" and re.search(r"Password:\s*$", buf, re.M):
                ser.sendall(b"\n")
                stage = "wait-shell"
            elif stage == "wait-shell" and re.search(r"@archiso[^\n]*#", buf):
                ser.sendall(("\n".join(GUEST_CMDS) + "\n").encode())
                stage = "wait-done"
                print(f"[probe] t={at:.1f}s 拿到 root shell，取 journal", flush=True)

        if at >= i:
            ppm, png = out / f"{i:03d}.ppm", out / f"{i:03d}.png"
            mon.sendall(f"screendump {ppm}\n".encode())
            for _ in range(60):
                if ppm.exists() and ppm.stat().st_size > 0:
                    break
                time.sleep(0.02)
            if ppm.exists():
                subprocess.run(["magick", str(ppm), str(png)],
                               capture_output=True, check=False)
                ppm.unlink(missing_ok=True)
                mean, bright = _frame_stats(png)
                rows.append((i, at, mean, bright))
            i += 1
            if i % 20 == 0:
                print(f"  t={at:6.1f}s 帧 {i:03d}", flush=True)

        if stage == "wait-done" and "PROBE-DONE" in buf:
            print(f"[probe] t={at:.1f}s journal 到手，收工", flush=True)
            break
        time.sleep(0.05)

    if ser is not None:
        m = re.search(r"=== systemd-analyze ===(.*?)PROBE-DONE", buf, re.S)
        (out / "journal.txt").write_text(m.group(1) if m else buf)
    with (out / "times.tsv").open("w") as fh:
        fh.write("frame\tsec\tmean\tbright_ratio\n")
        for r in rows:
            fh.write(f"{r[0]}\t{r[1]:.2f}\t{r[2]:.1f}\t{r[3]:.3f}\n")

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except OSError:
        pass
    time.sleep(2)
    stray = subprocess.run(["pgrep", "-f", "qemu-system-x86_64.*miplinux"],
                           capture_output=True, text=True).stdout
    for line in stray.splitlines():
        try:
            os.kill(int(line.split()[0]), signal.SIGTERM)
        except (OSError, ValueError):
            pass
    qlog.close()
    print(f"[probe] 完成：{len(rows)} 帧 → {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
