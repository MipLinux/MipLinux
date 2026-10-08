"""QEMU / Live 那一轮的设备形状，用假 sysfs 钉住。

**为什么值得单独一个文件：** 验收是「QEMU 里全程图形化装完一次」，而那一轮要 root、
要重建 ISO。真跑之前，至少要把**这一轮会看到哪几块盘**先算出来 —— 否则现场看到的
每一项都要现判断「这对不对」，而判断不了的东西等于没测。

QEMU 那一轮的设备是个很具体的形状（`scripts/mipl.sh` 的 qemu 参数决定）：

    -drive "file=…,if=virtio"   →  /dev/vda   （virtio-blk，**sysfs 里没有 model**）
    ISO 挂在光驱上               →  /dev/sr0   （有 device 链接，但要被前缀规则滤掉）
    Live 自带 zram               →  /dev/zram0 （没有 device 链接）

目标盘是 `mipl target` 刚建出来的**空盘**，所以磁盘页应当显示「整块未使用」、
比例条整条是未分配、并且它是唯一可选的那一块。这些都在下面断言。

> **界面那一半的断言搬到哪去了（Issue #97）。** 「这块盘在界面上显示成什么样」
> ——`sizeLabel`、「（型号未报告）」、推荐标记、只列能装的盘—— 现在归
> `installer/frontend/app/renderer/js/backend.js`（真跑时是它把后端事实翻成界面形状）。
> 那个文件的断言在 `installer/frontend/app/tests/backend.test.mjs`。
> 这里只留**后端这一侧**：这一轮会枚举出哪几块盘、各自是什么事实。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mipl_installer import disk

GiB = 1024 ** 3


def build_sysfs(root: str, *, disk_partitions: list[tuple[str, str, str]] | None = None) -> None:
    """搭一棵 QEMU Live 形状的假 sysfs。

    `disk_partitions` 为 None 表示**空盘**（`mipl target` 刚建出来的那种）。
    """
    block = Path(root) / "block"

    # /dev/vda：virtio-blk。有 device 链接，**没有 model 文件**；
    # `vendor` 是红的 PCI 厂商号 `0x1af4`（真 ISO 里实测到的就是它）
    vda = block / "vda"
    (vda / "device").mkdir(parents=True)
    (vda / "device" / "vendor").write_text("0x1af4\n", encoding="utf-8")
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
    """`linux` 那一轮的设备形状 → 后端会报出哪几块盘。"""

    def test_sees_only_the_virtio_target_disk(self):
        """候选表里**只有** /dev/vda：光驱与 zram 都不该出现。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            found = candidates(tmp)
        self.assertEqual([c.path for c in found], ["/dev/vda"])

    def test_empty_target_disk_is_usable(self):
        """空盘（`mipl target` 刚建的）必须是能装的那一块 —— 不然这一轮根本开不了工。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            candidate = candidates(tmp)[0]
        self.assertTrue(candidate.usable)
        self.assertFalse(candidate.in_use)
        self.assertFalse(candidate.too_small)
        self.assertEqual(candidate.partitions, ())
        self.assertEqual(candidate.size, 40 * GiB)

    def test_virtio_blk_has_no_model_and_we_do_not_invent_one(self):
        """virtio-blk 的 sysfs 里没有 model，`vendor` 是 PCI 厂商号 `0x1af4`。

        **这条是实测补上的**：真 ISO 里那一行曾经显示成 `0x1af4`（PCI 厂商号被
        当成型号读出来了）—— 用户看到它学不到任何东西，比空着更糟。
        界面把空型号显示成「（型号未报告）」，那是**界面**的措辞（见 Node 侧断言）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            build_sysfs(tmp)
            self.assertEqual(candidates(tmp)[0].model, "")

    def test_second_install_run_shows_the_previous_layout(self):
        """第二次装（盘上已有分区）时，分区事实要来自**真 sysfs**，不是猜的。"""
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
            candidate = candidates(tmp)[0]
        self.assertEqual([part.number for part in candidate.partitions], [1, 2])
        self.assertEqual(candidate.partitions[0].size, esp_size * 512)
        self.assertEqual(
            sum(part.size for part in candidate.partitions),
            (esp_size + data_size) * 512,
        )
        # 已有分区的盘仍然能装（重装到同一块盘是正常流程），只是不再被标成「推荐」
        self.assertTrue(candidate.usable)


if __name__ == "__main__":
    unittest.main()
