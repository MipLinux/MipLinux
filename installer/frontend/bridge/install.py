"""安装控制器：把阻塞的 `pipeline.run()` 放进工作线程，事件经信号回界面。

界面这一侧只有三件事：`start(request)` / `cancel()` / 订阅信号。

**取消只在阶段之间生效**（见 [pipeline](../../backend/mipl_installer/pipeline.py)
的说明）：正在跑的 `pacstrap` 不会被掐断，请求会被记下来，等这一步收尾再停。
掐断它只会留下一个谁也说不清的半成品 —— 那不是「取消」，是制造现场。

**擦盘确认也是一道真守卫。** 界面上那道「逐字输入设备路径」的结论随 `request`
传进来，`confirm` 钩子会拿它与真正要擦的盘再对一次；对不上就 `EXIT_GUARD` 退出，
一个字节都不动。守卫一个都没少，只是确认从 TTY 挪到了界面上。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from mipl_installer import pipeline, util
from mipl_installer.util import EXIT_GUARD, EXIT_USAGE, InstallerError

from .reporter import QtReporter

#: `request` 里能直接对应 `Plan` 字段的那些（`disk` 单独校验，`steps` 不接受 ——
#: 界面上没有「只跑一半」这种操作）。
PLAN_FIELDS = (
    "target",
    "hostname",
    "user",
    "locale",
    "timezone",
    "keymap",
    "packages_file",
    "pacman_conf",
    "mirrorlist",
    "no_nvram",
    "keep_mounted",
)


class InstallController(QObject):
    """跑一次安装。信号是给界面看的，`Plan` 是给后端看的。"""

    #: 阶段变了：phase, 那句话
    phaseChanged = Signal(str, str)
    #: 一行日志（命令 / 旁白 / 事件正文）
    logged = Signal(str)
    #: 失败：`InstallerError.render()` 的两行 —— message, hint
    failed = Signal(str, str)
    #: 成功收尾
    succeeded = Signal()
    #: 跑起来了 / 停了（界面据此控制按钮，不用自己猜）
    runningChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._confirmed = ""
        self._reporter = QtReporter(self)
        self._reporter.phased.connect(self.phaseChanged)
        self._reporter.logged.connect(self.logged)

    # ── 界面调这两个 ──────────────────────────────────────────────────
    @Slot("QVariantMap", bool)
    def start(self, request: dict, dry_run: bool = False) -> None:
        """开始安装。`dry_run=True` 只打印命令序列（取图与流程烟测用它排练）。"""
        if self.running:
            self.logged.emit("安装已经在跑了 —— 忽略这次请求")
            return
        try:
            plan = self._plan(request)
        except InstallerError as exc:
            self.failed.emit(str(exc), exc.hint or "")
            return

        self._confirmed = str(request.get("confirmedDevice", ""))
        self._cancel.clear()
        password = str(request.get("password", ""))
        root_password = request.get("rootPassword") or None
        self._thread = threading.Thread(
            target=self._run,
            args=(plan, password, root_password, dry_run),
            name="mipl-install",
            daemon=True,
        )
        self.runningChanged.emit(True)
        self._thread.start()

    @Slot()
    def cancel(self) -> None:
        """请求取消。**不掐断正在跑的命令**（见文件头）。"""
        if not self.running:
            return
        self._cancel.set()
        self.logged.emit("已请求取消：等当前这一步做完就停，不会掐断正在跑的命令")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── 内部 ──────────────────────────────────────────────────────────
    def _plan(self, request: dict) -> pipeline.Plan:
        device = str(request.get("disk", "")).strip()
        if not device:
            raise InstallerError("没有选目标盘", EXIT_USAGE, hint="回到磁盘页选一块盘再开始")
        kwargs = {key: request[key] for key in PLAN_FIELDS if request.get(key)}
        return pipeline.Plan(disk=device, **kwargs)

    def _confirm(self, plan: pipeline.Plan, layout, reporter: QtReporter) -> None:
        reporter.note(f"目标盘：{plan.disk}（{util.human_size(layout.total)}）")
        reporter.note(
            f"将建：系统分区 {util.human_size(layout.esp_size)} (vfat) + "
            f"数据分区 {util.human_size(layout.root_size)} (ext4)"
        )
        if self._confirmed != plan.disk:
            raise InstallerError(
                "没有确认擦除这块盘，已放弃",
                EXIT_GUARD,
                hint="擦除页要求原样输入设备路径；对不上就一个字节都不动",
            )

    def _run(self, plan: pipeline.Plan, password: str, root_password: str | None, dry_run: bool) -> None:
        try:
            pipeline.run(
                plan,
                self._reporter,
                password=password,
                root_password=root_password,
                confirm=self._confirm,
                dry_run=dry_run,
                should_cancel=self._cancel.is_set,
            )
        except InstallerError as exc:
            self.failed.emit(str(exc), exc.hint or "")
        except Exception as exc:  # noqa: BLE001 - 兜底：别让工作线程悄悄死掉
            # 工作线程死了而界面还停在「安装中」，是最难查的一种现场 —— 所以兜底
            # 也要把话说出去。
            self.failed.emit(f"未预期的异常：{exc!r}", "这是安装器的缺陷，请连同上面几行日志一起报 issue")
        else:
            self.succeeded.emit()
        finally:
            self.runningChanged.emit(False)
