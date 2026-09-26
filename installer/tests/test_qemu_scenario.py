"""QEMU / Live 那一轮的预期画面，用假 sysfs 钉住。

**为什么值得单独一个文件：** M2 的验收是「QEMU 里全程图形化装完一次」，而那一轮要
root、要重建 ISO。真跑之前，至少要把**界面该显示什么**先算出来 —— 否则现场看到的
每一个字都要现判断「这对不对」，而判断不了的东西等于没测。

QEMU 那一轮的设备是个很具体的形状（`scripts/mipl.sh` 的 qemu 参数决定）：

    -drive "file=…,if=virtio"   →  /dev/vda   （virtio-blk，**sysfs 里没有 model**）
    ISO 挂在光驱上               →  /dev/sr0   （有 device 链接，但要被前缀规则滤掉）
    Live 自带 zram               →  /dev/zram0 （没有 device 链接）

目标盘是 `mipl target` 刚建出来的**空盘**，所以磁盘页应当显示「整块未使用」、
比例条整条是未分配、并且因为只有一块可用盘而**自动选中**。这些都在下面断言。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from mipl_installer import disk

#: 测试要直接调 `bridge/records.py`（纯函数、不依赖 Qt），而 `tests/__init__.py`
#: 只把 backend 接上 sys.path —— 所以这里补 frontend，路径知识不留第二份。
_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from bridge import records  # noqa: E402  （必须在 sys.path 补好之后）

GiB = 1024 ** 3


def build_sysfs(root: str, *, disk_partitions: list[tuple[str, str, str]] | None = None) -> None:
    """搭一棵 QEMU Live 形状的假 sysfs。

    `disk_partitions` 为 None 表示**空盘**（`mipl target` 刚建出来的那种）。
    """
    block = Path(root) / "block"

    # /dev/vda：virtio-blk。有 device 链接，**没有 model 文件**（这是它的真实形状）
    vda = block / "vda"
    (vda / "device").mkdir(parents=True)
    (vda / "size").write_text(str(40 * GiB // 512) + "\n", encoding="utf-8")
    (vda / "removable").write_text("0\n", encoding="utf-8")
    for name, start, size in disk_partitions or []:
        part = vda / name
        part.mkdir()
        (part / "partition").write_text(name[-1] + "\n", encoding="utf-8")
        (part / "start").write_text(start + "\n", encoding="utf-8")
        (part / "size").write_text(size + "\n", encoding="utf-8")

    # /dev/sr0：光驱。**有 device 链接**，所以它只能靠名字前缀规则被滤掉 ——
    # 这正是「两道判据缺一不可」要证的那件事
    sr0 = block / "sr0"
    (sr0 / "device").mkdir(parents=True)
    (sr0 / "size").write_text("1000000\n", encoding="utf-8")
    (sr0 / "removable").write_text("1\n", encoding="utf-8")

    # /dev/zram0：Live 自带。没有 device 链接，第一道判据就把它滤掉了
    zram = block / "zram0"
    zram.mkdir()
    (zram / "size").write_text("1000000\n", encoding="utf-8")


def candidates(root: str) -> list[disk.Candidate]:
    # sources 给空集：Live 里没有任何东西从 /dev/vda 上挂载（ISO 在 sr0 上）
    return disk.list_candidates(sysfs_root=root, disk_root="/dev", sources=set(), runner=None)


class TestQemuLiveShape(unittest.TestCase):
    """`linux` 那一轮的设备形状 → 界面该显示什么。"""

    def test_sees_only_the_virtio_target_disk(self):
        """候选表里**只有** /dev/vda：光驱与 zram 都不该出现。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            found = candidates(tmp)
        self.assertEqual([c.path for c in found], ["/dev/vda"])

    def test_empty_target_disk_looks_like_a_blank_disk(self):
        """空盘（`mipl target` 刚建的）在磁盘页上应当就是「整块未使用」。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            record = records.disk_record(candidates(tmp)[0])
        self.assertEqual(record["summary"], "整块未使用")
        self.assertEqual(record["segments"], [{"kind": "free", "share": 1.0}])
        self.assertEqual(record["size"], "40.0 GiB")
        self.assertTrue(record["selectable"], "空盘必须可选 —— 不然 M2 那一轮根本开不了工")
        self.assertEqual(record["badges"], [], "空盘没有任何要提醒的状态")

    def test_virtio_blk_has_no_model_and_we_do_not_invent_one(self):
        """virtio-blk 的 sysfs 里没有 model —— 界面显示「（型号未报告）」。

        **这是有意的**，不是漏了：界面上每个字都要能指出出处（`DiskPage.qml` 文件头）。
        真机上（NVMe / SATA / USB）型号都在，只有 QEMU 这种虚拟盘没有。
        """
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            candidate = candidates(tmp)[0]
            self.assertEqual(candidate.model, "")
            self.assertEqual(records.disk_record(candidate)["model"], "（型号未报告）")

    def test_only_one_usable_disk_so_the_page_auto_selects(self):
        """恰好一块可用盘 → 磁盘页自动选中（`DiskPage.qml` 的 `autoSelected`）。

        这一条是「默认路径只留一个真决策」在 QEMU 那一轮的实际形态。
        """
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            usable = [c for c in candidates(tmp) if c.usable]
        self.assertEqual(len(usable), 1)

    def test_second_install_run_shows_the_previous_layout(self):
        """第二次装（盘上已有分区）时，比例条与摘要要来自**真分区**，不是猜的。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 1 MiB 对齐的 ESP 512 MiB + 剩下的数据分区，盘尾留 1 MiB
            total_sectors = 40 * GiB // 512
            esp_start, esp_size = 2048, 1048576
            data_start = esp_start + esp_size
            data_size = total_sectors - data_start - 2048
            build_sysfs(tmp, disk_partitions=[
                ("vda1", str(esp_start), str(esp_size)),
                ("vda2", str(data_start), str(data_size)),
            ])
            record = records.disk_record(candidates(tmp)[0])
        self.assertEqual([s["kind"] for s in record["segments"]], ["os", "os"])
        self.assertIn("512.0 MiB", record["summary"])
        self.assertIn("39.5 GiB", record["summary"])
        # 1 MiB 的对齐零头不值得出现在摘要里（FREESPACE_NOISE 那条阈值）
        self.assertNotIn("未分配", record["summary"])


if __name__ == "__main__":
    unittest.main()
