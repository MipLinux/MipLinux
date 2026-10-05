r"""键位预览：把 `.map.gz` 解析成「哪个键打哪个字符」，给界面画主键区图。

**为什么需要它（Issue #65）。** 键盘页只列一串名字（`us` / `de` / `be-latin1`）时，
选错的人要等到装完、进了 TTY 才发现自己按不出想要的字符 —— 那时系统已经装好了。
给一张主键区图是唯一能在**装之前**回答「这个布局长什么样」的办法。

**为什么不能用试打框。** 原来的键盘页有个输入框让人在里面敲字试效果。它在 Wayland
会话里测的是**合成器/桌面**的键位，而 `vconsole.conf` 管的是**装后系统的控制台** ——
两者不是同一套映射。试打通过不等于装完能用，等于用一个假证据替代真证据，所以删掉。

## 这个文件里只有事实，没有界面

`parse()` 吐的是「keycode N 的默认层是什么、Shift 层是什么」；**主键区的排布**
（哪几个 keycode 是一行、空格键画多宽）是界面的事，在 `renderer/js/backend.js`。
这里不画图、不认识 `KeyboardEvent.code`、不引图片资源。

## `.map.gz` 的三个坑（都在本机 `/usr/share/kbd/keymaps` 上实测过）

1. **`#` 与 `!` 都是注释符，而且不必在行首**（`man keymaps`）——
   `!	shift alt keycode 4 = VoidSymbol  # already has 8. bit set!`
   整行都是注释。所以要先按引号感知地剥注释，再谈解析。
2. **行尾 `\` 是续行**：一行的 keysym 列表可以跨好几条物理行
   （`keycode 2 = one exclam ... \` 后面还跟着 Meta_* 一整排）。不合并就会把后半截
   当成新的指令，整份映射读错。
3. **`include` 的三种写法各指不同目录**（源 issue 只写了其中一处）：
   `qwerty-layout` → `keymaps/i386/include/qwerty-layout.inc`、
   `euro2.map` → 同目录的 `euro2.map.gz`、
   `compose.latin1` → `keymaps/include/compose.latin1`（顶层，不在 i386 下）。
   所以候选路径要按「先本目录、再本架构 include/、最后顶层 include/」的顺序逐个试，
   而不是拼死一条路径。
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path

from .options import KEYMAP_ROOT
from .util import EXIT_USAGE, InstallerError

#: 展开 `include` 的最大深度。防的是**环**：键位表里 `a` include `b`、`b` include `a`
#: 是完全合法的写法，光靠「访问过的路径」去重挡不住「同一个文件被不同分支再次展开」，
#: 所以再压一道深度上限，让畸形数据以一句人话失败、而不是把进程拖死。
MAX_INCLUDE_DEPTH = 16

#: 形如 `keycode 2 = one exclam` / `altgr keycode 18 = euro` / `plain keycode 83 = KP_Comma`。
#: 修饰键前缀是**可选的一组小写词**；`strings as usual`、`compose 'a' 'b' to 'c'`
#: 这些不是键位绑定，所以要求整行里必须有 `keycode`。
_BINDING_RE = re.compile(
    r"^(?P<mods>(?:[a-z]+(?:\s+[a-z]+)*)\s+)?keycode\s+(?P<code>\d+)\s*=\s*(?P<syms>.+)$"
)

#: `include "qwerty-layout"` —— 只有这一种写法（名字一定在双引号里）。
_INCLUDE_RE = re.compile(r'^include\s+"(?P<name>[^"]+)"\s*$')

#: 认得出的修饰键。`plain` 是「没有修饰键」的另一种写法，归一化成空集。
_MODIFIERS = frozenset({"shift", "altgr", "control", "alt", "plain", "meta", "ctrl"})

#: `include` 找不到目标时给的提示（三种写法各自去哪儿找，写清楚省得下一个人再摸一遍）。
_INCLUDE_HINT = (
    "include 的目标按「本目录 → 本架构 include/ → 顶层 include/」的顺序找，"
    "自动补 .inc / .gz；.map 结尾的会在同目录找 .map.gz"
)


@dataclass(frozen=True)
class KeyView:
    """一个键的**主键区**要画的东西：默认层与 Shift 层。

    `shift` 可能为空串（映射里只写了一列），界面按「没有上层字符」处理 ——
    不拿默认层顶替：把 `a` 画成 `a / a` 是在编造原文里没有的东西。
    """

    code: int
    plain: str
    shift: str


@dataclass(frozen=True)
class IncludeRef:
    """一次 include 展开。`line` 是**引用它的那份文件**里的物理行号（1 起）。"""

    name: str
    path: str | None
    line: int


@dataclass(frozen=True)
class KeymapView:
    """一份键位映射解析完的样子。`lines` 是原文逐字，供「解析没吃掉东西」自证。"""

    name: str
    source: str
    lines: tuple[str, ...]
    includes: tuple[IncludeRef, ...]
    keys: tuple[KeyView, ...]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "lines": list(self.lines),
            "includes": [
                {"name": item.name, "path": item.path, "line": item.line}
                for item in self.includes
            ],
            "keys": [
                {"code": key.code, "plain": key.plain, "shift": key.shift}
                for key in self.keys
            ],
        }


# ── 读文件 ────────────────────────────────────────────────────────────
def read_map(path: Path) -> str:
    """读一份键位表。`.gz` 透明解压 —— `.inc` / `compose.*` 是纯文本。"""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8", errors="replace")


def find_keymap(name: str, root: str = KEYMAP_ROOT) -> Path:
    """名字 → 文件路径。名单页给的是不带 `.map.gz` 的 basename（`options.keymaps()`）。

    重名时**取路径字典序最小的那个**：本机 252 份键位表里没有重名，但真重名的话
    结果至少要稳定 —— 换台机器就换一份映射，是那种最难查的差异。
    """
    base = Path(root)
    if not base.is_dir():
        raise InstallerError(
            f"这台机器上没有键位表目录：{root}",
            EXIT_USAGE,
            hint="装 kbd 包；或者别用 --print-keymap",
        )
    wanted = f"{name}.map.gz"
    found = sorted(path for path in base.rglob("*.map.gz") if path.name == wanted)
    if not found:
        raise InstallerError(
            f"没有这份键位映射：{name}",
            EXIT_USAGE,
            hint="用 localectl 的写法（us、be-latin1）；名单见安装器的键盘页",
        )
    return found[0]


# ── 词法：注释与续行 ──────────────────────────────────────────────────
def strip_comment(line: str) -> str:
    """剥掉 `#` / `!` 到行尾的部分。**引号里的不算** —— `string FN = "a#b"` 是数据。

    引号感知这一层不能省：`compose '\\'' 'a' to '...'` 这类行里单引号是语法的一部分，
    粗暴地按第一个 `#` 切会把正经内容切掉。
    """
    quote: str | None = None
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
            continue
        if char in "#!":
            return line[:index]
    return line


def logical_lines(text: str) -> list[tuple[int, str]]:
    """物理行 → 逻辑行：剥注释、按行尾 `\\` 合并，返回 `(首个物理行号, 内容)`。

    行号是给报错用的 —— `include` 找不到目标时，人要知道是哪一行。
    """
    out: list[tuple[int, str]] = []
    pending: str | None = None
    start = 0

    for number, raw in enumerate(text.splitlines(), start=1):
        body = strip_comment(raw).rstrip()
        if pending is None:
            start = number
            pending = ""
        # 续行符留着不剥：先判断，再去掉
        if body.endswith("\\"):
            pending += body[:-1]
            continue
        pending += body
        out.append((start, pending.strip()))
        pending = None

    if pending is not None:
        out.append((start, pending.strip()))
    return out


# ── include 的三种写法 ────────────────────────────────────────────────
def include_candidates(name: str, includer: Path, root: Path) -> list[Path]:
    """`include "名字"` 可能指向的路径，按可信度排序（先找到的先用）。

    三种实测形态各自落在哪一段：

    | 写法 | 落点 | 靠哪一段命中 |
    |---|---|---|
    | `qwerty-layout` | `<arch>/include/qwerty-layout.inc` | 架构 include + 补 `.inc` |
    | `euro2.map` | `<arch>/include/euro2.map.gz` | 架构 include + 补 `.gz` |
    | `compose.latin1` | `include/compose.latin1` | 顶层 include + 原样 |

    `<arch>` 是**引用方所在目录的上一级**（`i386/qwertz/de.map.gz` → `i386`），
    所以 mac / ppc 那两套也自动走对，不用另写分支。
    """
    arch_include = includer.parent.parent / "include"
    top_include = root / "include"

    out: list[Path] = []
    for directory in (includer.parent, arch_include, top_include):
        out.append(directory / name)
        if not name.endswith((".inc", ".gz")):
            out.append(directory / f"{name}.inc")
            out.append(directory / f"{name}.gz")
            if name.endswith(".map"):
                out.append(directory / f"{name}.gz")
    return out


def resolve_include(name: str, includer: Path, root: Path) -> Path | None:
    for candidate in include_candidates(name, includer, root):
        if candidate.is_file():
            return candidate
    return None


# ── 解析与展开 ────────────────────────────────────────────────────────
def parse(name: str, root: str = KEYMAP_ROOT) -> KeymapView:
    """解析 `name` 并展开它的 include，返回主键区要用的那张表。

    合并语义就是 kbd 自己的语义：`include` 等价于**把对方的内容插在这一行**，
    于是后出现的绑定覆盖先出现的（同一个 keycode + 同一组修饰键）。
    `qwertz-layout` 给 `de` 补上字母键、`de` 自己再改掉其中几个，就是靠这个顺序。
    """
    root_path = Path(root)
    source = find_keymap(name, root)
    bindings: dict[tuple[int, tuple[str, ...]], tuple[str, ...]] = {}
    includes: list[IncludeRef] = []
    seen: list[Path] = []

    _expand(source, root_path, bindings, includes, seen, depth=0)

    keys: list[KeyView] = []
    for (code, mods), syms in bindings.items():
        if mods:  # 主键区只看默认层；Shift 层是同一条绑定的第 2 列
            continue
        keys.append(KeyView(code=code, plain=syms[0] if syms else "", shift=syms[1] if len(syms) > 1 else ""))
    keys.sort(key=lambda item: item.code)

    return KeymapView(
        name=name,
        source=str(source),
        lines=tuple(read_map(source).splitlines()),
        includes=tuple(includes),
        keys=tuple(keys),
    )


def _expand(
    path: Path,
    root: Path,
    bindings: dict[tuple[int, tuple[str, ...]], tuple[str, ...]],
    includes: list[IncludeRef],
    seen: list[Path],
    *,
    depth: int,
) -> None:
    if depth > MAX_INCLUDE_DEPTH:
        raise InstallerError(
            f"include 嵌套太深（>{MAX_INCLUDE_DEPTH}）：{path}",
            EXIT_USAGE,
            hint="键位表里可能有环；这是数据问题，不该由安装器猜一个终点",
        )
    if path in seen:
        # 同一个文件在**一条链**上再次出现 = 环。直接停：继续展开只会无限循环，
        # 而环形 include 在 kbd 里本来也是无意义的（后展开的会覆盖前一次）。
        return
    seen = [*seen, path]

    for line_number, text in logical_lines(read_map(path)):
        if not text:
            continue

        match = _INCLUDE_RE.match(text)
        if match:
            target = resolve_include(match.group("name"), path, root)
            includes.append(
                IncludeRef(name=match.group("name"), path=str(target) if target else None, line=line_number)
            )
            if target is None:
                # 找不到就把这一行**跳过**，不整体失败：一份键位表里丢掉一个 include
                # 只是少几个键，而键位页是给人做参考的，不该因此整页打不开。
                # 缺了哪一条在 includes 里写着 path=None，界面上标出来即可。
                continue
            _expand(target, root, bindings, includes, seen, depth=depth + 1)
            continue

        match = _BINDING_RE.match(text)
        if not match:
            continue
        # `plain keycode 83 = ...` 与 `keycode 83 = ...` 是同一件事，归一化成空集，
        # 否则同一个键会留下两条「默认层」记录，后一条把前一条盖掉，凭空少一个键。
        words = (match.group("mods") or "").split()
        mods = tuple(sorted(word for word in words if word in _MODIFIERS and word != "plain"))
        syms = tuple(match.group("syms").split())
        bindings[(int(match.group("code")), mods)] = syms
