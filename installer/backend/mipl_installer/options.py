"""「高级安装」那几项的候选名单与校验：语言 / 键盘 / 时区 / 主机名 / 目标挂载点。

这几项都有能用的默认值，改的人是少数 —— 但它们一旦可选，就必须**真的生效**，
而且是**后端说了算**：界面上列出来的每一项，都得来自运行系统上真实存在的文件，
不能由前端另抄一份名单。

四个出处（都在运行系统上，Live 里就是出厂设置）：

| 项 | 名单 | 存在性判据 |
|---|---|---|
| 时区 | `/usr/share/zoneinfo/zone1970.tab` | `/usr/share/zoneinfo/<tz>` 是不是文件 |
| 键盘 | `/usr/share/kbd/keymaps/**/*.map.gz` | 名字在不在名单里 |
| 语言 | `/usr/share/i18n/SUPPORTED` | 目标系统的 `locale.gen` 里有没有这一行 |
| 主机名 | 没有名单，只有规则 | RFC 1123 |
| 目标挂载点 | 没有名单，只有命名空间 | `/mnt/` 下的规范化绝对路径（见 `validate_target()`） |

**名单读不到就是空的，绝不内建一份兜底名单。** 内建一份，就等于把
「界面里能选、写进目标却不生效」重新种回去 —— Issue #63 / #64 正是这么长出来的。
界面对空名单该说的是「这个环境列不出名单」，不是摆一排好看的假选项。
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone as dt_timezone
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from .util import DEFAULT_TARGET, EXIT_CONFIGURE, EXIT_USAGE, InstallerError

#: 都在**运行系统**上（Live 里就是出厂设置），路径可注入，测试里搭假目录即可。
ZONEINFO = "/usr/share/zoneinfo"
KEYMAP_ROOT = "/usr/share/kbd/keymaps"
LOCALE_SUPPORTED = "/usr/share/i18n/SUPPORTED"

#: 主机名：字母数字开头结尾，中间可以有连字符，单段最长 63。
#: 与 `HostnamePage.qml` 原来那条正则**同一条规则** —— 只是搬到了后端，
#: 前端改成调用（「唯一来源」在验证逻辑上的翻版，见 frontend/README.md）。
HOSTNAME_RE = re.compile(r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?")

#: 语言名的规范形态：`xx_YY.UTF-8`（`SUPPORTED` 里带字符集的那些）。
#: 字符集的大小写与 `-` 可以不同（`utf8` / `utf-8` / `UTF8` 是同一个字符集的写法）。
#: 用它只在**名单读不到**时兜底 —— 见 `validate_locale()` 的说明。
LOCALE_RE = re.compile(r"[a-z]{2,3}_[A-Z]{2}\.[Uu][Tt][Ff]-?8")


def locale_key(name: str) -> str:
    """locale 名的**比较键**：只归一字符集那一段（大小写、`-`、`_`）。

    语言 / 地区 / 修饰符保持原样 —— `zh_CN` 与 `zh_cn` 是两个名字，
    `sr_RS@latin` 与 `sr_RS` 也是；把整名的标点都抹掉会把它们错误地合并。
    `SUPPORTED` 写的是 `zh_CN.UTF-8`，而 `locale-gen` 生成、`locale -a` 列出的
    目录是 `zh_CN.utf8` —— 同一个 locale 的两种写法，靠这个键认回规范名。

    这是 locale 别名比较的**唯一实现**：`configure.py` 的 `has_locale()` /
    `enable_locales()`（#152）要按同一规则比，否则「preflight 放行、落盘前失败」。
    """
    base, dot, charset = name.rpartition(".")
    if not dot:
        return name
    return f"{base}.{charset.lower().replace('-', '').replace('_', '')}"

#: 键盘映射名的形态：`vconsole.conf` 的 `KEYMAP=` 收的是**单段 basename**
#: （`us`、`be-latin1`、`defkeymap_V1.0`），既不能是空串，也不能带目录或空白。
#: 与 `LOCALE_RE` 同一个用途：只用在本机列不出名单时兜底（见 `validate_keymap()`）。
KEYMAP_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")

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
    except (OSError, UnicodeDecodeError):
        # 解码失败与读不出来的后果一样：这台机器列不出名单。硬要读出一份半截
        # 名单，等于把「界面里能选、写进目标却不生效」重新种回去。
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

    只有能原样写进 `KEYMAP=` 的名字才进名单（见 `KEYMAP_RE`）：切成空串的
    `.map.gz`、带空白或斜杠的 basename 一律不列 —— 列出来就是让人选一个
    写进去不生效的值。
    """
    base = Path(root)
    if not base.is_dir():
        return []
    suffix = ".map.gz"
    found: set[str] = set()
    for path in base.rglob(f"*{suffix}"):
        name = path.name[: -len(suffix)]
        if KEYMAP_RE.fullmatch(name):
            found.add(name)
    return sorted(found)


def locales(path: str = LOCALE_SUPPORTED) -> list[str]:
    """`locale.gen` 生成得出来的语言名单（读 glibc 的 `SUPPORTED` 表）。

    一行形如 `zh_CN.UTF-8 UTF-8`，**第一列**才是 `--locale` 要的值。
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
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
            reason="notFound",
        )


def validate_keymap(keymap: str, root: str = KEYMAP_ROOT) -> None:
    """键盘映射必须真的存在。

    `/usr/share/kbd/keymaps` **不存在**时退到**形状检查** —— 与 `validate_locale()`
    同形：没装 kbd 的环境里列不出名单，但「一眼就不像」的名字（空串、带 `/`、
    带空白）仍然要挡掉，它们写进 `vconsole.conf` 只会得到 systemd 认不出的配置。
    名单在、名字不在 —— 那才是要拦的（Issue #64 的口径）。
    """
    available = keymaps(root)
    if available:
        if keymap not in available:
            raise InstallerError(
                f"键盘映射不存在：{keymap}",
                EXIT_CONFIGURE,
                hint="用 localectl 的写法，例如 us、be-latin1；可选名单见安装器的键盘页",
                reason="notInList",
            )
        return
    if not KEYMAP_RE.fullmatch(keymap):
        raise InstallerError(
            f"键盘映射名不合法：{keymap!r}",
            EXIT_CONFIGURE,
            hint="用 localectl 的写法，例如 us、be-latin1；这台机器列不出名单，只能按写法判断",
            reason="format",
        )


def validate_hostname(hostname: str) -> None:
    """RFC 1123。这条规则原来是**前端自己立的**（`HostnamePage.qml`），
    现在后端接管 —— 前端改成调用，不重写一份。"""
    if len(hostname) > MAX_HOSTNAME or not HOSTNAME_RE.fullmatch(hostname):
        raise InstallerError(
            f"主机名不合法：{hostname!r}",
            EXIT_CONFIGURE,
            hint=f"字母或数字开头、字母或数字结尾，中间可以有连字符，最长 {MAX_HOSTNAME} 字符",
            reason="format",
        )


def validate_locale(locale: str, path: str = LOCALE_SUPPORTED) -> None:
    """语言必须是这台机器**生成得出来**的一个（Issue #63）。

    要拦的是什么：界面上列了一份名单、用户挑了其中一项，而目标系统 `locale.gen`
    里根本没有这一行 —— 装出来的系统每个程序都报 `setlocale` 警告。
    `configure.py` 落盘前还会对着目标的 `locale.gen` 再查一遍（最后一道），
    但那已经是**盘擦干净之后**了；所以这一关提前到 `preflight()`。

    **名单读得到就按名单，读不到才退到形状检查。** 与 `validate_keymap()` 同形：
    名单为空时不装作能判断，只是把「一眼就不像」的名字挡掉。
    这里没有采用「在名单里**或**形如 `xx_YY.UTF-8` 就放行」的读法 —— 那样一个
    拼错的名字（`ja_XX.UTF-8`）会通过 preflight，然后在 chroot 里以
    `EXIT_CONFIGURE` 失败，而那正是这条校验要提前的失败。

    **别名按 `locale_key()` 认回名单里的规范名。** `zh_CN.utf8` 与 `SUPPORTED`
    里的 `zh_CN.UTF-8` 是同一个 locale（`locale-gen` 生成的目录就叫 `zh_CN.utf8`），
    CLI 传前者不该在 preflight 被拒。只归一字符集 —— `zh_CN` / `zh_cn` /
    `sr_RS@latin` 这些语言、地区、修饰符的差异仍然各算各的（不过度合并）。
    `configure.py` 的 `has_locale()` / `enable_locales()` 必须用同一个键（#152）；
    否则「preflight 放行、落盘前失败」，那正是这条校验要提前的失败。
    """
    available = locales(path)
    if locale in available:
        return
    if available:
        known = {locale_key(name) for name in available}
        if locale_key(locale) in known:
            return
        raise InstallerError(
            f"语言不在名单里：{locale}",
            EXIT_CONFIGURE,
            hint="用 /usr/share/i18n/SUPPORTED 里的写法，例如 zh_CN.UTF-8；可选名单见安装器的语言页",
            reason="notInList",
        )
    if not LOCALE_RE.fullmatch(locale):
        raise InstallerError(
            f"语言名不合法：{locale!r}",
            EXIT_CONFIGURE,
            hint="形如 xx_YY.UTF-8（字符集也可写 utf8），例如 ja_JP.UTF-8；这台机器列不出名单，只能按写法判断",
            reason="format",
        )


def validate_target(target: str) -> None:
    """目标挂载点必须落在安装器的保留命名空间 `/mnt/` 下，且是规范写法。

    这条校验挡的是**开工前那次自动清理**（`disk.cleanup_stale_target`）——它按
    「挂载点在 `target` 之下」判定归属，然后 `umount -R`。归属判据只在 `target`
    本身可信时才成立：`target` 取 `/` 时，整台机器都算「我们的」，清理会把运行中
    的系统卸掉；取 `/mnt` 时，用户自己挂在 `/mnt` 的盘会被当成残留。

    而 `--target` 是 CLI 可传的参数，清理又跑在 `preflight()` 与守卫**之前**，
    所以「传错了」在这里的代价不是报错，是**先卸了再说**。GUI 不发这个字段
    （走 `DEFAULT_TARGET`），可达路径只有 CLI —— 但校验没有理由因此缺席。

    规范化也一并要求（`/mnt/mipl/`、`/mnt//x`、`/mnt/./x`、含 `..` 的写法全拒）：
    归属判定拿字符串前缀去比 `/proc/self/mountinfo` 里的挂载点，一个能指向同一
    位置却长得不一样的写法，会让「是不是我们的」这个判断悄悄失准。`..` 尤其要
    单独拦：`PurePosixPath` 只做词法规范化、**不解析 `..`**，光靠它会漏掉
    `/mnt/../etc` 这种「前缀像 `/mnt/`、解析后是 `/etc`」的写法。

    **字符串合法还不够：`mount` / `umount` 都会解析符号链接。** `/mnt/mipl -> /proc`
    能过上面每一条，却把一次 `umount -R`（或一次挂载）落到真实路径上；指向 `/` 时
    足以影响运行中的系统。所以再按 `realpath` 比一次：只接**解析后与字面完全一致**
    的写法 —— 保留命名空间里的链接同样不认，归属判据才只有一个答案。

    两个挂载点都要查：`target` 与 `target/boot`（ESP 挂在后者，`disk.py` 会
    `mount` / `umount -R` 它）。只查前者的话，`/mnt/mipl/boot -> /` 仍然能把一次
    递归卸载带到整台机器上。
    """
    components = PurePosixPath(target).parts if target else ()
    if (
        not target.startswith("/mnt/")
        or ".." in components
        or str(PurePosixPath(target)) != target
    ):
        raise InstallerError(
            f"目标挂载点不合法：{target!r}",
            EXIT_USAGE,
            hint=f"/mnt/ 下的规范化绝对路径，例如 {DEFAULT_TARGET}（不要用 /、/mnt 或带 .. 的写法）",
            reason="format",
        )
    for path in (target, f"{target}/boot"):
        resolved = os.path.realpath(path)
        if resolved != path:
            raise InstallerError(
                f"目标挂载点不能经过符号链接：{path!r}（实际指向 {resolved!r}）",
                EXIT_USAGE,
                hint=f"/mnt/ 下的真实目录，例如 {DEFAULT_TARGET}；不要用指向别处的链接",
                reason="format",
            )
    # 已存在的部分必须是**目录**。`ensure_dir()` 跑在盘擦完之后，撞上一个同名普通
    # 文件才抛 `FileExistsError` —— 那时分区已经没了，失败点远在动盘之后。
    probe = target
    while True:
        if os.path.exists(probe) and not os.path.isdir(probe):
            raise InstallerError(
                f"目标挂载点已存在但不是目录：{probe!r}",
                EXIT_USAGE,
                hint=f"{DEFAULT_TARGET} 这类路径要么不存在（安装器会建），要么是目录",
                reason="format",
            )
        if probe == "/mnt":
            break
        probe = os.path.dirname(probe)
