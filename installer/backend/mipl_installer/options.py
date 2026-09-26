"""「高级安装」那四项的候选名单与校验：语言 / 键盘 / 时区 / 主机名。

这四项都有能用的默认值，改的人是少数 —— 但它们一旦可选，就必须**真的生效**，
而且是**后端说了算**：界面上列出来的每一项，都得来自运行系统上真实存在的文件，
不能由前端另抄一份名单。

四个出处（都在运行系统上，Live 里就是出厂设置）：

| 项 | 名单 | 存在性判据 |
|---|---|---|
| 时区 | `/usr/share/zoneinfo/zone1970.tab` | `/usr/share/zoneinfo/<tz>` 是不是文件 |
| 键盘 | `/usr/share/kbd/keymaps/**/*.map.gz` | 名字在不在名单里 |
| 语言 | `/usr/share/i18n/SUPPORTED` | 目标系统的 `locale.gen` 里有没有这一行 |
| 主机名 | 没有名单，只有规则 | RFC 1123 |

**名单读不到就是空的，绝不内建一份兜底名单。** 内建一份，就等于把
「界面里能选、写进目标却不生效」重新种回去 —— Issue #63 / #64 正是这么长出来的。
界面对空名单该说的是「这个环境列不出名单」，不是摆一排好看的假选项。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .util import EXIT_CONFIGURE, InstallerError

#: 都在**运行系统**上（Live 里就是出厂设置），路径可注入，测试里搭假目录即可。
ZONEINFO = "/usr/share/zoneinfo"
KEYMAP_ROOT = "/usr/share/kbd/keymaps"
LOCALE_SUPPORTED = "/usr/share/i18n/SUPPORTED"

#: 主机名：字母数字开头结尾，中间可以有连字符，单段最长 63。
#: 与 `HostnamePage.qml` 原来那条正则**同一条规则** —— 只是搬到了后端，
#: 前端改成调用（「唯一来源」在验证逻辑上的翻版，见 frontend/README.md）。
HOSTNAME_RE = re.compile(r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?")

MAX_HOSTNAME = 63


# ── 名字必须待在它自己的根里 ──────────────────────────────────────────
def confined(root: str, value: str) -> Path | None:
    """把用户给的名字限制在 `root` 之内；绝对路径与 `..` 一律不认（返回 None）。

    为什么要有这一关：`ln -sf /usr/share/zoneinfo/<名字>` 是拼出来的路径，
    而 `<名字>` 来自界面。`../../etc/passwd` 这种名字能让存在性检查**通过**，
    然后被当成合法时区写进目标 —— 那不是「用户输错了」，是路径逃逸。
    """
    if not value or value.startswith("/"):
        return None
    parts = Path(value).parts
    if not parts or ".." in parts:
        return None
    return Path(root).joinpath(*parts)


# ── 名单 ──────────────────────────────────────────────────────────────
def timezones(root: str = ZONEINFO) -> list[str]:
    """IANA 时区名单。

    用 `zone1970.tab` 而不是遍历目录：目录里混着 `posix/`、`right/`、`SystemV/`
    这些同义树与历史名，摆进界面只会让人选错。
    """
    tab = Path(root) / "zone1970.tab"
    if not tab.is_file():
        tab = Path(root) / "zone.tab"
    try:
        text = tab.read_text(encoding="utf-8")
    except OSError:
        return []

    out: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 3:
            out.append(fields[2])
    return out


def zone_offset(tz: str, root: str = ZONEINFO, *, now: datetime | None = None) -> str | None:
    """这个时区**当前**的 UTC 偏移，形如 `UTC+08:00`；取不到就 None。

    「当前」是有意的：夏令时会变，界面上这一列只是提示，真正写进目标的是
    那个 `id`（符号链接）。两者分工不同，所以显示值不会冒充生效值。
    """
    path = confined(root, tz)
    if path is None or not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            zone = ZoneInfo.from_file(handle, key=tz)
        moment = now if now is not None else datetime.now(dt_timezone.utc)
        delta = moment.astimezone(zone).utcoffset()
    except (OSError, ValueError, KeyError):
        return None
    if delta is None:
        return None

    seconds = int(delta.total_seconds())
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(seconds)
    return f"UTC{sign}{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def keymaps(root: str = KEYMAP_ROOT) -> list[str]:
    """控制台键盘映射的名单（`/etc/vconsole.conf` 里 `KEYMAP=` 的取值）。

    取的是**不带 `.map.gz` 的 basename**：`systemd-vconsole-setup` 与 `localectl`
    用的就是这个写法（`us`、`be-latin1`）。把目录层级写进去（`i386/qwerty/us`）
    在自己这套 `find` 里看着对，但在 `vconsole.conf` 里不保证被认出来。
    """
    base = Path(root)
    if not base.is_dir():
        return []
    suffix = ".map.gz"
    found = {path.name[: -len(suffix)] for path in base.rglob(f"*{suffix}")}
    return sorted(found)


def locales(path: str = LOCALE_SUPPORTED) -> list[str]:
    """`locale.gen` 生成得出来的语言名单（读 glibc 的 `SUPPORTED` 表）。

    一行形如 `zh_CN.UTF-8 UTF-8`，**第一列**才是 `--locale` 要的值。
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []

    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped.split()[0])
    return out


# ── 校验（全部在后端，前端只调用）───────────────────────────────────────
def validate_timezone(tz: str, root: str = ZONEINFO) -> None:
    """时区必须真的存在。

    不校验的后果就是 Issue #66：`ln -sf /usr/share/zoneinfo/<打错的>` 会**成功**
    建出一个悬空软链（`ln` 不检查目标），装出来的系统时间不对，而且要等到第一次
    翻日志才发现。
    """
    path = confined(root, tz)
    if path is None or not path.is_file():
        raise InstallerError(
            f"时区不存在：{tz}",
            EXIT_CONFIGURE,
            hint="用 IANA 名字，例如 Asia/Shanghai；可选名单见安装器的时区页",
        )


def validate_keymap(keymap: str, root: str = KEYMAP_ROOT) -> None:
    """键盘映射必须真的存在。

    `/usr/share/kbd/keymaps` **不存在**时跳过：没装 kbd 的环境里无从判断，
    而这时 `KEYMAP` 本来就只在 TTY 生效，写个名字进去不会比现在更糟。
    名单在、名字不在 —— 那才是要拦的（Issue #64 的口径）。
    """
    available = keymaps(root)
    if not available:
        return
    if keymap not in available:
        raise InstallerError(
            f"键盘映射不存在：{keymap}",
            EXIT_CONFIGURE,
            hint="用 localectl 的写法，例如 us、be-latin1；可选名单见安装器的键盘页",
        )


def validate_hostname(hostname: str) -> None:
    """RFC 1123。这条规则原来是**前端自己立的**（`HostnamePage.qml`），
    现在后端接管 —— 前端改成调用，不重写一份。"""
    if len(hostname) > MAX_HOSTNAME or not HOSTNAME_RE.fullmatch(hostname):
        raise InstallerError(
            f"主机名不合法：{hostname!r}",
            EXIT_CONFIGURE,
            hint=f"字母或数字开头、字母或数字结尾，中间可以有连字符，最长 {MAX_HOSTNAME} 字符",
        )
