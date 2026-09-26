"""Live 网络（`nmcli`）：terse 解析、现状、无线列表、连接。

两处是红线，改动前先想清楚：

* `nmcli -t` 的 `\\:` 转义 —— 用 `split(":")` 解析，SSID 叫 `My:Net` 就会被切成
  两段，于是这个网络永远连不上，而现场看起来像「密码不对」。
* **密码不进 argv** —— 进了就会留在进程列表里（与「密码只走 stdin」同一条红线）。
"""

from __future__ import annotations

import unittest

from mipl_installer import network
from mipl_installer.util import EXIT_USAGE, InstallerError
from tests.support import FakeRunner


class _InputRunner(FakeRunner):
    """把 `input=` 也记下来：`FakeRunner` 只记 argv，而密码正是在 argv 之外。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.inputs: list[str | None] = []

    def run(self, argv, **kwargs):
        self.inputs.append(kwargs.get("input"))
        return super().run(argv, **kwargs)


class TestSplitTerse(unittest.TestCase):
    def test_escaped_colon_stays_inside_the_field(self):
        """**回归测试**：SSID 里的冒号被当成字段分隔符，网络就再也连不上。"""
        self.assertEqual(network.split_terse("My\\:Net:48:WPA2"), ["My:Net", "48", "WPA2"])

    def test_trailing_empty_field_is_preserved(self):
        """`a:b:` 是三个字段 —— 丢掉尾巴会让宽度判断把整行扔了（开放网络正长这样）。"""
        self.assertEqual(network.split_terse("a:b:"), ["a", "b", ""])

    def test_plain_line(self):
        self.assertEqual(network.split_terse("wlan0:wifi:connected:MyNet"),
                         ["wlan0", "wifi", "connected", "MyNet"])


class TestState(unittest.TestCase):
    STATUS = "DEVICE,TYPE,STATE,CONNECTION"

    def _runner(self, status: str, *, ipv4: str = "") -> FakeRunner:
        return FakeRunner(outputs={self.STATUS: status, "IP4.ADDRESS": ipv4})

    def test_connected_ethernet_reads_the_ipv4_from_a_second_command(self):
        """`device show` 的输出**带字段名**（`IP4.ADDRESS[1]:…`），不是一行一个值。

        这是拿真 nmcli 的输出核出来的（1.58.1）。曾经 `_ipv4` 按定宽表解析，
        于是每一行都对不上、永远返回空串 —— 有线连着也报不出 IPv4。
        """
        runner = self._runner(
            "enp0s3:ethernet:connected:Wired connection 1\nwlan0:wifi:disconnected:\n",
            ipv4="IP4.ADDRESS[1]:192.168.1.5/24\n",
        )
        result = network.state(runner)
        self.assertTrue(result["online"])
        self.assertTrue(result["wired"])
        self.assertEqual(result["wired_interface"], "enp0s3")
        self.assertEqual(result["wired_ipv4"], "192.168.1.5/24")
        self.assertTrue(any("IP4.ADDRESS" in c for c in runner.commands()))

    def test_externally_managed_link_still_counts_as_online(self):
        """`connected (externally)` 也是连着 —— 判据取前缀。

        漏掉它，界面就会在链路明明通的时候说「未连接」，而网络页没连**不让往下走**
        （`submit()` 去连网而不是继续）—— 那是个死结。代价是只有 docker0 那种
        机器也会报在线；假阳性只是晚一步失败，假阴性是把人卡住。
        """
        result = network.state(self._runner("br0:bridge:connected (externally):br0\n"))
        self.assertTrue(result["online"])

    def test_loopback_never_counts_as_online(self):
        """`lo` 永远连着，与「有没有网」无关。"""
        self.assertFalse(network.state(self._runner("lo:loopback:connected (externally):lo\n"))["online"])

    def test_connected_wifi_takes_the_ssid_from_the_connection_field(self):
        result = network.state(self._runner("wlan0:wifi:connected:MyNet\n"))
        self.assertTrue(result["online"])
        self.assertFalse(result["wired"])
        self.assertEqual(result["wifi_interface"], "wlan0")
        self.assertEqual(result["wifi_ssid"], "MyNet")

    def test_nothing_connected_invents_no_fields(self):
        """读不到就当没通 —— 界面上写着「已连接」而实际没网，用户会一路点到 pacstrap 失败。"""
        result = network.state(self._runner("lo:loopback:unmanaged:\nwlan0:wifi:disconnected:\n"))
        self.assertFalse(result["online"])
        self.assertFalse(result["wired"])
        self.assertEqual(result["wired_interface"], "")
        self.assertEqual(result["wired_ipv4"], "")
        self.assertEqual(result["wifi_ssid"], "")

    def test_runner_with_no_output_is_offline(self):
        self.assertFalse(network.state(FakeRunner(outputs={}))["online"])


class TestWifiNetworks(unittest.TestCase):
    KEY = "SSID,SIGNAL,SECURITY"

    #: Alpha 出现两次（同一 SSID 的多个 AP）；空 SSID 是隐藏网络
    LIST = "\n".join([
        "Alpha:30:WPA2",
        "Beta:80:WPA1",
        "Alpha:70:WPA2",
        ":99:--",
        "Gamma:50:--",
        "Delta:20:",
    ])

    def _networks(self, **kwargs) -> list[dict]:
        return network.wifi_networks(FakeRunner(outputs={self.KEY: self.LIST}), **kwargs)

    def test_sorted_by_signal_descending_and_deduplicated(self):
        found = self._networks()
        self.assertEqual([n["ssid"] for n in found], ["Beta", "Alpha", "Gamma", "Delta"])
        self.assertEqual([n["signal"] for n in found], [80, 70, 50, 20])
        self.assertTrue(all(isinstance(n["signal"], int) for n in found))

    def test_secured_is_false_for_open_networks(self):
        by_ssid = {n["ssid"]: n["secured"] for n in self._networks()}
        self.assertTrue(by_ssid["Beta"])
        self.assertTrue(by_ssid["Alpha"])
        self.assertFalse(by_ssid["Gamma"])          # SECURITY 是 "--"
        self.assertFalse(by_ssid["Delta"])          # SECURITY 是空

    def test_rescan_flag(self):
        cached = FakeRunner(outputs={self.KEY: self.LIST})
        network.wifi_networks(cached, rescan=False)
        self.assertTrue(any("--rescan no" in c for c in cached.commands()))

        fresh = FakeRunner(outputs={self.KEY: self.LIST})
        network.wifi_networks(fresh, rescan=True)
        self.assertFalse(any("--rescan" in c for c in fresh.commands()))


class TestConnect(unittest.TestCase):
    def test_password_goes_to_stdin_never_to_argv(self):
        """安全红线：密码进 argv 就会留在进程列表里。"""
        runner = _InputRunner()
        network.connect(runner, "My:Net", "s3cret")
        commands = runner.commands()
        self.assertIn("My:Net", commands[0])                 # SSID 必须在 argv 里
        self.assertIn("--ask", commands[0])
        self.assertTrue(all("s3cret" not in c for c in commands))
        self.assertEqual(runner.inputs, ["s3cret\n"])

    def test_open_network_sends_an_empty_line(self):
        runner = _InputRunner()
        network.connect(runner, "Open", "")
        self.assertEqual(runner.inputs, ["\n"])

    def test_no_ssid_is_a_usage_error(self):
        with self.assertRaises(InstallerError) as ctx:
            network.connect(_InputRunner(), "")
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
