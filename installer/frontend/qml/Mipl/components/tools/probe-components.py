#!/usr/bin/env python3
"""Mipl 组件级探针 —— 阶段 0 的**仓内可跑**证据脚本（离屏）。

跑法：
    QT_QPA_PLATFORM=offscreen python3 installer/frontend/qml/Mipl/components/tools/probe-components.py
    （需要 PySide6 —— 安装器前端栈本来就带，不引入新依赖）

覆盖三件事：
  1. 编译 / 实例化：components/*.qml（每件都 `import Mipl 1.0`）+ ExamplePage.qml → 必须 Ready；
  2. 组件级键盘（08 §3.8）：`Return` / 小键盘 `Enter` / `Space` 都要触发 `clicked`；
     另外菜单项还多验一条：键盘激活要走到 `onTriggered`（菜单项的业务回调挂在它上面）；
  3. 动效时长（08 §3.6）：在 `motionScale = 0.5 / 1.0 / 2.0` 三档读回组件里
     `Behavior.animation.duration`，断言**等于** `MiplMotion.<档位>`（token 单例内部已经乘过
     motionScale，组件不得再乘 —— 复核线抓过一轮 `基准 × motionScale²` 的 F1）。

**踩过的坑（别重蹈）**：Qt 的 `Behavior.animation` 是**懒创建**的 —— 不先触发一次状态变化
（聚焦 / 切换），`QQmlProperty.read(behavior, "animation")` 读到的是 None，看着像「组件没挂动画」。
所以下面每个用例都先制造一次真实的状态变化再读。

口径：本脚本是**离屏、组件级旁证**，不等于 V3 / V5。
  V3（cage 里纯键盘走完整流程）与 V5（真 ISO 视觉基线）必须真 ISO / cage，未跑就记「未实测」。
退出码：0 = 全部 PASS；1 = 有 FAIL；2 = 环境不满足（缺 PySide6 等）。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PySide6.QtCore import QUrl, Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlProperty
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest
except ImportError as exc:  # pragma: no cover
    print(f"[SKIP] 需要 PySide6（安装器前端栈已带）：{exc}")
    sys.exit(2)

# .../qml/Mipl/components/tools/probe-components.py → parents[3] = .../qml
QML_ROOT = Path(__file__).resolve().parents[3]
COMPONENTS_DIR = QML_ROOT / "Mipl" / "components"
EXAMPLE_PAGE = COMPONENTS_DIR / "ExamplePage.qml"

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    ok = bool(ok)
    RESULTS.append((ok, name, detail))
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f" —— {detail}"
    print(line)
    return ok


def section(title: str) -> None:
    print(f"\n== {title} ==")


def cls(obj) -> str:
    return obj.metaObject().className()


def prop(obj, name):
    return obj.property(name)


def descendants(obj) -> list:
    """QObject children ∪ childItems（Repeater 造出来的 delegate 只在 childItems 里）。"""
    out: list = []
    stack = [obj]
    while stack:
        node = stack.pop()
        for child in node.children():
            out.append(child)
            stack.append(child)
        if isinstance(node, QQuickItem):
            for child in node.childItems():
                if child not in out:
                    out.append(child)
                    stack.append(child)
    return out


def instances(root, prefix: str, text: str | None = None) -> list:
    found = [o for o in descendants(root) if cls(o).startswith(prefix)]
    if text is not None:
        found = [o for o in found if prop(o, "text") == text]
    return found


def click_count(obj, win, key) -> int:
    """给控件接上 clicked 计数，聚焦后按一个键，返回 clicked 次数。"""
    hits: list[int] = []
    try:
        obj.clicked.connect(lambda: hits.append(1))
    except Exception:  # 极少数类型没有 clicked
        return -1
    obj.forceActiveFocus()
    QTest.qWait(40)
    QTest.keyClick(win, key)
    QTest.qWait(140)
    return len(hits)


def behavior_durations(obj) -> list[float]:
    """读对象内部**已经物化**的 Behavior.animation.duration（懒创建 —— 调用前必须先触发状态变化）。"""
    out: list[float] = []
    for node in descendants(obj):
        if "Behavior" not in cls(node):
            continue
        try:
            anim = QQmlProperty.read(node, "animation")
        except Exception:
            anim = None
        if anim is not None:
            out.append(round(float(prop(anim, "duration")), 2))
    return out


def approx_all(values: list[float], expected: float, tol: float = 0.01) -> bool:
    return bool(values) and all(abs(v - expected) <= tol for v in values)


def same_multiset(values: list[float], expected: list[float], tol: float = 0.01) -> bool:
    return (len(values) == len(expected)
            and all(abs(a - b) <= tol for a, b in zip(sorted(values), sorted(expected))))


def key_activations(obj, win, key) -> tuple[int, int]:
    """按一个键，返回 (clicked 次数, triggered 次数)。

    计数器用默认参数绑定各自的 list —— 否则多个 lambda 会闭包晚绑定到同一个变量，
    第二个用例会看到累加值（复核时踩过）。
    """
    clicked: list[int] = []
    triggered: list[int] = []
    def on_clicked(bag=clicked):
        bag.append(1)
    def on_triggered(bag=triggered):
        bag.append(1)
    try:
        obj.clicked.connect(on_clicked)
    except Exception:
        return -1, -1
    try:
        obj.triggered.connect(on_triggered)
    except Exception:
        pass
    obj.forceActiveFocus()
    QTest.qWait(50)
    QTest.keyClick(win, key)
    QTest.qWait(160)
    return len(clicked), len(triggered)


def main() -> int:
    print(f"Mipl 组件级探针 · QML 根 = {QML_ROOT}")
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_ROOT))

    warned: list[str] = []
    engine.warnings.connect(lambda ws: [warned.append(w.toString()) for w in ws])

    # ── 1. 编译 / 实例化 ────────────────────────────────────────────────
    section("1. 编译与实例化（每个组件文件都 import Mipl 1.0）")
    component_files = sorted(p for p in COMPONENTS_DIR.glob("*.qml") if p.name != EXAMPLE_PAGE.name)
    print(f"  组件文件 {len(component_files)} 个：{', '.join(p.name for p in component_files)}")
    for path in component_files:
        comp = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
        ready = comp.status() == QQmlComponent.Ready
        errs = "; ".join(e.toString() for e in comp.errors())
        if not check(ready, f"编译 {path.name}", errs):
            continue
        obj = comp.create()
        check(obj is not None, f"实例化 {path.name}",
              "; ".join(e.toString() for e in comp.errors()))

    if not EXAMPLE_PAGE.exists():
        check(False, "ExamplePage.qml 存在")
        return 1
    engine.load(QUrl.fromLocalFile(str(EXAMPLE_PAGE)))
    if not engine.rootObjects():
        check(False, "加载 ExamplePage.qml", "rootObjects 为空")
        return 1
    win = engine.rootObjects()[0]
    win.setProperty("snapshotDelay", 3600_000)   # 别让示例页自己截图退出
    win.requestActivate()
    QTest.qWait(200)
    check(True, "加载 ExamplePage.qml")

    motion = engine.singletonInstance("Mipl", "MiplMotion")

    # ── 2. 组件级键盘 ──────────────────────────────────────────────────
    section("2. 键盘：Return / 小键盘 Enter / Space 都要触发 clicked（08 §3.8）")
    keys = ((Qt.Key_Return, "Return"), (Qt.Key_Enter, "小键盘 Enter"), (Qt.Key_Space, "Space"))

    # MiplButton
    btn = instances(win, "MiplButton_QMLTYPE", "打开确认对话框")[0]
    dlg = instances(win, "MiplDialog_QMLTYPE")[0]
    for key, label in keys:
        if prop(dlg, "opened"):
            dlg.close()
            QTest.qWait(120)
        n = click_count(btn, win, key)
        check(n == 1, f"MiplButton + {label} → clicked×1", f"实际 {n}")

    # MiplSwitch / MiplChip / MiplCheckbox / MiplRadio（checkable：clicked 也该来一次）
    for prefix, label_ in (("MiplSwitch_QMLTYPE", "MiplSwitch"), ("MiplChip_QMLTYPE", "MiplChip"),
                           ("MiplCheckbox_QMLTYPE", "MiplCheckbox"), ("MiplRadio_QMLTYPE", "MiplRadio")):
        node = instances(win, prefix)[0]
        for key, key_label in keys:
            n = click_count(node, win, key)
            check(n == 1, f"{label_} + {key_label} → clicked×1", f"实际 {n}")

    # MiplListItem
    item = instances(win, "MiplListItem_QMLTYPE")[0]
    for key, key_label in keys:
        n = click_count(item, win, key)
        check(n == 1, f"MiplListItem + {key_label} → clicked×1", f"实际 {n}")

    # MiplSegmentedButton 的分段（AbstractButton；clicked 应让 currentIndex 跟着走）
    seg_btn = instances(win, "MiplSegmentedButton_QMLTYPE")[0]
    segments = [o for o in descendants(seg_btn) if "AbstractButton" in cls(o)]
    check(len(segments) == 3, "MiplSegmentedButton 有 3 个分段", f"实际 {len(segments)}")
    if segments:
        for key, key_label in keys:
            n = click_count(segments[1], win, key)
            check(n == 1, f"MiplSegmentedButton 分段 + {key_label} → clicked×1", f"实际 {n}")

    # MiplMenuItem：键盘不仅要触发 clicked，还要走到 triggered（菜单项的业务回调挂在它上面）。
    # 注意：菜单项被激活后**菜单会自动关闭**，关着的菜单里的项拿不到焦点 —— 所以每次按键前都要重开。
    more_menu = instances(win, "MiplMenu_QMLTYPE")[1]
    reported_count = False
    for key, key_label in keys:
        if not prop(more_menu, "opened"):
            more_menu.open()
        QTest.qWait(350)
        menu_items = [o for o in descendants(more_menu) if cls(o).startswith("MiplMenuItem")]
        if not reported_count:
            check(len(menu_items) == 3, "moreMenu 有 3 个 MiplMenuItem", f"实际 {len(menu_items)}")
            reported_count = True
        if not menu_items:
            check(False, f"MiplMenuItem + {key_label}", "菜单项没实体化")
            continue
        c, t = key_activations(menu_items[0], win, key)
        check(c == 1 and t == 1,
              f"MiplMenuItem + {key_label} → clicked×1 且 triggered×1",
              f"clicked={c} triggered={t}")
    if prop(more_menu, "opened"):
        more_menu.close()
        QTest.qWait(150)

    # ── 3. 动效时长 ────────────────────────────────────────────────────
    section("3. 动效：Behavior.animation.duration 必须等于 MiplMotion.<档位>（懒创建，先触发再读）")

    def reset_states() -> None:
        """每个档位重新制造一遍状态变化（Behavior 只在值真的变了时才动画）。"""
        for prefix in ("MiplButton_QMLTYPE", "MiplIconButton_QMLTYPE", "MiplChip_QMLTYPE",
                       "MiplCheckbox_QMLTYPE", "MiplRadio_QMLTYPE", "MiplListItem_QMLTYPE"):
            nodes = instances(win, prefix)
            if len(nodes) >= 2:
                nodes[0].forceActiveFocus()
                QTest.qWait(20)
                nodes[-1].forceActiveFocus()
        switch = instances(win, "MiplSwitch_QMLTYPE")[0]
        switch.setProperty("checked", not bool(prop(switch, "checked")))
        text_fields = instances(win, "MiplTextField_QMLTYPE")
        empty = next((o for o in text_fields if not prop(o, "displayText")), None)
        if empty is not None:
            empty.setProperty("text", "probe")
        seg = instances(win, "MiplSegmentedButton_QMLTYPE")[0]
        segs = [o for o in descendants(seg) if "AbstractButton" in cls(o)]
        if len(segs) >= 2:
            segs[0].forceActiveFocus()
            QTest.qWait(20)
            segs[-1].forceActiveFocus()
        # 菜单项：开菜单后给两项轮流焦点
        menu = instances(win, "MiplMenu_QMLTYPE")[0]
        if not prop(menu, "opened"):
            menu.open()
        QTest.qWait(250)
        m_items = [o for o in descendants(menu) if cls(o).startswith("MiplMenuItem")]
        if len(m_items) >= 2:
            m_items[0].forceActiveFocus()
            QTest.qWait(20)
            m_items[1].forceActiveFocus()
        snack = instances(win, "MiplSnackbar_QMLTYPE")[0]
        if not prop(snack, "opened"):
            snack.setProperty("message", "probe")
            snack.open()
        QTest.qWait(150)
        action = [o for o in descendants(snack) if "AbstractButton" in cls(o)]
        if action:
            action[0].forceActiveFocus()

    for scale in (0.5, 1.0, 2.0):
        motion.setProperty("motionScale", scale)
        QTest.qWait(80)
        reset_states()
        QTest.qWait(int(500 * scale) + 200)

        short2, short3, short4, extra_long4 = (float(prop(motion, k))
                                               for k in ("short2", "short3", "short4", "extraLong4"))
        print(f"  -- motionScale={scale}  token: short2={short2} short3={short3} "
              f"short4={short4} extraLong4={extra_long4}")

        cases = (
            ("MiplButton(状态层)", "MiplButton_QMLTYPE", [short2]),
            ("MiplIconButton(状态层)", "MiplIconButton_QMLTYPE", [short2]),
            ("MiplChip(状态层)", "MiplChip_QMLTYPE", [short2]),
            ("MiplCheckbox(状态层)", "MiplCheckbox_QMLTYPE", [short2]),
            ("MiplRadio(状态层)", "MiplRadio_QMLTYPE", [short2]),
            ("MiplListItem(状态层)", "MiplListItem_QMLTYPE", [short2]),
            # 开关有三处：轨道状态层 short2 + 拇指 x/width 各一个 short4
            ("MiplSwitch(状态层 short2 + 拇指 x/width short4)", "MiplSwitch_QMLTYPE",
             [short2, short4, short4]),
            ("MiplTextField(浮动标签 y/pixelSize short3)", "MiplTextField_QMLTYPE", [short3, short3]),
        )
        for label_, prefix, expected in cases:
            nodes = instances(win, prefix)
            got: list[float] = []
            for node in nodes:
                got = behavior_durations(node)
                if got:
                    break
            check(same_multiset(got, expected),
                  f"[{scale}] {label_} Behavior == {expected}", f"实际 {got}")

        seg = instances(win, "MiplSegmentedButton_QMLTYPE")[0]
        check(approx_all(behavior_durations(seg), short2),
              f"[{scale}] MiplSegmentedButton 分段 Behavior == {short2}",
              f"实际 {behavior_durations(seg)}")

        menu = instances(win, "MiplMenu_QMLTYPE")[0]
        menu_got: list[float] = []
        for node in descendants(menu):
            if cls(node).startswith("MiplMenuItem"):
                menu_got = behavior_durations(node)
                if menu_got:
                    break
        check(approx_all(menu_got, short2),
              f"[{scale}] MiplMenuItem Behavior == {short2}", f"实际 {menu_got}")

        snack = instances(win, "MiplSnackbar_QMLTYPE")[0]
        check(approx_all(behavior_durations(snack), short2),
              f"[{scale}] MiplSnackbar 动作 Behavior == {short2}",
              f"实际 {behavior_durations(snack)}")

        # LinearProgress 的循环动画是 SequentialAnimation 的 QObject 子对象，不用触发
        lp = instances(win, "MiplLinearProgress_QMLTYPE")[0]
        lp_durations = [round(float(prop(c, "duration")), 2)
                        for node in descendants(lp) if "SequentialAnimation" in cls(node)
                        for c in node.children() if "NumberAnimation" in cls(c)]
        check(approx_all(lp_durations, extra_long4),
              f"[{scale}] MiplLinearProgress 循环 == {extra_long4}", f"实际 {lp_durations}")

    motion.setProperty("motionScale", 1.0)

    # ── 汇总 ───────────────────────────────────────────────────────────
    failed = [name for ok, name, _ in RESULTS if not ok]
    passed = len(RESULTS) - len(failed)
    print(f"\n== 汇总 ==\n  共 {len(RESULTS)} 项：PASS {passed}，FAIL {len(failed)}")
    if warned:
        print(f"  QML 警告 {len(warned)} 条（不计入 PASS/FAIL，但值得看）：")
        for w in warned:
            print(f"    WARN: {w}")
    if failed:
        print("  失败项：")
        for name in failed:
            print(f"    - {name}")
        print("\n结果：FAIL（离屏、组件级；V3/V5 仍需真 ISO / cage）")
        QTimer.singleShot(10, app.quit)
        app.exec()
        return 1
    print("\n结果：全过（离屏、组件级旁证；V3 键盘全流程与 V5 视觉基线仍需真 ISO / cage，未跑记「未实测」）")
    QTimer.singleShot(10, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
