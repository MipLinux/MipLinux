// 图标：按名字取 Lucide 图标，染成需要的颜色。
//
// **图标集是 Lucide**（ISC；其中一批派生自 Feather，MIT），许可文件在
// `installer/frontend/icons/lucide/LICENSE`。
//
// **仓库里只放用到的那些**（当前 20 个，84 KB）—— 全量 1854 个是 7.3 MB，
// 塞进仓库就是把发行版的一份图标主题背在身上（评审口径，2026-09-25）。
// 要加一个新图标：从 https://lucide.dev/icons 拿那**一个** `.svg`，
// 放进 `installer/frontend/icons/lucide/`，然后按下面那样写名字即可。
// 少一个图标不会静默：`bridge/icons.py` 会打出「找不到图标：X」并画一张空图。
//
//     Icon { name: "lock";     size: 15; color: Tokens.textMuted }
//     Icon { name: "wifi-off"; size: 48; color: Tokens.textFaint }
//
// 取名字：https://lucide.dev/icons
// 或者 `ls installer/frontend/icons/lucide/ | grep 关键词`
//
// ── 为什么过一层 Python，而不是 `Image { source: "…/lock.svg" }` ────────────
// Lucide 的 SVG 全写 `stroke="currentColor"`，而 **Qt 的 SVG 渲染器不认这个关键字**，
// 实测渲染出来是纯黑，`Image.color` 也染不了它。所以由 `bridge/icons.py` 里的
// `QQuickImageProvider` 在渲染前把 `currentColor` 换成真实色值。
// 顺带做到按需渲染，以及按 (图标, 颜色, 尺寸) 缓存。
//
// ── 为什么不用 emoji / ✓ ✗ ▾ 这类字符 ───────────────────────────────────────
// 那是**字体**的产物：命中哪个字形、什么颜色、什么粗细都不由我们决定，
// 而且 Live 里有 `noto-fonts-emoji`、装后系统不一定有 —— 同一个界面在两处不一样。

import QtQuick
import "../theme"

Item {
    id: icon

    /// Lucide 图标名，例如 lock / check / x / chevron-down / ethernet-port / wifi
    property string name: ""
    /// 显示边长（正方形）
    property int size: 16
    property color color: Tokens.textMuted

    implicitWidth: size
    implicitHeight: size

    /// 渲染分辨率留 HiDPI 余量 —— 位图被放大才不糊
    readonly property int _px: Math.min(512, Math.max(16, Math.round(size * 3)))

    Image {
        anchors.fill: parent
        // 颜色转成不带 # 的十六进制：URL 里 # 会截断查询串
        source: icon.name === ""
                ? ""
                : "image://lucide/" + icon.name
                  + "?color=" + icon.color.toString().slice(1)
                  + "&w=" + icon._px
        sourceSize.width: icon._px
        sourceSize.height: icon._px
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        visible: icon.name !== ""
    }
}
