#!/usr/bin/env python3
"""图标库：把 `icons/lucide/*.svg` 按名字取出来、染成需要的颜色。

## 为什么需要这个（而不是直接把 SVG 丢给 Image）

Lucide 的每个 SVG 都写 `stroke="currentColor"`。**Qt 的 SVG 渲染器不认这个关键字**，
实测渲染出来是**纯黑**；`Image` 的 `color` 属性也染不了它（那是给单色位图用的）。
所以必须在渲染前把 `currentColor` 换成真实色值。

顺带解决三件事：
  · **按需**：只用到的图标才会被渲染成位图（仓库里也只放用到的那些 SVG）；
  · **可染色**：同一图标多个颜色（强调 / 次要 / 危险 / 成功）各自缓存；
  · **不依赖图标主题**：Live 里没有完整的 `breeze-icons`，`QIcon::fromTheme` 取不到东西。

## Qt 用法

```python
engine = QQmlApplicationEngine()
engine.addImageProvider("lucide", LucideIconProvider(ICON_DIR))
```

QML 里：

```qml
Image { source: "image://lucide/lock?color=2A78EC&w=16" }
```

`Icon.qml` 已经把这一串拼好了，业务代码只用 `Icon { name: "lock"; size: 16 }`。

## 图标集

Lucide（ISC；其中一批派生自 Feather，MIT）。完整许可随图标一起在
`icons/lucide/LICENSE` —— **那份文件必须跟着分发**，两个许可都要求保留版权声明。
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

#: 图标目录：`installer/frontend/icons/lucide/`
ICON_DIR = Path(__file__).resolve().parent.parent / "icons" / "lucide"

#: `currentColor` 是 Lucide 的统一写法；换掉它就能染色。
_CURRENT_COLOR_RE = re.compile(r"currentColor")

#: 渲染尺寸上限，防止有人传个特别大的 w 把内存吃光。
MAX_SIZE = 512

#: 默认渲染尺寸 —— 屏幕是 HiDPI 时图标要留足像素再缩放。
DEFAULT_SIZE = 64


class LucideIconProvider(QQuickImageProvider):
    """`image://lucide/<name>?color=RRGGBB&w=<px>` → 染好色的位图。

    缓存键是 (名字, 颜色, 尺寸)。一个界面里同一图标的同一种颜色只会渲染一次 ——
    网络列表里每行都有锁，没有缓存就是每行都跑一遍 SVG 解析。
    """

    def __init__(self, icon_dir: Path | str = ICON_DIR) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.icon_dir = Path(icon_dir)
        self._cache: dict[tuple[str, str, int], QImage] = {}
        self._source_cache: dict[str, str] = {}

    # ── 取源文件 ──────────────────────────────────────────────────────
    def _svg_text(self, name: str) -> str | None:
        """读出 SVG 源文本（带缓存）。名字不存在就返回 None。"""
        if name in self._source_cache:
            return self._source_cache[name]

        # 名字里不许有路径分隔符：`image://lucide/../../etc/passwd` 这种要挡住
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return None

        path = self.icon_dir / f"{name}.svg"
        if not path.is_file():
            return None

        text = path.read_text(encoding="utf-8")
        self._source_cache[name] = text
        return text

    # ── 渲染 ──────────────────────────────────────────────────────────
    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:  # noqa: N802 (Qt 命名)
        # image_id 形如 "lock?color=2A78EC&w=16"。`size` 是输出参数，要就地写回真实尺寸。
        name, _, query = image_id.partition("?")
        params = dict(
            item.split("=", 1) for item in query.split("&") if "=" in item and item
        )

        color = params.get("color", "2A78EC").lstrip("#")
        # 只接受 6 位 / 8 位十六进制，别的当非法参数忽略（不要把它拼进 SVG）
        if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", color):
            color = "2A78EC"

        try:
            width = int(params.get("w", DEFAULT_SIZE))
        except ValueError:
            width = DEFAULT_SIZE
        width = max(8, min(width, MAX_SIZE))

        key = (name, color, width)
        cached = self._cache.get(key)
        if cached is not None:
            size.setWidth(cached.width())
            size.setHeight(cached.height())
            return cached

        source = self._svg_text(name)
        if source is None:
            # 画一张透明的空图并报出来 —— 静默返回空图会让人以为「布局坏了」
            print(f"[icons] 找不到图标：{name}（在 {self.icon_dir}）")
            blank = QImage(width, width, QImage.Format_ARGB32_Premultiplied)
            blank.fill(Qt.transparent)
            self._cache[key] = blank
            size.setWidth(width)
            size.setHeight(width)
            return blank

        # 换色 + 按目标宽度重设 width/height（viewBox 不变，所以是等比重绘）
        recolored = _CURRENT_COLOR_RE.sub(f"#{color}", source)
        recolored = re.sub(r'width="[^"]*"', f'width="{width}"', recolored, count=1)
        recolored = re.sub(r'height="[^"]*"', f'height="{width}"', recolored, count=1)

        renderer = QSvgRenderer(recolored.encode("utf-8"))
        image = QImage(width, width, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        if renderer.isValid():
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            renderer.render(painter)
            painter.end()

        self._cache[key] = image
        size.setWidth(width)
        size.setHeight(width)
        return image


def register_icon_provider(engine: QQmlEngine, icon_dir: Path | str = ICON_DIR) -> LucideIconProvider:
    """把图标源注册到 QML 引擎上。返回 provider，方便测试里查缓存。"""
    provider = LucideIconProvider(icon_dir)
    engine.addImageProvider("lucide", provider)
    return provider
