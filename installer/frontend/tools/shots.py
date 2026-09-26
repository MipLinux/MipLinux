#!/usr/bin/env python3
"""把 QML 页面渲染成 PNG —— 原型评审与验收的取图工具。

**为什么不用 `qmlscene` / `qml`：** 本机（CachyOS，Qt 6.11.2 + PySide6）实测这两个
Qt 自带工具**连纯 QML 文件都加载不了**，一律报 `Library import requires a version`
（`file://…:-1`，连文件名都是空的 —— 那是 Qt 工具自身的动态库版本问题，与 QML 内容无关）。
同一个文件用 PySide6 的 `QQmlApplicationEngine` 直接加载则完全正常。

所以取图走这条路：**它同时也是安装器真身要用的那条路**（`mipl-installer` 本来就是
PySide6 程序），所以这个工具不是临时脚手架，而是「本机快速迭代」的标准姿势。

用法：

    python3 installer/frontend/tools/shots.py                    # 全部页面
    python3 installer/frontend/tools/shots.py --page welcome     # 只取一张
    python3 installer/frontend/tools/shots.py --out /tmp/shots   # 换输出目录
    python3 installer/frontend/tools/shots.py --list             # 看有哪些页面

产出默认落 `out/m2-prototype/`（已 gitignore）—— 截图是 QML 的**生成物**，
与 `out/`、`*.iso` 同一条纪律，不进仓库。文档里给的是命令，不是会过期的图。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

#: 与 QML 里 `Tokens.qml` 的 pagePadding / 主画布一致（设计文档 §设计语言）。
DEFAULT_SIZE = (1280, 800)

FRONTEND = Path(__file__).resolve().parent.parent
QML_DIR = FRONTEND / "qml"

#: 页面名 → (QML 文件, 画布宽, 画布高)
#: 高默认 800；需要整页滚动的内容可用 --size 覆盖。
#: 排版样张要一张图看全（宽 880 时内容高约 1170），所以它单独给一个高画布。
TALL_SIZE = (1280, 2100)

PAGES: dict[str, tuple[str, int, int]] = {
    "tokens": ("theme/TokensPage.qml", *TALL_SIZE),
    "gallery": ("GalleryPage.qml", 1280, 3260),
    # 流程壳（唯一的 Window）。默认停在加载页；想看别的屏用
    # `--set page=welcome`（页面名见 qml/Main.qml 的 pageFiles）。
    "flow": ("Main.qml", *DEFAULT_SIZE),
    "loading": ("pages/LoadingPage.qml", *DEFAULT_SIZE),
    "welcome": ("pages/WelcomePage.qml", *DEFAULT_SIZE),
    "advanced": ("pages/AdvancedPage.qml", *DEFAULT_SIZE),
    "language": ("pages/LanguagePage.qml", *DEFAULT_SIZE),
    "keyboard": ("pages/KeyboardPage.qml", *DEFAULT_SIZE),
    "timezone": ("pages/TimezonePage.qml", *DEFAULT_SIZE),
    "hostname": ("pages/HostnamePage.qml", *DEFAULT_SIZE),
    "network": ("pages/NetworkPage.qml", *DEFAULT_SIZE),
    "disk": ("pages/DiskPage.qml", *DEFAULT_SIZE),
    "partition": ("pages/PartitionPage.qml", *DEFAULT_SIZE),
    "erase-confirm": ("pages/EraseConfirmPage.qml", *DEFAULT_SIZE),
    "account": ("pages/AccountPage.qml", *DEFAULT_SIZE),
    "install-details": ("pages/InstallDetailsPage.qml", *DEFAULT_SIZE),
    "install": ("pages/InstallPage.qml", *DEFAULT_SIZE),
    "install-failed": ("pages/InstallFailedPage.qml", *DEFAULT_SIZE),
    "done": ("pages/DonePage.qml", *DEFAULT_SIZE),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="shots.py",
        description="把每个原型页面渲染成 PNG（走 PySide6，不用 qmlscene）。",
    )
    parser.add_argument("--page", action="append", default=None,
                        help="只取指定页面，可重复；默认全部")
    parser.add_argument("--out", default="out/m2-prototype",
                        help="输出目录（默认 out/m2-prototype，已 gitignore）")
    parser.add_argument("--size", default=None, metavar="WxH",
                        help=f"覆盖画布尺寸，例如 1024x600；默认 {'x'.join(map(str, DEFAULT_SIZE))}")
    parser.add_argument("--settle", type=int, default=1200, metavar="MS",
                        help="取图前等多久，让动效走到终点（默认 1200ms）")
    parser.add_argument("--list", action="store_true", help="列出所有页面名后退出")
    parser.add_argument("--no-build", action="store_true",
                        help="不自动构建 assets/ 里的 logo（默认缺了就建）")
    parser.add_argument("--set", action="append", default=None, metavar="属性=值",
                        help="取图前设置根对象上的属性，可重复。值按 JSON 解析，"
                             "例如 --set submitted=true --set userName=\"mipl\"；"
                             "用来取「错误态」「选中态」这类需要交互才出现的画面")
    parser.add_argument("--measure", action="store_true",
                        help="取图后打印内容高 / 可用高 / 是否需要滚动 —— "
                             "验收「1280×800 一屏放得下」用，见 tech/07 §2.8")
    return parser.parse_args(argv)


def coerce(raw: str):
    """把命令行给的值按 JSON 解析；解析不了就当字符串（省得为每个值加引号）。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def build_assets(quiet: bool = False, force: bool = False) -> None:
    """按 Assets.py 里的规格，把 LOGO 源图缩放成界面用的小图。

    图片本身不进仓库（见 Assets.py 的说明），所以**缺了就现建**：
    换一台机器、换一次 clone，界面不会因为少一张图而开不起来。
    """
    script = FRONTEND / "tools" / "build-assets.sh"
    if not script.is_file():
        return
    cmd = ["bash", str(script)]
    if quiet:
        cmd.append("--quiet")
    if force:
        cmd.append("--force")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"生成 logo 资产失败（退出码 {proc.returncode}）")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list:
        for name in PAGES:
            print(name)
        return 0

    names = args.page or list(PAGES)
    unknown = [n for n in names if n not in PAGES]
    if unknown:
        raise SystemExit(f"不认识的页面：{'、'.join(unknown)}（--list 看全部）")

    if args.size:
        try:
            width, height = (int(v) for v in args.size.lower().split("x"))
        except ValueError:
            raise SystemExit("--size 要写成 1280x800 这种形式")
        for name in names:
            file, _, _ = PAGES[name]
            PAGES[name] = (file, width, height)

    if not args.no_build:
        # LOGO 的 PNG **在仓库里**（理由见 assets/README.md），所以正常情况下这里
        # 什么都不用做。这一句只是给「刚换过 LOGO、手抖删了图」兜底 ——
        # 生成不了也不算错，QML 那边会画一个「LOGO 未生成」的占位，照样能取图。
        try:
            build_assets(quiet=True)
        except SystemExit as exc:
            print(f"提示：{exc}", file=sys.stderr)

    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise SystemExit(
            f"没有权限写 {out_dir}\n"
            f"  → out/ 是构建脚本以 root 建的。换目录：--out /tmp/m2-shots"
        )

    # 取图一律走 offscreen 平台插件，**不是**为了"无头"：
    # 宿主显示器在 1.66667 缩放下，普通窗口抓出来是设备像素（1280×800 的逻辑窗口
    # 抓成 2133×1333），同一份 QML 在两台机器上会得到不同尺寸的图。
    # offscreen 下 devicePixelRatio 恒为 1，取图是**确定性**的。
    # 出图不弹窗，顺带避免取图期间在用户屏幕上闪一堆窗口。
    os.environ["QT_QPA_PLATFORM"] = os.environ.get("MIPL_SHOTS_PLATFORM", "offscreen")

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QGuiApplication, QWindow
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow

    # 图标走 image://lucide/… —— 没有这个 provider，所有图标都是空的。
    # 安装器真身（mipl-installer）也要注册同一份，见 bridge/icons.py。
    sys.path.insert(0, str(FRONTEND))
    from bridge.icons import register_icon_provider

    app = QGuiApplication([sys.argv[0]])

    failures: list[str] = []
    for name in names:
        rel, width, height = PAGES[name]
        target = QML_DIR / rel
        if not target.is_file():
            print(f"跳过 {name}：{rel} 还不存在", file=sys.stderr)
            failures.append(f"{name}（文件不存在）")
            continue

        engine = QQmlApplicationEngine()
        register_icon_provider(engine)
        engine.warnings.connect(
            lambda errs, n=name: [print(f"[{n}] QML: {e.toString()}", file=sys.stderr) for e in errs]
        )
        engine.load(QUrl.fromLocalFile(str(target)))

        roots = engine.rootObjects()
        if not roots:
            print(f"[{name}] 加载失败：root object 没建起来", file=sys.stderr)
            failures.append(name)
            continue

        item = roots[0]

        # 页面根有两类（2026-09-25 之后）：
        #   · **Item** —— 绝大多数页面（PageShell 的根）。Item 自己不是窗口，
        #     取不了图，所以现造一个 QQuickWindow 把它装进去、按需要的尺寸铺开；
        #   · **Window** —— 加载页、`Main.qml`（流程壳）这些自己就是窗口的。
        # 两种都在这里归一到 `win`（真正被 grabWindow 的那个窗口）。
        if isinstance(item, QQuickWindow):
            win = item
            # 真跑时窗口是 kiosk 全屏（`Main.qml` 里 `visibility: Window.FullScreen` ——
            # 不然 Qt 的 Wayland 插件会自己画标题栏 + 关闭按钮）。取图要**确定性**尺寸，
            # 所以先掰回窗口模式再定宽高，否则截出来的是这台机器屏幕的尺寸。
            win.setVisibility(QWindow.Windowed)
            win.setWidth(width)
            win.setHeight(height)
        else:
            win = QQuickWindow()
            win.setWidth(width)
            win.setHeight(height)
            item.setParentItem(win.contentItem())
            item.setWidth(width)
            item.setHeight(height)
            win.show()

        # 属性注入要在**取图之前**设完：这些是「点过按钮才会出现」的状态
        # （错误态、选中态），没有它就只能靠改默认值取图，取完还得改回来。
        for assignment in (args.set or []):
            prop, sep, raw = assignment.partition("=")
            if not sep or not prop:
                raise SystemExit(f"--set 要写成 属性=值：{assignment!r}")
            if not item.setProperty(prop, coerce(raw)):
                print(f"[{name}] 根对象上没有属性 {prop!r}", file=sys.stderr)

        # 一个页面一个引擎：上一页的组件缓存不会串味。
        # engine 与（可能现造的）窗口都必须活到取完图 —— 用闭包持有它们。
        def save(w=win, it=item, n=name, e=engine) -> None:
            image = w.grabWindow()
            path = out_dir / f"{n}.png"
            if not image.save(str(path)):
                print(f"[{n}] 存图失败：{path}", file=sys.stderr)
                failures.append(n)
            else:
                print(f"  {n:<14} {image.width()}×{image.height()}  {path}")
                if args.measure and hasattr(it, "contentHeight"):
                    # 量的是**排完版之后**的值，所以必须在 settle 之后调
                    # （抛光阶段直接读会停在很早的一次测量上，PageShell 文件头有记录）
                    content = it.contentHeight()
                    avail = it.property("contentAvailableHeight")
                    verdict = "需要滚动" if content > avail else "一屏放得下"
                    print(f"  {'':<14} 内容高 {content:.0f} / 可用高 {avail:.0f} → {verdict}")
            app.quit()

        QTimer.singleShot(args.settle, save)
        app.exec()

    if failures:
        print(f"\n有 {len(failures)} 个页面没取到图：{'、'.join(failures)}", file=sys.stderr)
        return 1
    print(f"\n全部取图完成 → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

