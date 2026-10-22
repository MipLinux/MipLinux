"""随包的时区表（D17）：生成物本身、与附 A 的关系、与本机 tzdata 的关系。

这里回答三个不同的问题，别混：

1. **生成物是不是最新的** —— `tools/gen-timezones.py --check` 逐字比；
2. **名单与名字是不是同一批** —— 附 A 里的 id ⇄ `data/timezones.txt`，两个方向都比
   （名单的入表条件是「附 A 里有过审中文名」，所以少了是死键、多了是绕过审核）；
3. **表里的区在这台机器上是否真的有** —— 有 tzdata 就查，没有就跳过。
   它红了不代表代码错，代表 **tzdata 变了、该刷表了**（这正是要提前看见的那种红）。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT_ROOT / "installer" / "frontend" / "app" / "tools"
DECK = PROJECT_ROOT / "docs" / "work" / "tech" / "09-安装器界面文案.md"
TABLE = PROJECT_ROOT / "installer" / "backend" / "mipl_installer" / "data" / "timezones.txt"
ZONEINFO = Path("/usr/share/zoneinfo")


def run_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "gen-timezones.py"), *args],
        capture_output=True,
        text=True,
    )


def table_ids() -> list[str]:
    lines = TABLE.read_text(encoding="utf-8").splitlines()
    return [name for line in lines if (name := line.split("#", 1)[0].strip())]


def approved_ids() -> list[str]:
    sys.path.insert(0, str(TOOLS))
    from i18n import parse_zone_names  # noqa: PLC0415 —— 路径要先接上

    entries = parse_zone_names(DECK.read_text(encoding="utf-8"))
    return [key[len("timezone.name."):] for key in entries]


class TestZoneTableArtifact(unittest.TestCase):
    def test_table_is_in_sync_with_the_deck(self):
        result = run_tool("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_deck_and_table_are_the_same_set(self):
        approved = approved_ids()
        shipped = table_ids()
        self.assertTrue(approved, "附 A 里没解析出时区")
        self.assertEqual([zone for zone in approved if zone not in shipped], [],
                         "附 A 已过审、表里却没有 —— 名字成了死键；跑 gen-timezones.py --write")
        self.assertEqual([zone for zone in shipped if zone not in approved], [],
                         "表里有附 A 没名字的区 —— D17 的入表条件被绕过")
        self.assertEqual(approved, shipped, "同集不同序：顺序也是口径（附 A 的顺序）")

    def test_shipped_zones_exist_in_the_local_tzdata(self):
        if not ZONEINFO.is_dir():
            self.skipTest(f"本机没有 {ZONEINFO}（没装 tzdata），无从对账")
        absent = [zone for zone in table_ids() if not (ZONEINFO / zone).is_file()]
        self.assertEqual(
            absent, [],
            f"表里的这些区在本机 tzdata 上不存在：{absent}\n"
            f"tzdata 变了 → 刷新 tech/09 附 A 并跑 gen-timezones.py --write（别只改表）",
        )


if __name__ == "__main__":
    unittest.main()
