"""界面能问系统的事：只读探测 + 少数几个明确动作。

这一层是「前端只订阅事件、不实现逻辑」的落点 —— 界面**不**解析 `nmcli` 的输出、
**不**读 sysfs、**不**拼 `parted` 命令，它只调这里的槽，拿回
[records.py](records.py) 那个形状的记录。

两类返回值：

* 探测类的槽返回**能直接塞进 QML 的记录**（`QVariantList` / `QVariantMap`）；
* 校验类的槽返回**错误文案**（空串 = 通过）—— 界面要把它显示在输入框下面，
  而不是自己再写一份正则（那正是 frontend/README 说的「唯一来源」翻版）。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Slot

from mipl_installer import configure, disk, network, options, util
from mipl_installer.events import NullReporter
from mipl_installer.util import InstallerError, Runner

from . import records
from .actions import SystemActions


class Backend(QObject):
    """注册成 QML 的 `Backend`（见 `mipl-installer`）。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        #: 探测用的 Runner：旁白丢给 NullReporter —— 探测不该混进安装日志。
        self._runner = Runner(NullReporter())
        #: 重启这类「动手」的动作仍然归 actions.py（它有自己的说明）。
        self._actions = SystemActions(self)

    # ── 磁盘 ──────────────────────────────────────────────────────────
    @Slot(result="QVariantList")
    def candidates(self) -> list:
        """候选盘（按 `DiskPage.qml` 的契约）。**读不到就返回空表**，
        界面该显示的是「看不到任何可用的整块盘」，不是一句假数据。"""
        try:
            return records.disk_records(self._candidates())
        except InstallerError:
            return []

    @Slot(str, result="QVariantMap")
    def partitionPlan(self, device: str) -> dict:
        """这块盘将要被分成什么样（分区页与安装详情页共用）。

        用的是 `disk.plan_layout` —— 与真正动手时**同一个函数**，所以界面上
        预告的容量与装出来的布局不会有两份答案。
        """
        if not device:
            return {}
        try:
            layout = disk.plan_layout(util.size_of_device(device))
        except (InstallerError, OSError):
            return {}
        return {
            "device": device,
            "partitions": records.planned_partitions(layout),
            "summary": records.layout_summary(layout),
            "total": util.human_size(layout.total),
        }

    # ── 就绪检查（加载页据此放行）───────────────────────────────────────
    @Slot(result="QVariantList")
    def readiness(self) -> list:
        try:
            usable = len([c for c in self._candidates() if c.usable])
        except InstallerError:
            usable = 0
        return records.readiness(
            {
                "network": self._network_state(),
                "usable_disks": usable,
                "efi": records.efi_booted(),
            }
        )

    # ── 网络 ──────────────────────────────────────────────────────────
    @Slot(result="QVariantMap")
    def network(self) -> dict:
        return records.network_record(self._network_state())

    @Slot(bool, result="QVariantList")
    def wifiNetworks(self, rescan: bool = False) -> list:
        """周围的无线网络。`rescan=True` 让 NetworkManager 重新扫一遍（慢几秒）。"""
        try:
            return records.wifi_records(network.wifi_networks(self._runner, rescan=rescan))
        except InstallerError:
            return []

    @Slot(str, str, result="QVariantMap")
    def connectWifi(self, ssid: str, password: str) -> dict:
        """连一个无线网络。密码走 stdin，**不进 argv**（见 `network.py`）。"""
        try:
            network.connect(self._runner, ssid, password)
        except InstallerError as exc:
            return {"ok": False, "message": str(exc), "hint": exc.hint or ""}
        return {"ok": True, "message": "", "hint": ""}

    # ── 高级安装的四份名单 ─────────────────────────────────────────────
    @Slot(result="QVariantList")
    def keymaps(self) -> list:
        return records.keymap_records(options.keymaps())

    @Slot(result="QVariantList")
    def locales(self) -> list:
        return records.locale_records(options.locales())

    @Slot(result="QVariantList")
    def timezones(self) -> list:
        return records.zone_records(options.timezones())

    # ── 校验：返回错误文案，空串 = 通过 ─────────────────────────────────
    @Slot(str, result=str)
    def validateUser(self, user: str) -> str:
        return self._check(lambda: configure.validate_user(user))

    @Slot(str, result=str)
    def validateHostname(self, hostname: str) -> str:
        return self._check(lambda: options.validate_hostname(hostname))

    @Slot(str, result=str)
    def validateTimezone(self, zone: str) -> str:
        return self._check(lambda: options.validate_timezone(zone))

    @Slot(str, result=str)
    def validateKeymap(self, keymap: str) -> str:
        return self._check(lambda: options.validate_keymap(keymap))

    # ── 动作 ──────────────────────────────────────────────────────────
    @Slot()
    def reboot(self) -> None:
        self._actions.reboot()

    # ── 内部 ──────────────────────────────────────────────────────────
    def _candidates(self) -> list[disk.Candidate]:
        return disk.list_candidates(runner=self._runner)

    def _network_state(self) -> dict:
        try:
            return network.state(self._runner)
        except InstallerError:
            # 探测失败就当没通 —— 见 network.state 的说明，绝不假装在线
            return {"online": False}

    @staticmethod
    def _check(probe: Callable[[], None]) -> str:
        try:
            probe()
        except InstallerError as exc:
            return str(exc)
        return ""
