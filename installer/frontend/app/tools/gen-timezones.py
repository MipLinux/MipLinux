#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时区表生成 / 守卫 —— tech/09 附 A 的 34 条过审时区名 ↔ 随包走的 `data/timezones.txt`。

为什么要有它
------------
D17 把界面上的时区名单从「运行系统的 `zone1970.tab`」换成**项目自维护的精选子集**。
子集的入表条件只有一条：**在 tech/09 附 A 里有已过审的中文名**。于是名单的真相
还是那张审核表 —— 本脚本把它落成后端随包读的一行一个 IANA id 的表，
`--check` 再比回去：改了附 A 没重生成、或手改了表，都会红。

两件不同的事，别混：
- **附 A / i18n 的守卫**（`i18n.py --check`）管「名字写了什么」；
- **本脚本**管「名单里有谁」——同一个来源，两个方向。

用法
----
    python3 app/tools/gen-timezones.py --write   # 由附 A 生成 data/timezones.txt
    python3 app/tools/gen-timezones.py --check   # 比对（默认；退出码 0 = 一致）
    python3 app/tools/gen-timezones.py --check --tzdata-check
        # 额外断言表里每一条在**本机** /usr/share/zoneinfo 上真的有（没装 tzdata 就跳过）

纪律
----
- **不入表、不删表靠脚本自己发明**：表 = 附 A 的 id，顺序也照附 A。
  要加一个时区 → 先在附 A 过审一行中文名，再重生成。**反过来不成立**。
- 只依赖标准库；不需要 root、不需要 Live、不联网。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from i18n import DEFAULT_DECK, find_up, parse_zone_names  # noqa: E402

#: 生成物：后端随包读的那张表（相对仓库根）。
TABLE_REL = "installer/backend/mipl_installer/data/timezones.txt"

#: 表头。写在生成物里，免得有人对着它手改。
HEADER = """\
# MipLinux 时区名单 —— **生成物，不要手改**（D17）
#
# 来源：docs/work/tech/09-安装器界面文案.md 附 A「时区名表」（34 条，中英已过审）。
# 生成：python3 installer/frontend/app/tools/gen-timezones.py --write
# 守卫：python3 installer/frontend/app/tools/gen-timezones.py --check
#
# 一行一个 IANA id；后端 `options.timezones()` 读它，并只列**运行系统上真的存在**的那些。
# 加一个时区 = 先在附 A 过审一行中文名，再重生成；不要在这里手加。
"""


def render(zone_ids: list[str]) -> str:
    return HEADER + "".join(f"{zone}\n" for zone in zone_ids)


def zone_ids_from_deck(deck: Path) -> list[str]:
    """附 A → IANA id 列表（保持表里的顺序）。

    `parse_zone_names` 的键是 `timezone.name.<IANA>`：剥掉前缀就是 id 本身。
    顺带挡住「附 A 里冒出一个带点的键」这种误解析 —— id 里不允许出现点。
    """
    entries = parse_zone_names(deck.read_text(encoding="utf-8"))
    ids = [key[len("timezone.name."):] for key in entries]
    bad = [zone for zone in ids if "." in zone or not zone]
    if bad:
        raise ValueError(f"附 A 解析出的 id 不像 IANA 名：{bad[:5]}")
    if not ids:
        raise ValueError("附 A 里没解析出任何时区 —— 表头或列格式变了？")
    return ids


def check_tzdata(zone_ids: list[str], root: Path) -> list[str]:
    """表里每一条在**本机** zoneinfo 上是否真的有（返回缺的那些）。

    `/usr/share/zoneinfo` 不存在（没装 tzdata 的机器）就返回空 —— 无从判断，
    按本仓库口径这不算通过、也不算失败，调用方打印「跳过」。
    """
    if not root.is_dir():
        return []
    return [zone for zone in zone_ids if not (root / zone).is_file()]


def main() -> int:
    here = Path(__file__).resolve()
    repo = here.parents[4]  # tools -> app -> frontend -> installer -> 仓库根

    parser = argparse.ArgumentParser(description="tech/09 附 A ↔ 后端时区表 生成与守卫")
    parser.add_argument("--deck", type=Path, default=None, help=f"文案表（默认往上找 {DEFAULT_DECK}）")
    parser.add_argument("--table", type=Path, default=repo / TABLE_REL)
    parser.add_argument("--write", action="store_true", help="由附 A 生成时区表")
    parser.add_argument("--check", action="store_true", help="比对（默认动作）")
    parser.add_argument("--tzdata-check", action="store_true",
                        help="额外断言每条在本机 /usr/share/zoneinfo 上存在（没装 tzdata 就跳过）")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    deck_path = args.deck or find_up(here.parent, DEFAULT_DECK)
    try:
        zone_ids = zone_ids_from_deck(deck_path)
    except (OSError, ValueError) as exc:
        print(f"❌ 读表失败：{exc}")
        return 2

    expected = render(zone_ids)
    if args.write:
        args.table.parent.mkdir(parents=True, exist_ok=True)
        args.table.write_text(expected, encoding="utf-8")
        if not args.quiet:
            print(f"✅ 写入 {args.table}（{len(zone_ids)} 条）")
        return 0

    problems = 0
    try:
        actual = args.table.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"❌ 读不到时区表 {args.table}：{exc}")
        return 2

    if actual != expected:
        problems += 1
        print(f"❌ {args.table} 与附 A 不一致 —— 跑 --write 重新生成，别手改生成物")
        got = [line.split("#", 1)[0].strip() for line in actual.splitlines()]
        got = [line for line in got if line]
        missing = [zone for zone in zone_ids if zone not in got]
        extra = [zone for zone in got if zone not in zone_ids]
        if missing:
            print(f"   表里少了 {len(missing)} 条：{missing[:8]}")
        if extra:
            print(f"   表里多了 {len(extra)} 条（附 A 里没有 = 没过审）：{extra[:8]}")
        if not missing and not extra:
            print("   条数相同但顺序或表头不同 —— 顺序也是口径（附 A 的顺序）")

    if args.tzdata_check:
        root = Path(os.environ.get("MIPL_ZONEINFO", "/usr/share/zoneinfo"))
        if not root.is_dir():
            print(f"（跳过 tzdata 对账：{root} 不存在）", file=sys.stderr)
        else:
            absent = check_tzdata(zone_ids, root)
            if absent:
                problems += 1
                print(f"❌ 这些区在本机 {root} 上没有（tzdata 变了，表该刷新）：{absent}")
            elif not args.quiet:
                print(f"✅ tzdata 对账：{len(zone_ids)} 条在本机 {root} 上都能找到")

    if not problems and not args.quiet:
        print(f"✅ 时区表与附 A 一致（{len(zone_ids)} 条）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
