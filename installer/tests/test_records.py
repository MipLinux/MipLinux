"""后端事实 → 界面记录（`bridge/records.py`）的纯函数。

这一层只**翻译**与**取舍**，不推断：界面上每个字都必须能指出出处。所以这里钉的
是字段名（`DiskPage.qml` / `NetworkPage.qml` 那边的契约）、胶囊顺序与噪声阈值。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# records.py 在 frontend 下，而 tests/__init__.py 只把 backend 接进了 sys.path ——
# 这里自己补 frontend：bridge 是纯 Python，不需要 Qt，所以能直接单测。
_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from bridge import records                                     # noqa: E402
from mipl_installer import disk, util                          # noqa: E402

GiB = disk.GiB
MiB = disk.MiB


def _candidate(size: int = 40 * GiB, *, partitions=(), in_use: bool = False,
               removable: bool = False, table_type: str | None = None,
               model: str = "") -> disk.Candidate:
    return disk.Candidate(path="/dev/vda", model=model, size=size, removable=removable,
                          in_use=in_use, table_type=table_type, partitions=tuple(partitions))


def _partition(number: int = 1, start: int = 0, size: int = 5 * GiB, *,
               fs_type: str | None = None, label: str | None = None,
               esp: bool = False) -> disk.Partition:
    return disk.Partition(device=f"/dev/vda{number}", number=number, start=start, size=size,
                          fs_type=fs_type, label=label, esp=esp)


class TestDiskRecord(unittest.TestCase):
    def test_empty_large_unused_disk(self):
        record = records.disk_record(_candidate())
        self.assertTrue(record["selectable"])
        self.assertEqual(record["badges"], [])
        self.assertEqual(record["summary"], "整块未使用")
        self.assertEqual(record["segments"], [{"kind": "free", "share": 1.0}])
        self.assertEqual(record["size"], util.human_size(40 * GiB))
        self.assertIsInstance(record["size"], str)


class TestBadges(unittest.TestCase):
    def test_priority_follows_danger(self):
        """顺序就是危险程度：不能选的原因排在最前 —— 胶囊的排法就是结论的排法。"""
        candidate = _candidate(2 * GiB, in_use=True, removable=True, table_type="gpt")
        self.assertEqual([(b["t"], b["v"]) for b in records.badges_of(candidate)],
                         [("正在使用", "danger"), ("太小", "danger"),
                          ("可移动设备", "warning"), ("已有分区表", "warning")])

    def test_in_use_large_disk_gets_only_the_first(self):
        candidate = _candidate(40 * GiB, in_use=True)
        self.assertEqual([(b["t"], b["v"]) for b in records.badges_of(candidate)],
                         [("正在使用", "danger")])


class TestSelectable(unittest.TestCase):
    def test_in_use_is_not_selectable(self):
        self.assertFalse(records.disk_record(_candidate(in_use=True))["selectable"])

    def test_too_small_is_not_selectable(self):
        self.assertFalse(records.disk_record(_candidate(2 * GiB))["selectable"])

    def test_large_free_disk_is_selectable(self):
        self.assertTrue(records.disk_record(_candidate())["selectable"])


class TestSegments(unittest.TestCase):
    def test_one_partition_in_the_middle(self):
        candidate = _candidate(partitions=(_partition(start=10 * GiB, size=5 * GiB),))
        segments = records.segments_of(candidate)
        self.assertEqual([s["kind"] for s in segments], ["free", "os", "free"])
        self.assertAlmostEqual(sum(s["share"] for s in segments), 1.0, places=6)

    def test_esp_partition_is_efi(self):
        candidate = _candidate(partitions=(_partition(start=MiB, size=512 * MiB, esp=True),))
        self.assertIn("efi", [s["kind"] for s in records.segments_of(candidate)])


class TestNoiseThreshold(unittest.TestCase):
    """摘要与条图对「1 MiB 对齐零头」必须用**同一个**判断 —— 两处不一致就会
    文字里不提、条上却留一根看不见的细丝。"""

    def test_alignment_sliver_is_dropped_from_both(self):
        total = 40 * GiB
        candidate = _candidate(total, partitions=(_partition(start=MiB, size=total - 2 * MiB),))
        summary = records.summary_of(candidate)
        segments = records.segments_of(candidate)
        self.assertNotIn("未分配", summary)
        self.assertEqual([s["kind"] for s in segments], ["os"])

    def test_a_real_unallocated_area_is_mentioned(self):
        candidate = _candidate(partitions=(_partition(start=MiB, size=10 * GiB),))
        self.assertIn("未分配", records.summary_of(candidate))
        self.assertIn("free", [s["kind"] for s in records.segments_of(candidate)])


class TestPartitionLabel(unittest.TestCase):
    def test_esp_wins(self):
        self.assertEqual(records.partition_label(_partition(esp=True, fs_type="vfat")), "EFI")

    def test_falls_back_to_the_filesystem_type(self):
        self.assertEqual(records.partition_label(_partition(fs_type="ntfs")), "NTFS")

    def test_falls_back_to_the_partition_number(self):
        self.assertEqual(records.partition_label(_partition(number=3)), "分区 3")


class TestReadiness(unittest.TestCase):
    OK_ITEMS = {"network": {"online": True, "wired": True, "wifi_ssid": ""},
                "usable_disks": 1, "efi": True}

    def test_shape_and_labels(self):
        rows = records.readiness(self.OK_ITEMS)
        self.assertEqual([row["label"] for row in rows], ["网络", "目标盘", "EFI 固件"])
        for row in rows:
            with self.subTest(label=row["label"]):
                self.assertTrue({"label", "state", "value"} <= set(row))
                self.assertIn(row["state"], {"ok", "fail", "checking"})
                self.assertIsInstance(row["value"], str)

    def test_fix_only_appears_on_failing_rows(self):
        rows = records.readiness(self.OK_ITEMS)
        self.assertTrue(all(row["state"] == "ok" for row in rows))
        for row in rows:
            self.assertNotIn("fix", row)

        mixed = records.readiness({"network": {"online": False, "wired": False},
                                   "usable_disks": 1, "efi": True})
        self.assertEqual(mixed[0]["state"], "fail")
        self.assertIn("fix", mixed[0])
        self.assertNotIn("fix", mixed[1])
        self.assertNotIn("fix", mixed[2])

    def test_all_three_pass_together(self):
        rows = records.readiness(self.OK_ITEMS)
        self.assertEqual([row["state"] for row in rows], ["ok", "ok", "ok"])

    def test_wifi_connection_names_the_ssid(self):
        items = {"network": {"online": True, "wired": False, "wifi_ssid": "MyNet"},
                 "usable_disks": 1, "efi": True}
        self.assertEqual(records.readiness(items)[0]["value"], "已连接（MyNet）")


class TestNetworkRecord(unittest.TestCase):
    def test_wifi_only_leaves_the_wired_fields_empty(self):
        record = records.network_record({"online": True, "wired": False, "wired_interface": "",
                                         "wired_ipv4": "", "wifi_ssid": "MyNet"})
        self.assertEqual(record, {"online": True, "wiredConnected": False, "wiredName": "",
                                  "wiredIPv4": "", "connectedSsid": "MyNet"})
        self.assertEqual(set(record), {"online", "wiredConnected", "wiredName",
                                       "wiredIPv4", "connectedSsid"})

    def test_wired_connection_fills_name_and_ipv4(self):
        record = records.network_record({"online": True, "wired": True, "wired_interface": "enp0s3",
                                         "wired_ipv4": "10.0.0.2/24", "wifi_ssid": ""})
        self.assertTrue(record["wiredConnected"])
        self.assertEqual(record["wiredName"], "enp0s3")
        self.assertEqual(record["wiredIPv4"], "10.0.0.2/24")


class TestWifiRecords(unittest.TestCase):
    def test_passes_fields_through_without_renaming(self):
        """`signal` 是百分比、就是百分比 —— 改名会让界面按 dBm 去读。"""
        networks = [{"ssid": "MyNet", "signal": 80, "secured": True}]
        self.assertEqual(records.wifi_records(networks), networks)
        self.assertIn("signal", records.wifi_records(networks)[0])


class TestPlannedPartitions(unittest.TestCase):
    def test_two_partitions_in_order(self):
        layout = disk.plan_layout(40 * GiB)
        rows = records.planned_partitions(layout)
        self.assertEqual([row["kind"] for row in rows], ["system", "data"])
        self.assertEqual([row["fs"] for row in rows], ["vfat", "ext4"])
        self.assertAlmostEqual(sum(row["share"] for row in rows), 1.0, delta=0.001)


class TestLocaleRecords(unittest.TestCase):
    def test_curated_name_and_fallback(self):
        rows = records.locale_records(["zh_CN.UTF-8", "xx_YY.UTF-8"])
        self.assertEqual(rows[0], {"name": "简体中文", "locale": "zh_CN.UTF-8"})
        # 认不出来就用 locale 自己当名字，绝不编一个假名字
        self.assertEqual(rows[1], {"name": "xx_YY.UTF-8", "locale": "xx_YY.UTF-8"})


if __name__ == "__main__":
    unittest.main()
