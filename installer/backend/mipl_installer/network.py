"""Live 环境的网络状况（`nmcli`）—— 给界面与就绪检查用。

**只管 Live，不碰装后系统。** 装后系统的源与 reflector 策略是 Issue #23 / P11 的
事（见 [06](../../docs/knowledge/06-待定事项.md)）；这里只回答三个问题：

1. 现在通不通（有线还是无线）；
2. 周围有哪些无线网络、信号多强、要不要密码；
3. 让用户点一下把某个网络连上。

两处**不是随手写**的地方：

* `nmcli -t` 是 terse 格式：字段用 `:` 分隔，值里的 `:` 会转义成 `\\:`。
  用 `split(":")` 解析，SSID 叫 `My:Net` 就会被切成两段 —— 于是这个网络永远
  连不上，而错误现场看起来像「密码不对」。
* **密码不进 argv。** `nmcli ... password <明文>` 会把密码留在进程列表里
  （与安装器「密码只走 stdin」是同一条红线）。所以走 `--ask` + stdin。
"""

from __future__ import annotations

from .util import EXIT_USAGE, InstallerError, Runner

#: 无线信号是**百分比**（nmcli 的 SIGNAL 字段，0–100），**不是 dBm**。
#: 界面上不要把它写成 dBm —— 那是另一套量纲，换算要靠一个没人担保的经验公式。
MAX_SIGNAL = 100


def split_terse(line: str) -> list[str]:
    """`nmcli -t` 的一行 → 字段列表，按 nmcli 自己的转义规则拆分。

    转义规则：`\\:` 是值里的冒号，`\\\\` 是值里的反斜杠。
    """
    fields: list[str] = []
    buf: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            buf.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    fields.append("".join(buf))
    return fields


def _lines(runner: Runner, argv: list[str]) -> list[str]:
    """跑一条 `nmcli -t`，返回非空输出行；读不到就是空列表。

    读不懂的行**不该让整页空白**：nmcli 的字段在版本间会增删，所以下面两层各自
    丢掉自己不认的行，而不是整体报错。
    """
    if runner is None or getattr(runner, "dry_run", False):
        return []
    try:
        text = runner.run(argv, capture=True, check=False)
    except InstallerError:
        return []
    return [line for line in (text or "").splitlines() if line.strip()]


def _rows(runner: Runner, argv: list[str], width: int) -> list[list[str]]:
    """**定宽表**（`device status` / `wifi list`）：字段数不对的行丢掉。"""
    rows: list[list[str]] = []
    for line in _lines(runner, argv):
        fields = split_terse(line)
        if len(fields) == width:
            rows.append(fields)
    return rows


def split_keyed(line: str) -> tuple[str, str]:
    """`nmcli -t` 的 `KEY:value` 行 → (key, value)。

    **不能 `split(":", 1)`**：值里的冒号是转义过的（IPv6 地址里几乎全是冒号，
    nmcli 写成 `\\:`）。先按转义规则整体拆，再把第一段之后接回去 —— 接回去的
    正好是**还原后**的值，因为当分隔用的那些冒号本来就是未转义的。
    """
    fields = split_terse(line)
    if not fields:
        return "", ""
    return fields[0], ":".join(fields[1:])


def values_of(runner: Runner, argv: list[str]) -> list[str]:
    """`device show` 那类 `KEY:value` 输出的值列（空值丢掉）。"""
    out: list[str] = []
    for line in _lines(runner, argv):
        _, value = split_keyed(line)
        if value:
            out.append(value)
    return out


def devices(runner: Runner) -> list[dict[str, str]]:
    """设备清单：`[{device, type, state, connection}]`。"""
    return [
        {"device": device, "type": kind, "state": state, "connection": connection}
        for device, kind, state, connection in _rows(
            runner,
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
            4,
        )
    ]


def _ipv4(runner: Runner, device: str) -> str:
    """第一个 IPv4 地址（带前缀长度），没有就空串。

    ⚠️ `nmcli -t -f IP4.ADDRESS device show <dev>` 的输出是
    **`IP4.ADDRESS[1]:192.168.1.23/24`** —— 带字段名，不是「一行一个值」。
    曾经这里按定宽表（一行一个字段）解析，于是每一行都对不上，永远返回空串。
    「带字段名」这件事是拿真 nmcli 的输出核出来的（`nmcli 1.58.1`），不是推的。
    """
    for value in values_of(
        runner, ["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", device]
    ):
        return value
    return ""


def state(runner: Runner) -> dict:
    """网络现状。**读不到就当没通** —— 这里绝不假装在线。

    假装的代价很具体：装包阶段要联网，界面上写着「已连接」而实际没网，
    用户会一路点到 `pacstrap` 失败为止。
    """
    result = {
        "online": False,
        "wired": False,
        "wired_interface": "",
        "wired_ipv4": "",
        "wifi_interface": "",
        "wifi_ssid": "",
    }
    for item in devices(runner):
        # `connected` **与** `connected (externally)` 都算连着：后者是「别人
        # （不是 NetworkManager）管起来的链路」，流量照样通。判据取前缀而不是
        # 等号 —— 漏掉它的代价是「明明能上网，界面说没连」，而这一页没连就
        # 不让往下走（`submit()` 会去连网而不是继续），是个死结。
        #
        # loopback 除外：它永远连着，与「有没有网」无关。
        #
        # **局限（已知）**：这里判的是「有没有链路」，不是「真能不能出网」。
        # 一台只有 docker0 的机器会报 online=True。宁可这样：假阳性只是让人
        # 走到 `pacstrap` 才失败，假阴性是把人卡在网络页上出不去。
        if item["type"] == "loopback" or not item["state"].startswith("connected"):
            continue
        result["online"] = True
        if item["type"] == "ethernet" and not result["wired"]:
            result["wired"] = True
            result["wired_interface"] = item["device"]
            result["wired_ipv4"] = _ipv4(runner, item["device"])
        elif item["type"] == "wifi" and not result["wifi_ssid"]:
            result["wifi_interface"] = item["device"]
            result["wifi_ssid"] = item["connection"]
    return result


def wifi_networks(runner: Runner, *, rescan: bool = False) -> list[dict]:
    """周围的无线网络，**按信号从强到弱**。

    排序在这里做而不是在界面里：界面那边 `visibleNetworks` 是 `slice(0, n)`
    （「只画最强的几个」），它假定拿到手就是排好序的。

    `rescan=False` 用 NetworkManager 的缓存（快，进页面时用）；`rescan=True`
    让 NM 重新扫一遍（慢几秒，用户点「刷新」时用）。
    """
    argv = ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
    if not rescan:
        argv += ["--rescan", "no"]
    best: dict[str, dict] = {}
    for ssid, signal, security in _rows(runner, argv, 3):
        if not ssid:                      # 隐藏网络：没有 SSID 就没法让人选
            continue
        try:
            strength = int(signal)
        except ValueError:
            continue
        found = {
            "ssid": ssid,
            "signal": max(0, min(MAX_SIGNAL, strength)),
            "secured": bool(security.strip()) and security.strip() != "--",
        }
        # 同一个 SSID 可能有多个 AP，留信号最强的那个
        if ssid not in best or found["signal"] > best[ssid]["signal"]:
            best[ssid] = found
    return sorted(best.values(), key=lambda item: item["signal"], reverse=True)


def connect(runner: Runner, ssid: str, password: str = "") -> None:
    """连一个无线网络。

    **密码走 stdin，不进 argv**（`--ask` 让 nmcli 自己从标准输入读密钥）。
    其它失败原样抛 `InstallerError` —— 界面把 `render()` 的第二行当「下一步」显示。
    """
    if not ssid:
        raise InstallerError("没有选中网络", EXIT_USAGE)
    argv = ["nmcli", "--ask", "device", "wifi", "connect", ssid]
    if runner.dry_run:
        runner.run(argv)
        return
    runner.run(argv, input=f"{password}\n" if password else "\n")
