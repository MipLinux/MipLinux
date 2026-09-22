"""pyparted 的调用名对不上的守卫（静态检查，不需要装 pyparted）。

**为什么要有这个测试：** pyparted 的公开 API 是 camelCase（`getDevice`、`freshDisk`、
`commit`），而 `_ped` 那层是 snake_case；凭记忆写就会写成 `get_device` ——
本仓库真的这么错过一次（Live 排练里 `module 'parted' has no attribute 'get_device'`），
而每验证一次要跑一轮 QEMU + Live 内安装，代价很高。

所以：**本文件里的名单是照 pyparted 上游源码与 archinstall 的用法核对过的**。
新增调用时先去看上游，再往名单里加 —— 名单是让「没核对过」变成红灯，不是形式主义。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "backend" / "mipl_installer" / "disk.py"

#: 我们依赖的 pyparted 名字（全部照上游源码核对过）。
#: 依据：pyparted master 的 `src/parted/{__init__,device,disk,partition,filesystem,geometry,constraint}.py`，
#: 以及 archinstall 的 `lib/disk/device_handler.py`（同一个库的真实用法）。
KNOWN_API = {
    "getDevice",        # parted/__init__.py：Device(path=…)
    "freshDisk",        # parted/__init__.py：freshDisk(device, "gpt")
    "Geometry",         # Geometry(device=…, start=…, length=…)
    "FileSystem",       # FileSystem(type=…, geometry=…)
    "Partition",        # Partition(disk=…, type=…, fs=…, geometry=…)
    "PARTITION_NORMAL",  # _ped 常量，条件导入但一直存在
    "PARTITION_ESP",    # _ped 常量，**条件**导入（见 disk._esp_flag）
}

DIRECT = re.compile(r"\bparted\.([A-Za-z_][A-Za-z0-9_]*)")
VIA_GETATTR = re.compile(r"getattr\(\s*parted\w*\s*,\s*\"([A-Za-z_][A-Za-z0-9_]*)\"")


class TestPartedApiNames(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding="utf-8")
        self.used = set(DIRECT.findall(self.source)) | set(VIA_GETATTR.findall(self.source))

    def test_every_name_is_verified(self):
        unknown = sorted(self.used - KNOWN_API)
        self.assertEqual(
            unknown, [],
            "这几个 pyparted 名字没在名单里（先核对上游 API 再加进来）：" + "、".join(unknown),
        )

    def test_no_snake_case_lookalikes(self):
        """pyparted 的公开 API 是 camelCase —— 出现 `get_device` 这种名字基本就是照 _ped 写的。"""
        suspicious = sorted(
            name for name in self.used
            if "_" in name and not name.startswith("PARTITION_")
        )
        self.assertEqual(suspicious, [], "这些看起来是 snake_case：" + "、".join(suspicious))

    def test_the_test_actually_sees_the_calls(self):
        # 守住测试本身：源文件改了名字/被移动时，上面两条会变成「空集合通过」
        for expected in ("getDevice", "freshDisk", "PARTITION_ESP"):
            self.assertIn(expected, self.used, f"没在源码里找到 {expected} —— 这个测试是不是失效了？")


if __name__ == "__main__":
    unittest.main()
