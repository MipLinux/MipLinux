#!/usr/bin/env python3
"""流程烟测：把 `qml/Main.qml` 跑起来，用信号走一遍整条链，逐跳断言。

**为什么需要它：单页取图看不出接线错。** 少接一个信号、属性名写错一个字母，
都要等人在 VM 里点到那一步才发现 —— 这个脚本第一次跑就抓到 `AdvancedPage`
漏声明 `backRequested`（点了「返回」会报 TypeError）。把「点一遍」变成一条命令：

    python3 installer/frontend/tools/flow-check.py           # 路由与状态传递
    python3 installer/frontend/tools/flow-check.py --demo    # 连假安装演完再断言（约 12 秒）
    python3 installer/frontend/tools/flow-check.py -v        # 每一步都打印当前页

覆盖的链（评审定的顺序）：

    加载 → 欢迎 → 网络 → 系统磁盘 → 磁盘分区 → 确认擦除 → 账户 → 安装详情 → 安装 → 结束
    分支：欢迎 → 高级安装 → 语言 → 返回 → 高级安装 → 返回

**不驱动真安装**（G3 不接后端）：安装页那一段是 `Main.qml` 里的假脚本，
`--demo` 只是等它演完，确认「装完自己进结束页」这条跳转是通的。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent
MAIN_QML = FRONTEND / "qml" / "Main.qml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flow-check.py", description="流程壳烟测")
    parser.add_argument("--demo", action="store_true",
                        help="等假安装演完（约 12 秒）再断言到结束页")
    parser.add_argument("--step-ms", type=int, default=120,
                        help="每一跳之间让事件循环转多久（默认 120ms）")
    parser.add_argument("-v", "--verbose", action="store_true", help="每一步都打印当前页")
    args = parser.parse_args(argv)

    import os
    # 与取图同一套：offscreen 下不弹窗、devicePixelRatio 恒为 1，CI/无显示环境也能跑
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression

    sys.path.insert(0, str(FRONTEND))
    from bridge.icons import register_icon_provider

    app = QGuiApplication([sys.argv[0]])
    engine = QQmlApplicationEngine()
    register_icon_provider(engine)

    problems: list[str] = []
    engine.warnings.connect(
        lambda errs: [problems.append(f"QML: {e.toString()}") for e in errs]
    )
    engine.load(QUrl.fromLocalFile(str(MAIN_QML)))
    roots = engine.rootObjects()
    if not roots:
        print("流程壳没加载起来", file=sys.stderr)
        return 1
    root = roots[0]

    checks = {"ok": 0, "bad": 0}

    def spin(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def page() -> str:
        return str(root.property("page"))

    def item():
        return root.property("currentPage")

    def call(code: str) -> None:
        """在当前页的 item 上求值一段 JS —— `chosen('x')` 这种就是「点一下」。"""
        expr = QQmlExpression(engine.rootContext(), item(), code)
        expr.evaluate()
        if expr.hasError():
            problems.append(f"{page()} 上求值 {code!r} 出错：{expr.error().toString()}")

    def expect(want: str, what: str) -> None:
        got = page()
        ok = got == want
        checks["ok" if ok else "bad"] += 1
        print(f"  [{'ok' if ok else '!!'}] {what}：{got}" + ("" if ok else f"（期望 {want}）"))
        if not ok:
            problems.append(f"{what}：期望 {want}，实际 {got}")

    def value(name: str):
        """读当前页的一个属性。QML 的 `var`（数组 / 对象）读出来是 QJSValue，
        要 `toVariant()` 转成 Python 的 list/dict 才能断言。"""
        it = item()
        if it is None:
            return None
        raw = it.property(name)
        return raw.toVariant() if hasattr(raw, "toVariant") else raw

    def expect_value(name: str, want, what: str) -> None:
        got = value(name)
        ok = got == want
        checks["ok" if ok else "bad"] += 1
        print(f"  [{'ok' if ok else '!!'}] {what}（{name} = {got!r}）"
              + ("" if ok else f"（期望 {want!r}）"))
        if not ok:
            problems.append(f"{what}：{name} 期望 {want!r}，实际 {got!r}")

    # 加载页停一下会自己进欢迎页
    spin(1600)
    expect("welcome", "加载页 → 欢迎页")

    # ── 分支：高级安装（语言 / 键盘 / 时区 / 主机名）────────────────────
    call("customizeRequested()")
    spin(args.step_ms)
    expect("advanced", "欢迎页「高级安装」")

    rows = value("rows")
    if not rows or len(rows) != 4 or [r["page"] for r in rows] != ["language", "keyboard", "timezone", "hostname"]:
        problems.append(f"高级安装的四行不对：{rows}")
    else:
        checks["ok"] += 1
        print("  [ok] 高级安装四行：语言 / 键盘 / 时区 / 主机名")

    call("rowChosen('language')")
    spin(args.step_ms)
    expect("language", "高级安装 → 语言")
    expect_value("selectedLocale", "zh_CN.UTF-8", "语言页带上了当前值")

    call("chosen('en_US.UTF-8')")
    spin(args.step_ms)
    expect("advanced", "语言选完 → 回高级安装")
    rows = value("rows")
    if rows and rows[0]["value"] == "en_US.UTF-8" and rows[0]["changed"] is True:
        checks["ok"] += 1
        print("  [ok] 语言改成 en_US.UTF-8，行上出现「改过」标记")
    else:
        problems.append(f"改过的语言没反映到高级安装：{rows[0] if rows else None}")

    call("backRequested()")
    spin(args.step_ms)
    expect("welcome", "高级安装「返回」→ 欢迎页")

    # ── 主流程 ────────────────────────────────────────────────────────
    call("installRequested()")
    spin(args.step_ms)
    expect("network", "欢迎页「开始安装」→ 网络")
    expect_value("online", True, "网络页显示已连接（流程注入）")

    call("continueRequested()")
    spin(args.step_ms)
    expect("disk", "网络「继续」→ 系统磁盘")

    call("chosen('/dev/vda')")
    spin(args.step_ms)
    expect("partition", "选盘 → 磁盘分区")
    expect_value("device", "/dev/vda", "分区页收到了目标盘")

    call("continueRequested()")
    spin(args.step_ms)
    expect("erase-confirm", "分区「继续」→ 确认擦除")
    expect_value("device", "/dev/vda", "确认擦除页收到了目标盘")

    call("confirmedRequested('/dev/vda')")
    spin(args.step_ms)
    expect("account", "逐字确认 → 账户")
    expect_value("hostName", "mipl", "账户页带上了主机名（高级安装里的值）")

    call("accountChosen('mipl', 'mipl', 'mipl-2026', false)")
    spin(args.step_ms)
    expect("install-details", "账户 → 安装详情")

    # 安装详情是「装前核对」：值必须是流程里那些，不是页面自己的默认值
    expect_value("userName", "mipl", "详情页带上了账户")
    expect_value("localeName", "en_US.UTF-8", "详情页带上了改过的语言")
    expect_value("rootHasPassword", False, "详情页如实反映 root 保持锁定")

    call("installRequested()")
    spin(200)
    expect("install", "详情页「开始安装」→ 安装")
    expect_value("phase", "start", "假安装从 start 起步")
    log_lines = value("logLines")
    if log_lines:
        checks["ok"] += 1
        print(f"  [ok] 安装页已收到第一批日志（{len(log_lines)} 行）")
    else:
        problems.append("安装页没有日志 —— 假安装没驱动起来")

    if args.demo:
        print("  … 等假安装演完（约 12 秒）")
        for _ in range(200):                     # 最多等 20 秒
            spin(100)
            if page() == "done":
                break
        expect("done", "假安装演完 → 结束页")

    if problems:
        print(f"\n{checks['bad'] + len(problems)} 个问题：", file=sys.stderr)
        for p in problems:
            print(f"  · {p}", file=sys.stderr)
        return 1

    print(f"\n流程烟测通过：{checks['ok']} 项断言全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
