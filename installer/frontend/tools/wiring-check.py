#!/usr/bin/env python3
"""接线的端到端烟测：挂上**真实后端**，走一遍并断言每一跳。

与 `flow-check.py` 的分工：

| 脚本 | 挂什么 | 验什么 |
|---|---|---|
| `flow-check.py` | 什么都不挂 | **离线**那条路：路由与状态传递（页面默认值 + 排练假安装） |
| `wiring-check.py` | `Backend` + `Install` | **真身**那条路：界面拿到的是真数据、按下「开始安装」真的驱动后端 |

**不碰盘。** 安装那一段走 `pipeline.run(dry_run=True)`：只打印命令序列，一个
字节都不动。做法是挂一个 `MipRehearsal` 上下文属性让流程壳把排练开关传给控制器
（那个开关只有这里会挂，见 `qml/Main.qml`）—— 所以这个脚本**不需要 root**：

    python3 installer/frontend/tools/wiring-check.py
    python3 installer/frontend/tools/wiring-check.py -v     # 每一步都打印当前页

它要证明的四件事，按重要性排：

1. **候选盘来自后端**：磁盘页上的那一串与 `Backend.candidates()` 逐条一致
   （不是页面里那份默认值）；
2. **事件流真的接上了**：安装页的阶段与日志由后端 `Reporter` 喂出来，
   日志里能看到真命令（`wipefs` / `pacstrap` / `arch-chroot` / `bootctl`）；
3. **擦盘守卫没被绕过**：`confirmedDevice` 对不上时控制器拒绝开跑；
4. **走完整条链**：`start → disk → packages → configure → boot → done`。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent
MAIN_QML = FRONTEND / "qml" / "Main.qml"

#: 日志里必须能看到的真命令 —— 少一条就说明那一段没真跑
EXPECTED_COMMANDS = ("wipefs -a", "mkfs.vfat", "pacstrap", "arch-chroot", "bootctl")

#: 磁盘页记录的契约字段（少一个 `DiskPage.qml` 就画不出来）
DISK_KEYS = {"path", "model", "size", "summary", "segments", "selectable", "badges"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiring-check.py", description="前后端接线的端到端烟测")
    parser.add_argument("--step-ms", type=int, default=150, help="每一跳之间让事件循环转多久")
    parser.add_argument("--install-timeout", type=float, default=60.0,
                        help="等排练安装跑完的上限（秒）")
    parser.add_argument("-v", "--verbose", action="store_true", help="每一步都打印当前页")
    args = parser.parse_args(argv)

    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression

    sys.path.insert(0, str(FRONTEND))
    # 顺序要紧：先把 backend/ 挂上 sys.path，再 import bridge.backend
    # （它 import `mipl_installer`）
    from bridge.paths import BACKEND, ensure_backend_on_path

    ensure_backend_on_path()
    if not BACKEND.is_dir():
        print(f"找不到后端源码：{BACKEND}", file=sys.stderr)
        return 1

    from bridge.backend import Backend
    from bridge.icons import register_icon_provider
    from bridge.install import InstallController

    app = QGuiApplication([sys.argv[0]])
    engine = QQmlApplicationEngine()
    register_icon_provider(engine)

    backend = Backend(app)
    install = InstallController(app)
    engine.rootContext().setContextProperty("Backend", backend)
    engine.rootContext().setContextProperty("Install", install)
    #: 排练开关：只在这里挂（Live 的入口不挂），见 qml/Main.qml
    engine.rootContext().setContextProperty("MipRehearsal", True)

    problems: list[str] = []
    engine.warnings.connect(lambda errs: [problems.append(f"QML: {e.toString()}") for e in errs])
    engine.load(QUrl.fromLocalFile(str(MAIN_QML)))
    roots = engine.rootObjects()
    if not roots:
        print("流程壳没加载起来", file=sys.stderr)
        return 1
    root = roots[0]

    checks = {"ok": 0, "bad": 0}

    def check(ok: bool, what: str) -> None:
        checks["ok" if ok else "bad"] += 1
        print(f"  [{'ok' if ok else '!!'}] {what}")
        if not ok:
            problems.append(what)

    def spin(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def page() -> str:
        return str(root.property("page"))

    def item():
        return root.property("currentPage")

    def value(name: str):
        it = item()
        if it is None:
            return None
        raw = it.property(name)
        return raw.toVariant() if hasattr(raw, "toVariant") else raw

    def call(code: str) -> None:
        expr = QQmlExpression(engine.rootContext(), item(), code)
        expr.evaluate()
        if expr.hasError():
            problems.append(f"{page()} 上求值 {code!r} 出错：{expr.error().toString()}")

    def advance(want: str, what: str, tries: int = 40) -> None:
        """等页面变成 `want`（有些跳转要等后端探测/线程）。"""
        for _ in range(tries):
            if page() == want:
                check(True, f"{what}：{want}")
                return
            spin(args.step_ms)
        check(False, f"{what}：期望 {want}，实际 {page()}")
        raise SystemExit(1)

    print("接线的端到端烟测（排练模式：只打印命令，不碰盘）")

    # ── 1. 加载页：等**真的**就绪探测 ─────────────────────────────────
    check(root.property("hasBackend") is True, "流程壳认出了 Backend")
    check(root.property("hasInstall") is True, "流程壳认出了 Install")
    advance("welcome", "加载页（真探测完）→ 欢迎页")

    ready = root.property("readyItems")
    ready = ready.toVariant() if hasattr(ready, "toVariant") else ready
    check(isinstance(ready, list) and len(ready) == 3,
          f"就绪检查拿到三行：{[r.get('label') for r in ready or []]}")
    print(f"       就绪检查明细：{ready}")

    # ── 2. 网络页：状态来自 nmcli ──────────────────────────────────────
    call("installRequested()")
    advance("network", "欢迎页「开始安装」→ 网络")
    net = value("online")
    check(net is not None, f"网络页拿到了后端状态（online = {net}）")

    call("continueRequested()")
    advance("disk", "网络「继续」→ 系统磁盘")

    # ── 3. 候选盘必须与后端逐条一致（这是「接了真后端」的核心断言）──────
    page_candidates = value("candidates") or []
    api_candidates = backend.candidates()
    check(len(page_candidates) > 0,
          f"磁盘页拿到了候选盘（{len(page_candidates)} 块："
          f"{[c.get('path') for c in page_candidates]}）")
    check([c.get("path") for c in page_candidates] == [c.get("path") for c in api_candidates],
          "磁盘页的候选盘与 Backend.candidates() 逐条一致（不是页面里的默认值）")
    bad_keys = [c.get("path") for c in page_candidates if set(c.keys()) != DISK_KEYS]
    check(not bad_keys, f"每条候选盘的字段都符合 DiskPage 的契约（异常：{bad_keys}）")

    usable = [c for c in page_candidates if c.get("selectable")]
    if not usable:
        print("\n这台机器没有任何可选的整块盘 —— 接线无法继续验证。", file=sys.stderr)
        for c in page_candidates:
            print(f"  · {c.get('path')} 标记 selectable=False", file=sys.stderr)
        return 1
    target = usable[0]["path"]
    print(f"       用第一块可选的盘排练：{target}")

    # ── 4. 分区预告来自后端 `plan_layout` ──────────────────────────────
    call(f"chosen('{target}')")
    advance("partition", "选盘 → 磁盘分区")
    plan = backend.partitionPlan(target)
    parts = value("partitions") or []
    check([p.get("kind") for p in parts] == ["system", "data"],
          f"分区页拿到两条规划中的分区：{[(p.get('name'), p.get('size')) for p in parts]}")
    check(parts == plan.get("partitions"),
          "分区页的两条记录与 Backend.partitionPlan() 一致（同一份 plan_layout）")

    call("continueRequested()")
    advance("erase-confirm", "分区「继续」→ 确认擦除")

    call(f"confirmedRequested('{target}')")
    advance("account", "逐字确认 → 账户")

    call("accountChosen('mipl', 'mipl', 'mipl-2026', false)")
    advance("install-details", "账户 → 安装详情")

    # 事件流**必须在开跑之前订阅** —— 后端不等我们，晚一步就漏掉前几段
    seen_phases: list[str] = []
    seen_logs: list[str] = []
    failures: list[tuple[str, str]] = []
    install.phaseChanged.connect(lambda phase, action: seen_phases.append(phase))
    install.logged.connect(lambda line: seen_logs.append(line))
    install.failed.connect(lambda message, hint: failures.append((message, hint)))

    def wait_for(what, predicate, timeout: float) -> bool:
        waited = 0.0
        while waited < timeout:
            spin(100)
            waited += 0.1
            if predicate():
                return True
        print(f"       （等 {what} 超时：{timeout:.0f} 秒）")
        return False

    # ── 5. 先演一遍**失败**：把时区改成一个不存在的名字 ────────────────
    #
    # 这一跳证三件事：参数守卫在**动盘之前**就拦（日志里不该有 wipefs）、
    # 失败真的显示在安装页上（不是停在「安装中」）、失败页给的是后端原文。
    root.setProperty("timezone", "Asia/Nowhere")
    call("installRequested()")
    advance("install", "详情页「开始安装」→ 安装")
    check(wait_for("失败", lambda: bool(failures), 20),
          f"不存在的时区让安装失败：{failures[0][0] if failures else '没有任何失败信号'}")
    check(bool(failures) and "时区不存在" in failures[0][0],
          "失败原文来自后端（「时区不存在」，不是界面自己编的）")
    check(bool(failures) and failures[0][1] != "", "失败带了「接下来怎么办」那行 hint")
    check(value("failed") is True and "时区不存在" in (value("failureMessage") or ""),
          "失败显示在安装页上（failed / failureMessage 都起来了）")
    check(page() != "done", "失败之后**没有**跳到「装好了」那一页")
    check(not any("wipefs" in line for line in seen_logs),
          "参数不对时一条动盘命令都没跑（守卫在擦盘之前）")

    # ── 6. 改回合法值 → 「重试」→ 跑完 ────────────────────────────────
    root.setProperty("timezone", "Asia/Shanghai")
    seen_phases.clear()
    seen_logs.clear()
    call("retryRequested()")
    print(f"  … 等排练安装跑完（上限 {args.install_timeout:.0f} 秒）")
    check(wait_for("跑完", lambda: page() == "done", args.install_timeout),
          "「重试」之后排练安装跑完 → 结束页")

    #: 阶段序列：去重保序 —— 同一阶段（比如 packages）会连报好几次
    order: list[str] = []
    for phase in seen_phases:
        if not order or order[-1] != phase:
            order.append(phase)
    check(order[:6] == ["start", "disk", "packages", "configure", "boot", "done"],
          f"事件流报了完整的六个阶段（实际：{order}）")
    from mipl_installer.events import PHASES
    check(all(phase in PHASES for phase in seen_phases),
          f"出现的阶段名都在 events.PHASES 里（实际：{sorted(set(seen_phases))}）")

    for needle in EXPECTED_COMMANDS:
        check(any(needle in line for line in seen_logs), f"安装日志里有真命令：{needle}")
    check(len(seen_logs) > 20, f"安装日志有 {len(seen_logs)} 行（后端事件流真的在报）")

    # ── 7. 擦盘守卫：确认对不上就必须拒绝 ──────────────────────────────
    failures.clear()
    install.start({"disk": target, "confirmedDevice": "/dev/别的盘"}, True)
    check(wait_for("拒绝", lambda: bool(failures), 10)
          and "没有确认擦除" in failures[0][0],
          f"擦盘确认对不上 → 控制器拒绝开跑（{failures[0][0] if failures else '没反应'}）")

    if problems:
        print(f"\n{checks['bad']} 项不过：", file=sys.stderr)
        for problem in problems:
            print(f"  · {problem}", file=sys.stderr)
        return 1

    print(f"\n接线烟测通过：{checks['ok']} 项断言全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
