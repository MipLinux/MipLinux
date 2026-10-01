#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真加载探针：把 `import Mipl 1.0` 跑起来，读回单例的值。

为什么除了 check-tokens.py 还要它（README §1 把取证方式定成「对最终产物复跑同口径探针」）：
- 静态解析与 `qmllint` **都抓不到** QML 的 `on-*` 信号处理器陷阱 —— qmllint 对
  `readonly property color onPrimary: ...`（同对象还有 `primary`）返回 0，只有真加载才会报
  “Cannot assign a value to a signal”。`--self-test` 会把这条价值现场验一遍。
- 单例能不能被 import、绑定是否真的求值，只有加载过才知道。

用法：
    python3 installer/frontend/qml/Mipl/tokens/tools/probe-tokens.py
        → 不注册 MiplLaunch（token-only 探针），断言 MiplColor 走回落暗色
    python3 .../probe-tokens.py --launcher
        → 按 README §2 的契约注册一个假 MiplLaunch（注册 → 建引擎 → load），验证主题跟随
    python3 .../probe-tokens.py --self-test
        → 用临时目录里的「天真写法」模块验证：qmllint 静默、加载报错

退出码：0 = 断言全过；1 = 断言失败；2 = 环境/参数问题（比如没有 PySide6）。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

# 探针 QML：不落盘也放进仓库 —— 用 QQmlComponent.setData 喂给引擎，避免多一个 .qml 文件。
PROBE_QML = textwrap.dedent(
    """
    import QtQuick
    import Mipl 1.0

    Item {
        property color probePrimary: MiplColor.primary
        property color probeSurface: MiplColor.surface
        property real probeBodyMediumSize: MiplType.bodyMedium.size
        property real probeShapeExtraLarge: MiplShape.extraLarge
        property QtObject themeSingleton: MiplTheme
    }
    """
).lstrip()

# 天真写法：QML 会把它当成「信号 Primary 的处理器」——用来给 --self-test 当反例。
NAIVE_QMlDIR = "module Mipl\nsingleton MiplColor 1.0 tokens/MiplColor.qml\n"
NAIVE_MIPLCOLOR = textwrap.dedent(
    """
    pragma Singleton
    import QtQuick
    QtObject {
        readonly property color primary: "#adc6ff"
        readonly property color onPrimary: "#102f60"
    }
    """
).lstrip()
NAIVE_PROBE = textwrap.dedent(
    """
    import QtQuick
    import Mipl 1.0
    Item { property color p: MiplColor.onPrimary }
    """
).lstrip()


def report(ok: bool, label: str, got, want) -> None:
    print("  %-52s got=%-12s want=%-12s %s" % (label, got, want, "PASS" if ok else "FAIL"))


def fail(msg: str) -> int:
    print("❌ %s" % msg)
    return 1


def main() -> int:
    here = Path(__file__).resolve()
    parser = argparse.ArgumentParser(description="真加载探针：import Mipl 1.0 并读回单例")
    parser.add_argument("--qml-root", type=Path, default=here.parents[3],
                        help="QML import 根目录（默认：脚本上溯 3 级 = installer/frontend/qml）")
    parser.add_argument("--launcher", action="store_true",
                        help="注册假 MiplLaunch，验证 README §2 的注入契约")
    parser.add_argument("--self-test", action="store_true",
                        help="验证「qmllint 静默、加载报错」这条 on-* 陷阱")
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QObject, Property, QUrl, Signal
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonInstance
    except ImportError as exc:
        print("❌ 需要 PySide6（本机 6.11.2 已装）：%s" % exc)
        return 2

    qml_root = args.qml_root.resolve()
    if not (qml_root / "Mipl" / "qmldir").is_file():
        return fail("%s 下没有 Mipl/qmldir，不是 QML import 根目录" % qml_root)

    if args.self_test:
        return self_test(qml_root, QGuiApplication, QQmlComponent, QQmlEngine, QUrl)

    print("QML import 根目录: %s" % qml_root)
    app = QGuiApplication(sys.argv[:1])
    launch = None
    if args.launcher:
        # README §2：启动器在 engine.load() 之前注册；实测最稳的顺序是「注册 → 建引擎 → load」
        class _Launch(QObject):
            themeChanged = Signal()

            def __init__(self) -> None:
                super().__init__()
                self._theme = "light"

            def get_theme(self) -> str:
                return self._theme

            def set_theme(self, value: str) -> None:
                self._theme = value
                self.themeChanged.emit()

            theme = Property(str, get_theme, set_theme, notify=themeChanged)

        launch = _Launch()
        qmlRegisterSingletonInstance(_Launch, "Mipl", 1, 0, "MiplLaunch", launch)
        print("模式: 注册假 MiplLaunch（注册 → 建引擎 → load）")

    engine = QQmlEngine()
    engine.addImportPath(str(qml_root))

    component = QQmlComponent(engine)
    component.setData(PROBE_QML.encode("utf-8"), QUrl.fromLocalFile(str(qml_root / "probe-tokens.qml")))
    item = component.create()

    print()
    print("== 加载结果 ==")
    status_ready = component.status() == QQmlComponent.Status.Ready
    report(status_ready, "component.status == Ready", str(component.status()).split(".")[-1], "Ready")
    if not status_ready or item is None:
        for error in component.errors():
            print("   %s" % error.toString())
        return fail("探针没加载起来（上面是 QML 的错误）")

    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got == want
        if not ok:
            failures += 1
        report(ok, label, got, want)

    if args.launcher:
        print()
        print("== README §2 注入契约 ==")
        theme = item.property("themeSingleton")
        check("MiplLaunch.theme='light' -> MiplTheme.dark", theme.property("dark"), False)
        check("  -> MiplColor.primary", item.property("probePrimary").name(), "#445e91")
        check("  -> MiplColor.surface", item.property("probeSurface").name(), "#f9f9ff")
        launch.set_theme("dark")
        check("MiplLaunch.theme='dark' -> MiplTheme.dark", theme.property("dark"), True)
        check("  -> MiplColor.primary", item.property("probePrimary").name(), "#adc6ff")
        theme.setProperty("locked", True)
        theme.setProperty("manualDark", False)
        launch.set_theme("dark")
        check("locked + manualDark=false -> dark（不再跟随）", theme.property("dark"), False)
    else:
        print()
        print("== 验收断言（无 MiplLaunch，回落暗色） ==")
        check('MiplColor.primary == "#adc6ff"', item.property("probePrimary").name(), "#adc6ff")
        check('MiplColor.surface == "#111318"', item.property("probeSurface").name(), "#111318")
        check("MiplType.bodyMedium.size == 14", item.property("probeBodyMediumSize"), 14.0)
        check("MiplShape.extraLarge == 28", item.property("probeShapeExtraLarge"), 28.0)
        check("MiplTheme.dark（回落暗色）", item.property("themeSingleton").property("dark"), True)

    print()
    if failures:
        print("❌ %d 项断言失败" % failures)
        return 1
    print("✅ 加载 Ready，全部断言通过")
    return 0


def self_test(qml_root, QGuiApplication, QQmlComponent, QQmlEngine, QUrl) -> int:
    """临时目录里造一个「天真写法」模块：qmllint 静默，但加载必须报错。"""
    print("== --self-test：加载探针能抓住 qmllint 抓不到的 on-* 陷阱 ==")
    with tempfile.TemporaryDirectory(prefix="mipl-tokens-selftest-") as tmp:
        root = Path(tmp)
        (root / "Mipl" / "tokens").mkdir(parents=True)
        (root / "Mipl" / "qmldir").write_text(NAIVE_QMlDIR, encoding="utf-8")
        naive = root / "Mipl" / "tokens" / "MiplColor.qml"
        naive.write_text(NAIVE_MIPLCOLOR, encoding="utf-8")
        probe = root / "P.qml"
        probe.write_text(NAIVE_PROBE, encoding="utf-8")

        lint = shutil.which("qmllint")
        lint_rc = None
        if lint:
            lint_rc = subprocess.run([lint, "-I", str(root), str(naive)],
                                     capture_output=True, text=True).returncode
            print("  qmllint 对天真写法: exit=%d %s"
                  % (lint_rc, "(静默 —— 正是这个陷阱最难发现的地方)" if lint_rc == 0
                     else "(有输出：%s)" % (lint_rc,)))
        else:
            print("  qmllint 不在 PATH：跳过「静默」这一步（未实测）")

        app = QGuiApplication(sys.argv[:1])
        engine = QQmlEngine()
        engine.addImportPath(str(root))
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(probe)))
        item = component.create()
        loaded = component.status() == QQmlComponent.Status.Ready and item is not None
        errors = [e.toString() for e in component.errors()]
        print("  真加载同一天真写法: status=%s" % str(component.status()).split(".")[-1])
        for error in errors[:3]:
            print("    %s" % (error.split("qml/")[-1] if "qml/" in error else error))

        # 真实树必须加载得起来（对照组）
        real_engine = QQmlEngine()
        real_engine.addImportPath(str(qml_root))
        real = QQmlComponent(real_engine)
        real.setData(PROBE_QML.encode("utf-8"),
                     QUrl.fromLocalFile(str(qml_root / "probe-tokens.qml")))
        real_item = real.create()
        real_ok = real.status() == QQmlComponent.Status.Ready and real_item is not None
        print("  真实单例树: status=%s" % str(real.status()).split(".")[-1])

        print()
        ok = (not loaded) and real_ok and (lint_rc in (None, 0))
        if not ok:
            print("❌ 自检不成立：天真写法 loaded=%s（应加载失败）、真实树 ok=%s、qmllint=%s"
                  % (loaded, real_ok, lint_rc))
            return 1
        print("✅ 自检成立：天真写法 qmllint exit=0 但加载失败；真实单例树加载 Ready")
        return 0


if __name__ == "__main__":
    sys.exit(main())
