#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""i18n 生成 / 守卫 —— tech/09 的过审文案表 ↔ 渲染层两份 JSON。

为什么要有它
------------
文案的唯一源是 `docs/work/tech/09-安装器界面文案.md` 第三节那张审核表（105 条 ID）。
渲染层读的是 `renderer/i18n/{zh_CN,en_US}.json`。两者之间**只能有一份真相**：
JSON 由本脚本从表里生成，`--check` 再逐字比对回去 —— 改了表没重生成、或手改了 JSON，都会红。

用法
----
    python3 app/tools/i18n.py --write   # 从表生成两份 JSON
    python3 app/tools/i18n.py --check   # 比对（默认；退出码 0 = 一致）
    python3 app/tools/i18n.py --check --quiet

纪律
----
- **只读第三节**。附 A 时区名表（34 条）走 `renderer/js/tz-names.js` 自己的守卫；附 B / 附 C 是历史记录，不是界面文案。
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
    """第三节的 104 条界面文案 + 附 A 的 34 条时区名 = 完整键空间。"""
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

    if problems:
        print(f"\n结论：{problems} 处不一致 —— 改表后跑 `--write`，或把 JSON 改回表里的字。")
        return 1
    if not args.quiet:
        print(f"\n结论：{len(entries)} 条 × {len(languages)} 语言全部一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
