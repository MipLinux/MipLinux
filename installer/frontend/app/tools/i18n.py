#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""i18n 生成 / 守卫 —— tech/09 的过审文案表 ↔ 渲染层两份 JSON。

为什么要有它
------------
文案的唯一源是 `docs/work/tech/09-安装器界面文案.md` 第三节那张审核表（条数以它为准，别在这里抄数）。
渲染层读的是 `renderer/i18n/{zh_CN,en_US}.json`。两者之间**只能有一份真相**：
JSON 由本脚本从表里生成，`--check` 再逐字比对回去 —— 改了表没重生成、或手改了 JSON，都会红。

用法
----
    python3 app/tools/i18n.py --write   # 从表生成两份 JSON
    python3 app/tools/i18n.py --check   # 比对（默认；退出码 0 = 一致）
    python3 app/tools/i18n.py --check --quiet

纪律
----
- **只把第三节当界面文案**。附 A 的时区名表（34 条）另有用处：它是 `renderer/js/tz-names.js` 的名字源，
  也是**后端随包时区表的名单源**（D19）—— `--check` 因此会顺手比一次两者逐条一致（`check_zone_table`）。
- 表里为了标重点用的 `**…**` 是**审阅排版**，落进 JSON 时去掉；界面上的强调由 CSS 表达。
- 只依赖标准库；不需要 root、不需要 Live、不联网。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: 第三节的起止标题（含）。
SECTION_START = "## 三、文案"
SECTION_END = "## 四、i18n 机制"

#: 附 A 时区名表的起止标题（含）。34 条中英已过审，以 `timezone.name.<IANA>` 入 JSON。
ZONE_START = "## 附 A"
ZONE_END = "## 附 B"

#: D19 的后端随包时区表（**名单**，相对仓库根）——`--check` 比它一眼，防名字与名单各走各的。
CHECK_ZONE_TABLE = "installer/backend/mipl_installer/data/timezones.txt"

#: 审核表里出现、但**不是**界面文案的元行 —— 它们是给维护者看的说明。
META_IDS = {"timezone.name.<IANA>", "timezone.fallback"}

#: 删除标记（`~~\`id\`~~`）—— 已作废的串，连行都不该出现。
DELETED_MARK = "~~"

ROW_RE = re.compile(r"^\|\s*`([A-Za-z][\w.\-]*)`\s*\|(.*)\|\s*$")

DEFAULT_DECK = "docs/work/tech/09-安装器界面文案.md"


def find_up(start: Path, rel: str) -> Path:
    for parent in [start, *start.parents]:
        candidate = parent / rel
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"往上找不到 {rel}（从 {start} 起）")


def strip_review_markup(cell: str) -> str:
    """去掉审阅排版：`**粗体**` 与可能包裹整格的 `…` 反引号。"""
    text = cell.replace("**", "").strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1]
    return text


def parse_zone_names(text: str) -> dict[str, dict[str, str]]:
    """附 A 的时区名表 → {"timezone.name.<IANA>": {"zh_CN": …, "en_US": …}}。

    这张表**不是**第三节那种 `| ID | 中 | 英 |` 形状，而是 `| IANA id | 中 | 英 |`，
    所以单独解析。审核口径相同：改名字必须过维护者。
    """
    start = text.find(ZONE_START)
    if start < 0:
        raise ValueError(f"找不到「{ZONE_START}」")
    end = text.find(ZONE_END, start)
    if end < 0:
        raise ValueError(f"找不到「{ZONE_END}」")
    section = text[start:end]

    entries: dict[str, dict[str, str]] = {}
    for line in section.splitlines():
        match = re.match(r"^\|\s*`([A-Za-z][\w+\-/]*)`\s*\|(.*)\|\s*$", line)
        if not match:
            continue
        cells = [c.strip() for c in match.group(2).split("|")]
        if len(cells) != 2:
            raise ValueError(f"时区「{match.group(1)}」这行不是三列：{line!r}")
        entries[f"timezone.name.{match.group(1)}"] = {
            "zh_CN": strip_review_markup(cells[0]),
            "en_US": strip_review_markup(cells[1]),
        }
    return entries


def parse_all(text: str) -> dict[str, dict[str, str]]:
    """第三节的界面文案 + 附 A 的时区名 = 完整键空间。"""
    entries = parse_deck(text)
    zones = parse_zone_names(text)
    clash = sorted(set(entries) & set(zones))
    if clash:
        raise ValueError(f"第三节与附 A 的键撞了：{clash[:5]}")
    entries.update(zones)
    return entries


def parse_deck(text: str) -> dict[str, dict[str, str]]:
    """第三节 → {id: {"zh_CN": …, "en_US": …}}。"""
    start = text.find(SECTION_START)
    if start < 0:
        raise ValueError(f"找不到「{SECTION_START}」")
    end = text.find(SECTION_END, start)
    if end < 0:
        raise ValueError(f"找不到「{SECTION_END}」")
    section = text[start:end]

    entries: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for line in section.splitlines():
        raw_cells = line.split("|")
        # 作废行形如 `| ~~`id`~~ | 已删除… | — |` —— 连解析都不该进
        if len(raw_cells) > 1 and DELETED_MARK in raw_cells[1]:
            continue
        match = ROW_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        cells = [c.strip() for c in match.group(2).split("|")]
        if key in META_IDS:
            skipped.append(key)
            continue
        if len(cells) != 2:
            raise ValueError(f"「{key}」这行不是三列（ID / 中 / 英）：{line!r}")
        entries[key] = {
            "zh_CN": strip_review_markup(cells[0]),
            "en_US": strip_review_markup(cells[1]),
        }
    if skipped:
        print(f"（跳过 {len(skipped)} 条元行：{', '.join(skipped)}）", file=sys.stderr)
    return entries


def zone_ids_from_names(zone_entries: dict[str, dict[str, str]]) -> list[str]:
    """附 A 的键 → IANA id（保持表里的顺序）。"""
    return [key[len("timezone.name."):] for key in zone_entries]


def check_zone_table(zone_entries: dict[str, dict[str, str]], *, root: Path | None = None) -> int:
    """名单守卫：附 A 的时区（= 有名字的那批）⇄ D19 的后端随包表，返回不一致的处数。

    **两个方向都要报**：
    - 表里少了 → 界面列不出这个区，而我们已经为它过审过一个名字（名字成了死键）；
    - 表里多了 → 界面会出现一个没有过审名字的区（显示成 IANA id），D19 的入表条件被绕过。

    表的**逐字生成**与刷新由 `tools/gen-timezones.py` 负责；这里只回答
    「名字与名单还是同一批吗」—— 这样任何一次 `--check` 都能拦住「改了一边忘了另一边」。
    """
    table = (root if root is not None else Path(__file__).resolve().parents[4]) / CHECK_ZONE_TABLE
    try:
        table_ids = [
            name
            for line in table.read_text(encoding="utf-8").splitlines()
            if (name := line.split("#", 1)[0].strip())
        ]
    except OSError as exc:
        print(f"❌ 读不到时区表 {table}：{exc}")
        return 1

    problems = 0
    missing = [zone for zone in zone_ids_from_names(zone_entries) if zone not in table_ids]
    extra = [zone for zone in table_ids if f"timezone.name.{zone}" not in zone_entries]
    if missing:
        print(f"❌ 时区表里少了附 A 已过审的 {len(missing)} 条：{missing[:6]}")
        print("   （跑 tools/gen-timezones.py --write 重生成；要改名单先改附 A）")
        problems += 1
    if extra:
        print(f"❌ 时区表里有附 A 没名字的 {len(extra)} 条：{extra[:6]}")
        print("   （D19 的入表条件是在附 A 有过审中文名 —— 要么补名字过审，要么从名单里去掉）")
        problems += 1
    if not problems:
        print(f"✅ 时区名单：{len(table_ids)} 条与附 A 的过审时区逐条一致")
    return problems


def dump_json(path: Path, payload: dict[str, str]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve()
    app_dir = here.parents[1]  # tools -> app
    i18n_dir = app_dir / "renderer" / "i18n"

    parser = argparse.ArgumentParser(description="tech/09 ↔ renderer/i18n/*.json 生成与守卫")
    parser.add_argument("--deck", type=Path, default=None, help=f"文案表（默认往上找 {DEFAULT_DECK}）")
    parser.add_argument("--i18n-dir", type=Path, default=i18n_dir)
    parser.add_argument("--write", action="store_true", help="从表生成两份 JSON")
    parser.add_argument("--check", action="store_true", help="比对（默认动作）")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    deck_path = args.deck or find_up(here.parent, DEFAULT_DECK)
    try:
        deck_text = deck_path.read_text(encoding="utf-8")
        copy_entries = parse_deck(deck_text)
        zone_entries = parse_zone_names(deck_text)
        entries = parse_all(deck_text)
    except (OSError, ValueError) as exc:
        print(f"❌ 读表失败：{exc}")
        return 2
    if not copy_entries or not zone_entries:
        print("❌ 表里没解析出完整的文案（§三）或时区名（附 A）")
        return 2
    print(
        f"表：§三 {len(copy_entries)} 条界面文案 + 附 A {len(zone_entries)} 条时区名 = {len(entries)} 个键",
        file=sys.stderr,
    )

    languages = ("zh_CN", "en_US")
    if args.write:
        args.i18n_dir.mkdir(parents=True, exist_ok=True)
        for lang in languages:
            payload = {key: value[lang] for key, value in entries.items()}
            dump_json(args.i18n_dir / f"{lang}.json", payload)
            if not args.quiet:
                print(f"✅ 写入 {args.i18n_dir / f'{lang}.json'}（{len(payload)} 条）")
        return 0

    problems = 0
    for lang in languages:
        path = args.i18n_dir / f"{lang}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"❌ 读不到 / 解析不了 {path}：{exc}")
            problems += 1
            continue
        expected = {key: value[lang] for key, value in entries.items()}
        missing = sorted(set(expected) - set(payload))
        extra = sorted(set(payload) - set(expected))
        diff = sorted(k for k in set(expected) & set(payload) if expected[k] != payload[k])
        if missing:
            print(f"❌ {lang}: JSON 缺 {len(missing)} 条：{missing[:6]}")
            problems += 1
        if extra:
            print(f"❌ {lang}: JSON 多出 {len(extra)} 条（表里没有）：{extra[:6]}")
            problems += 1
        for key in diff[:6]:
            print(f"❌ {lang}: {key}\n    表：{expected[key]!r}\n    JSON：{payload[key]!r}")
        if diff:
            print(f"   （共 {len(diff)} 条不一致）")
            problems += 1
        if not (missing or extra or diff) and not args.quiet:
            print(f"✅ {lang}: {len(payload)} 条与 tech/09 逐字一致")

    # 名单那一半也要过一遍 —— 名字与名单同源于附 A，任何一侧漂了都得红。
    problems += check_zone_table(zone_entries)

    if problems:
        print(f"\n结论：{problems} 处不一致 —— 改表后跑 `--write`，或把 JSON 改回表里的字。")
        return 1
    if not args.quiet:
        print(f"\n结论：{len(entries)} 条 × {len(languages)} 语言全部一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
