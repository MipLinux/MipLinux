#!/usr/bin/env python3
"""M2 验收（无头）：QEMU 里全程图形化装完一次，再从盘启动验一次。

**为什么需要它：** M2 的验收判据是「QEMU 里全程图形化装完一次」，而跑它的机器
常常没有显示器 —— CI、远程、以及按仓库规矩用 `pkexec` 提权时 `DISPLAY` 会被清掉
（[scripts/AGENTS.md](../../../scripts/AGENTS.md) 的坑 2）。「图形化」这件事因此
不能靠宿主的窗口来做。

QEMU 自己给了两只手，都走 QMP（JSON over unix socket）—— **不需要任何新依赖**：

| 要什么 | 用什么 |
|---|---|
| 眼睛 | `screendump`（QMP），每步一张 PNG |
| 手（点击） | `input-send-event` 的**绝对**坐标事件 —— 靠 `-device virtio-tablet-pci` |
| 手（打字） | `human-monitor-command` → HMP `sendkey` |
| 判「装完了没有」 | Live 的**串口 root shell**：`efibootmgr` + `mountpoint` 直接问客机 |

最后一条是有意的：**不靠截图比对去猜「这是不是结束页」**。装完的*事实*是固件里
有引导项、目标已经卸载干净 —— 那两件事问客机就有确定答案，截图只用来留证据。

用法（要 root；按仓库规矩走 pkexec，**不要** sudo）：

    pkexec /usr/bin/python3 installer/frontend/tools/gui-install.py
    pkexec /usr/bin/python3 installer/frontend/tools/gui-install.py --timeout 1800
    pkexec /usr/bin/python3 installer/frontend/tools/gui-install.py --skip-boot-check

产出（默认 `out/gui-install/`，已 gitignore）：

    00-loading.png …  每一步一张，按顺序命名
    steps.tsv         步骤名 / 时刻 / 截图文件名
    serial.log        串口全文（含我发的命令与它的回显）
    guest-check.txt   装完之后在客机里核对的输出
    qemu-live.log     第一轮（装）的 qemu 输出
    qemu-boot.log     第二轮（从盘启动）的 qemu 输出
"""
from __future__ import annotations

import argparse
import json
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

#: 目标盘（`mipl.sh` 挂上去的 virtio 盘；InstallDetailsPage 上显示的就是它）
TARGET_DISK = "/dev/vda"

#: 1280×800 上**主按钮**的中心。算法见 PageShell.qml：
#: `actionBar` 高 = 按钮 48 + 上下各 16 = 80，贴底 → y = 800-80+16+24 = 760；
#: `actionRow` 右缘 = (1280 + pageWidth)/2，按钮被推到右边，所以点「右缘 - 30」
#: 比点「右缘 - 半个按钮宽」稳 —— 按钮宽度随文案变，右边距是固定的。
PRIMARY_WIDE = (1050, 760)      # pageWidth 880：欢迎 / 网络 / 磁盘 / 安装 / 结束
PRIMARY_NARROW = (940, 760)     # pageWidth 660：分区 / 擦除确认 / 账户 / 详情

#: `Tokens.borderField` —— 输入框描边色。卡片描边（`Tokens.border`）是另一个色，
#: 所以它唯一定位输入框；聚焦后描边变焦点环色，所以要在**点击之前**找。
FIELD_BORDER = (203, 212, 226)

#: 字符 → HMP `sendkey` 的键名（US 布局；Live 的 vconsole 就是 us）
KEYS = {"/": "slash", "-": "minus", ".": "dot", " ": "spc"}

#: 固件里有引导项就算「引导写完了」—— 判据与 `boot._has_entry` 同一套
#: （bootctl 有时用 "Linux Boot Manager" 这个名字建项，只认标题会误判）。
EFI_ENTRY_RE = r"miplinux|linux boot manager|systemd-boot"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """去掉终端转义序列。

    `nmcli -t` 在串口 tty 上**照样会上色**（实测拿到的是 `\\x1b[32mconnected\\x1b[0m`），
    不剥掉的话 `^connected$` 这类判断永远不匹配 —— 脚本会「等一个已经到了的状态」
    一直等到超时。
    """
    return _ANSI_RE.sub("", text)


def keys_for(text: str) -> str:
    out: list[str] = []
    for char in text:
        if char.isalnum():
            out.append(char.lower())
        elif char in KEYS:
            out.append(KEYS[char])
        else:
            raise SystemExit(f"不知道怎么打这个字符：{char!r}")
    return "-".join(out)


# ── QMP：眼睛与手 ─────────────────────────────────────────────────────
class Qmp:
    def __init__(self, path: Path, timeout: float = 90.0) -> None:
        self.sock = _unix_connect(path, timeout)
        self.buf = b""
        self._read()                                   # greeting
        self.cmd("qmp_capabilities")

    def _read(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise SystemExit("QMP 连接断了")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        return json.loads(line)

    def cmd(self, name: str, **args):
        self.sock.sendall((json.dumps({"execute": name, "arguments": args}) + "\n").encode())
        while True:
            msg = self._read()
            if "error" in msg:
                raise RuntimeError(f"QMP {name} 失败：{msg['error']}")
            if "return" in msg:
                return msg["return"]

    def shot(self, path: Path) -> Path:
        """截一屏，落成**真 PNG**。

        `screendump` 给的是 PPM（要 qemu 自己编码得走 HMP 的 `-f png`），所以这里
        统一转一道 —— 产物要能直接用任何看图工具打开，不能是一个「扩展名叫 png
        的 ppm」。
        """
        from PIL import Image

        raw = path.with_name(path.stem + ".ppm")
        raw.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        self.cmd("screendump", filename=str(raw))
        for _ in range(250):
            if raw.exists() and raw.stat().st_size > 0:
                break
            time.sleep(0.02)
        else:
            raise SystemExit(f"screendump 没有产出 {raw}")
        Image.open(raw).save(path)
        raw.unlink(missing_ok=True)
        return path

    def click(self, point: tuple[int, int], screen: tuple[int, int] = (1280, 800)) -> None:
        """绝对坐标点击。坐标按 0..32767 归一化 —— virtio-tablet 是绝对指针。"""
        ax = round(point[0] / screen[0] * 32767)
        ay = round(point[1] / screen[1] * 32767)
        self.cmd("input-send-event", events=[
            {"type": "abs", "data": {"axis": "x", "value": ax}},
            {"type": "abs", "data": {"axis": "y", "value": ay}},
            {"type": "btn", "data": {"down": True, "button": "left"}},
            {"type": "btn", "data": {"down": False, "button": "left"}},
        ])

    def type_text(self, text: str, delay: float = 0.22) -> None:
        """一个键一个键地打，中间留出时间。

        **不能一次 `sendkey a-b-c-d` 打完整串。** 实测：`/dev/vda` 会被打成 `/deva`
        —— 中间三个键**悄无声息地丢了**（不是报错，是没到）。客机是软件渲染，输入
        链路（evdev → libinput → Qt）慢，一次发一串它来不及收。慢一点不值得冒险。
        """
        for char in text:
            self.cmd("human-monitor-command", **{"command-line": f"sendkey {keys_for(char)}"})
            time.sleep(delay)

    def use_absolute_pointer(self) -> str | None:
        """把 QEMU 的**当前鼠标**切到绝对指针（virtio-tablet），返回它的名字。

        两件实测出来的事，缺一条点击就不生效：

        1. 默认机型自带的 PS/2 鼠标是**相对**指针，`input-send-event` 的绝对坐标
           送给它会被直接丢掉、**不报任何错**。
        2. **必须在每次点击之前重申。** 客机的内核启用 VMware vmmouse 协议时，
           QEMU 会把「当前鼠标」自动切到 `vmmouse` —— 那之后再发绝对事件只能让
           指针**移动**（按钮出现悬停高亮），**按下的那一下不会变成点击**。
           开机早期切一次是不够的，会被这次激活抢走。

        （第 2 条是踩出来的：脚本在开机 10 秒时切好指针，之后所有点击都只产生
        悬停效果；把 `mouse_set` 挪到每次点击之前才通。）
        """
        mice = self.cmd("query-mice")
        tablet = next((m for m in mice if m.get("absolute") and "tablet" in m["name"].lower()),
                      None) or next((m for m in mice if m.get("absolute")), None)
        if tablet is None:
            return None
        self.cmd("human-monitor-command", **{"command-line": f"mouse_set {tablet['index']}"})
        time.sleep(0.1)
        return str(tablet["name"])


def _unix_connect(path: Path, timeout: float) -> socket.socket:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(path))
        except OSError:
            sock.close()
            time.sleep(0.2)
            continue
        sock.settimeout(60)
        return sock
    raise SystemExit(f"连不上 unix socket：{path}")


# ── 串口 root shell：问客机「装完没有」 ────────────────────────────────
class Serial:
    """Live 的串口控制台（`console=ttyS0`，root 空密码 —— 见 tech/04 §2.1）。

    命令输出用哨兵行夹起来：串口是带回显的 tty，把整段文本拿去做正则很容易撞上
    我自己敲的那行命令，夹起来之后 `run()` 只返回真正的输出。
    """

    def __init__(self, path: Path, timeout: float = 120.0) -> None:
        self.sock = _unix_connect(path, timeout)
        self.sock.setblocking(False)
        self.text = ""

    def pump(self, seconds: float = 0.3) -> str:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                chunk = self.sock.recv(1 << 20)
            except (BlockingIOError, socket.timeout):
                time.sleep(0.05)
                continue
            except OSError:
                break
            if not chunk:
                break
            self.text += chunk.decode("utf-8", "replace")
        return self.text

    def wait_for(self, pattern: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.3)
            if re.search(pattern, self.text, re.M):
                return True
        return False

    def login(self, timeout: float = 180.0) -> None:
        if not self.wait_for(r"login:\s*$", timeout):
            raise SystemExit("串口没有出现 login 提示符")
        self.sock.sendall(b"root\n")
        if not self.wait_for(r"@archiso[^\n]*#", 60):
            raise SystemExit("串口登录之后没有拿到 shell 提示符")

    def run(self, command: str, timeout: float = 30.0) -> str:
        tag = f"{int(time.time() * 1000) % 1000000}"
        begin, end = f"__MIPL_B{tag}__", f"__MIPL_E{tag}__"
        self.sock.sendall(f"echo {begin}; {command}; echo {end}\n".encode())
        if not self.wait_for(end, timeout):
            raise TimeoutError(f"客机里这条命令超时：{command}")
        chunk = self.text.rsplit(begin, 1)[-1].split(end)[0]
        return strip_ansi(chunk).strip("\r\n \t")


# ── 从**当前这一屏**找输入框（不靠参考图，字体差异影响不到）────────────
def fields_on(png: Path) -> list[tuple[int, int]]:
    from PIL import Image

    image = Image.open(png).convert("RGB")
    width, height = image.size
    pixels = image.load()
    edges: list[tuple[int, int, int]] = []
    for y in range(height):
        xs = [x for x in range(0, width, 2)
              if all(abs(pixels[x, y][i] - FIELD_BORDER[i]) <= 6 for i in range(3))]
        if len(xs) > 40:                       # 一条边至少横跨 ~80px
            edges.append((y, xs[0], xs[-1]))

    out: list[tuple[int, int]] = []
    i = 0
    while i < len(edges) - 1:
        top, bottom = edges[i], edges[i + 1]
        if bottom[0] - top[0] < 60:            # 同一个框的上边与下边（框高 48）
            x = (min(top[1], bottom[1]) + max(top[2], bottom[2])) // 2
            out.append((x, (top[0] + bottom[0]) // 2))
            i += 2
        else:
            i += 1
    return out


def mean_brightness(png: Path) -> float:
    from PIL import Image, ImageStat
    return ImageStat.Stat(Image.open(png).convert("L")).mean[0]


def digest(path: Path) -> str:
    import hashlib
    return hashlib.md5(path.read_bytes()).hexdigest()


def content_changed(before: Path, after: Path, minimum: int = 3000) -> tuple[bool, int]:
    """**行动区以上**的内容有没有变 —— 用来分辨「翻页」与「悬停」。

    为什么不能简单地看「整屏变了多少」：主按钮在 y=720..800 那条带里，鼠标移到
    按钮上就会让它变高亮，于是「没点动」也「有变化」。实测两个极端：

    * 悬停高亮：变化的像素**只在按钮那一小块**（约 0.4% 屏）；
    * 真翻页：内容区整片都换（网络页 → 磁盘页实测 3.4% 屏，分布在上百个列块里）。

    0.4% 与 3.4% 之间的阈值不好定，而且换一对页面就变 —— 所以这里改成**结构化的
    判据**：把行动区那条带整条排除，只看上面的内容。悬停碰不到内容区，翻页必然
    大动内容区。光标本身很小（几百像素），用一个下限把它挡掉。
    """
    from PIL import Image, ImageChops

    box = (0, 0, 1280, 715)
    left = Image.open(before).convert("L").crop(box)
    right = Image.open(after).convert("L").crop(box)
    binary = ImageChops.difference(left, right).point(lambda value: 1 if value > 20 else 0)
    changed = binary.histogram()[1]
    return changed > minimum, changed


# ── 起 / 停 QEMU ──────────────────────────────────────────────────────
def start_qemu(args: list[str], log: Path, extra: str) -> subprocess.Popen:
    env = dict(os.environ)
    env["MIPL_QEMU_EXTRA"] = extra
    handle = log.open("wb")
    return subprocess.Popen(["./scripts/mipl.sh", *args], cwd=REPO, env=env,
                            stdout=handle, stderr=subprocess.STDOUT, preexec_fn=os.setsid)


def stop_qemu(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gui-install.py",
                                     description="M2 验收：无头把安装器点完一遍")
    parser.add_argument("--out", default="out/gui-install", help="截图与日志落哪")
    parser.add_argument("--disk", default="target.qcow2",
                        help="目标盘（裸文件名按 out/ 解析）")
    parser.add_argument("--timeout", type=float, default=1800.0, help="等安装完成的上限（秒）")
    parser.add_argument("--boot-timeout", type=float, default=150.0, help="等从盘启动的上限（秒）")
    parser.add_argument("--window-timeout", type=float, default=240.0,
                        help="等安装器窗口画出来的上限（秒）")
    parser.add_argument("--skip-boot-check", action="store_true", help="只验装完，不验从盘启动")
    parser.add_argument("--keep", action="store_true", help="保留上一次的产出目录")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        raise SystemExit("需要 root：pkexec /usr/bin/python3 " + __file__)

    out = Path(args.out)
    if not out.is_absolute():
        out = REPO / out
    if out.exists() and not args.keep:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    mon = REPO / "out" / "gui-mon.sock"
    qmp_path = REPO / "out" / "gui-qmp.sock"
    ser_path = REPO / "out" / "installer-serial.sock"
    for path in (mon, qmp_path, ser_path):
        path.unlink(missing_ok=True)

    steps: list[tuple[str, float, str]] = []
    t0 = time.monotonic()

    def snap(qmp: Qmp, name: str) -> Path:
        path = out / f"{len(steps):02d}-{name}.png"
        qmp.shot(path)
        steps.append((name, round(time.monotonic() - t0, 1), path.name))
        print(f"  [{time.monotonic() - t0:6.1f}s] {path.name}", flush=True)
        return path

    #: `-display none` + 监控/QMP 两个 socket + **绝对指针**。
    #: `virtio-tablet-pci` 是本脚本唯一的设备增补 —— 默认的 PS/2 鼠标是相对指针，
    #: 没法「按坐标点」；它与安装器逻辑无关，只影响我们怎么把事件送进去。
    extra = (f"-display none -monitor unix:{mon},server,nowait "
             f"-qmp unix:{qmp_path},server,nowait -device virtio-tablet-pci")

    print("[1/3] 装：起 Live（cage + 安装器）", flush=True)
    # `--fresh-vars` 不是顺手加的：这一轮的完成判据是「**固件里有引导项**」，
    # 而目标盘的 NVRAM（`out/target.vars.fd`）默认是**保留**的 —— 上一次测试留下的
    # 那条 MipLinux 会让判据在安装刚开始时就成立，于是脚本报「装完了」而其实没有。
    # 清空之后，那条引导项只可能来自这一轮。
    live_args = ["qemu", "--disk", args.disk, "--boot", "d", "--serial", "console",
                 "--vga", "virtio", "--fresh-vars"]
    live = start_qemu(live_args, out / "qemu-live.log", extra)
    serial: Serial | None = None
    try:
        qmp = Qmp(qmp_path)
        pointer = qmp.use_absolute_pointer()
        if pointer is None:
            raise SystemExit("QEMU 里没有绝对指针设备 —— 检查 MIPL_QEMU_EXTRA 里的 "
                             "-device virtio-tablet-pci")
        print(f"      指针切到绝对设备：{pointer}", flush=True)
        serial = Serial(ser_path)
        serial.login()
        print("      串口 root shell 到手", flush=True)

        # 起点的现场：这一轮到底动了什么，得有对照
        before = serial.run(
            f"efibootmgr | head -8; echo ---; lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL {TARGET_DISK} "
            f"2>/dev/null || echo '(盘上还没有可列的东西)'", timeout=40)
        (out / "guest-before.txt").write_text(before, encoding="utf-8")
        print("      ── 装之前（对照）──", flush=True)
        for line in before.splitlines():
            print(f"      │ {line}", flush=True)

        # ── 等窗口画出来：加载页是浅色底 + 大 LOGO，黑屏时整帧很暗 ──────
        deadline = time.monotonic() + args.window_timeout
        while time.monotonic() < deadline:
            if mean_brightness(qmp.shot(out / "_probe.png")) > 120:
                break
            time.sleep(1.0)
        else:
            raise SystemExit("窗口一直没画出来 —— 看 out/gui-install/qemu-live.log")
        snap(qmp, "window-up")

        # 网络先就绪再进流程：网络页的状态是**进页面那一刻**读的，NM 还没连上时
        # 主按钮是「连接」而不是「继续」，点下去只会去连一个不存在的无线网。
        # 放在窗口出来之后：窗口要等十几秒到一分钟，NM 那时通常早就好了。
        print("      等 NetworkManager 连上（QEMU 用户网络）", flush=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if re.search(r"^connected\b",
                         serial.run("nmcli -t -f STATE general", timeout=20), re.M):
                break
            time.sleep(3)
        else:
            print("      ⚠ NetworkManager 一直没 connected —— 装包阶段会失败", flush=True)
        print(f"      联网状态：{serial.run('nmcli -t -f STATE,CONNECTIVITY general', timeout=20)}",
              flush=True)

        # 加载页等就绪探测 + 最小展示时间（qml/Main.qml 里 700ms），给足再进
        time.sleep(3.0)
        previous = snap(qmp, "welcome")

        def click_to(name: str, point: tuple[int, int], before: Path) -> Path:
            """点一下、截一屏，**并确认真的翻了页**。

            两条实测出来的门道，缺一条这个断言就会骗自己：

            1. **每次点击之前重申绝对指针** —— 客机启用 vmmouse 之后 QEMU 会把
               「当前鼠标」换成它，那之后绝对事件只能让指针移动、按下的那一下不生效；
            2. **不能只看「有没有变化」** —— 指针移到按钮上会让它变高亮，那也叫
               「有变化」。所以用 `content_changed()`：只看行动区**以上**的内容。
            """
            qmp.use_absolute_pointer()
            qmp.click(point)
            time.sleep(1.6)
            path = snap(qmp, name)
            moved, changed = content_changed(before, path)
            if not moved:
                raise SystemExit(
                    f"点完「{name}」之后内容区只变了 {changed} 个像素（悬停只有几百个）"
                    f"—— 点击没有送到客机（看 {path}）")
            return path

        for name in ("network", "disk", "partition"):
            previous = click_to(name, PRIMARY_WIDE, previous)

        # 擦除页：pageWidth 660 → 主按钮在窄位置
        erase = click_to("erase-confirm", PRIMARY_NARROW, previous)

        # 擦盘守卫：**逐字**输入设备路径。框的位置当场从这一屏上找。
        boxes = fields_on(erase)
        if len(boxes) != 1:
            raise SystemExit(f"擦除页应当有 1 个输入框，找到 {len(boxes)} 个")
        qmp.use_absolute_pointer()
        qmp.click(boxes[0])
        time.sleep(0.4)
        qmp.type_text(TARGET_DISK)
        time.sleep(0.8)
        typed = snap(qmp, "erase-typed")
        # 打字就看「有没有变化」就够了：这里没有悬停那种干扰。
        # ⚠️ 但**这条断言抓不到「打漏了几个键」** —— 聚焦后的蓝框 + 光标本身就足以
        # 让画面变化。真正兜底的是下面那次点击：路径不对时 `primaryEnabled` 是 false，
        # 点不动，`click_to` 的判据立刻失败（实测就是这样抓到 `/deva` 的）。
        if digest(typed) == digest(erase):
            raise SystemExit(f"在擦除页输入了 {TARGET_DISK}，但框里什么都没出现 —— "
                             f"`sendkey` 没送到客机（看 {typed}）")
        account = click_to("account", PRIMARY_NARROW, typed)

        fields = fields_on(account)
        print(f"      账户页找到 {len(fields)} 个输入框：{fields}", flush=True)
        if len(fields) < 3:
            raise SystemExit(f"账户页只找到 {len(fields)} 个输入框，点不下去")
        qmp.use_absolute_pointer()
        for (x, y), text in zip(fields, ("mipl", "mipl-2026", "mipl-2026")):
            qmp.click((x, y))
            time.sleep(0.4)
            qmp.type_text(text)
            time.sleep(0.4)
        filled = snap(qmp, "account-filled")
        if digest(filled) == digest(account):
            raise SystemExit(f"账户页三个框都填了，屏幕上没有任何变化（看 {filled}）")

        details = click_to("install-details", PRIMARY_NARROW, filled)
        click_to("install-start", PRIMARY_NARROW, details)          # 「开始安装」

        # ── 等装完：**问客机**，不猜截图 ────────────────────────────────
        #
        # 两条**简单**命令，再在宿主机这边合并判断。**不要写成一条带 `!` 的
        # 复合命令**：Live 的串口控制台是交互式 zsh，`! mountpoint` 会触发历史
        # 展开（`zsh: event not found`），于是判据永远不成立、脚本一直等到超时 ——
        # 而客机那边其实早就装完了（实测踩过：安装 16 分钟前就完成了，脚本还在
        # 打印「还在装」）。
        print("[2/3] 等安装完成（判据：固件里有引导项，且目标已卸载）", flush=True)
        done = False
        deadline = time.monotonic() + args.timeout
        next_shot = time.monotonic() + 60
        while time.monotonic() < deadline:
            time.sleep(5)
            try:
                efi = serial.run(
                    "efibootmgr 2>/dev/null | grep -Eic '"
                    + EFI_ENTRY_RE + "'", timeout=25)
                mounted = serial.run("mountpoint -q /mnt && echo yes || echo no", timeout=25)
            except TimeoutError:
                continue
            count = next((int(n) for n in re.findall(r"\d+", efi)), 0)
            if count and mounted.strip().endswith("no"):
                done = True
                break
            if time.monotonic() > next_shot:
                next_shot = time.monotonic() + 60
                stamp = int(time.monotonic() - t0)
                print(f"      … 还在装（{stamp}s；引导项 {count} 条，/mnt "
                      f"{'还挂着' if mounted.strip().endswith('yes') else '已卸载'}）", flush=True)
                snap(qmp, f"installing-{stamp}s")
        if not done:
            snap(qmp, "install-not-finished")
            raise SystemExit("等安装完成超时 —— 看 out/gui-install/ 里最后那几张图")
        time.sleep(5.0)                          # 收尾 → 结束页
        snap(qmp, "done")

        print("      ── 客机里核对 ──", flush=True)
        detail = serial.run(
            f"blkid {TARGET_DISK}1 {TARGET_DISK}2; echo ---; efibootmgr | head -12; "
            f"echo ---; mountpoint -q /mnt && echo '/mnt 还挂着' || echo '/mnt 已卸载'",
            timeout=40)
        (out / "guest-check.txt").write_text(detail, encoding="utf-8")
        for line in detail.splitlines():
            print(f"      │ {line}", flush=True)
    finally:
        # 串口全文**无论如何都要落盘**：脚本中途失败时，那份日志往往是唯一的现场
        # （第一版把写日志放在成功路径上，结果中途失败就什么都没有）。
        if serial is not None:
            (out / "serial.log").write_text(strip_ansi(serial.text), encoding="utf-8")
        stop_qemu(live)
        for path in (mon, qmp_path, ser_path):
            path.unlink(missing_ok=True)

    if not args.skip_boot_check:
        # ── 检查点 4：不挂 ISO、保留 NVRAM，从盘启动 ────────────────────
        # 装后系统的 loader entry 里**没有** `console=ttyS0`，所以这一轮只能看
        # 截图（systemd 输出 / 登录提示），串口是安静的。
        print("[3/3] 从盘启动：验检查点 4", flush=True)
        for path in (mon, qmp_path):
            path.unlink(missing_ok=True)
        boot = start_qemu(["qemu", "--disk", args.disk, "--boot", "c", "--serial", "console",
                           "--vga", "virtio"], out / "qemu-boot.log",
                          f"-display none -monitor unix:{mon},server,nowait "
                          f"-qmp unix:{qmp_path},server,nowait")
        try:
            qmp = Qmp(qmp_path)
            deadline = time.monotonic() + args.boot_timeout
            index = 0
            while time.monotonic() < deadline:
                time.sleep(8)
                index += 1
                frame = out / f"_boot{index}.png"
                qmp.shot(frame)
                bright = mean_brightness(frame)
                print(f"      第 {index} 帧（第 {index * 8}s）亮度 {bright:.1f}", flush=True)
                if bright > 20 and index >= 3:
                    break
            snap(qmp, "boot-from-disk")
        finally:
            stop_qemu(boot)
            for path in (mon, qmp_path):
                path.unlink(missing_ok=True)

    with (out / "steps.tsv").open("w", encoding="utf-8") as handle:
        handle.write("step\t秒\t截图\n")
        for name, at, file in steps:
            handle.write(f"{name}\t{at}\t{file}\n")

    print(f"\n产出：{out}", flush=True)
    for name, at, file in steps:
        print(f"  {at:7.1f}s  {name:22} {file}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
