// 细滚动条：4px 圆头 —— 滚动条的样式**全项目只有这一份**。
//
// 为什么不用 QtQuick Controls 的 `ScrollBar`：它的粗细、圆角、颜色都由平台样式
// 决定，同一份界面在装了不同主题的机器上长得不一样；而且 kiosk 全屏下系统滚动条
// 又宽又显眼，与这套「克制的仪器感」不是一个调子。所以自己画。
//
// 用法（**必须与 Flickable 同级**，自己把轨道摆到 Flickable 上）：
//
//     Flickable { id: flick; … }
//     ScrollBar {
//         flickable: flick
//         x: …;  y: flick.y;  height: flick.height
//     }
//
// 它自己管三件事：不需要滚时整根隐藏、条长按内容比例、按 contentY 定位。
// 拖动与滚轮都由 Flickable 负责，这里只处理「抓条拖」。

import QtQuick
import "../theme"

Item {
    id: root

    /// 要跟随的 Flickable（必须给）
    property var flickable: null

    /// 内容比视口高才出现 —— 放得下时整根不画，也不占事件
    readonly property bool scrollable: flickable !== null
                                       && flickable.contentHeight > flickable.height + 1
    /// 可滚动的距离（分母）；为 0 时下面所有除法都要走 Math.max
    readonly property real span: flickable === null
                                 ? 1
                                 : Math.max(1, flickable.contentHeight - flickable.height)
    /// 条能走的距离
    readonly property real track: Math.max(1, root.height - bar.height)

    width: 4
    visible: scrollable

    Rectangle {
        id: bar

        width: root.width
        radius: width / 2
        // 条长按「视口 / 内容」的比例；太短抓不住，所以有 32px 下限
        height: root.flickable === null
                ? 32
                : Math.max(32, root.flickable.height * root.flickable.height
                               / Math.max(1, root.flickable.contentHeight))
        y: root.flickable === null ? 0 : root.track * (root.flickable.contentY / root.span)
        color: area.pressed || area.containsMouse ? Tokens.accentDecor : Tokens.borderField

        MouseArea {
            id: area

            anchors.fill: parent
            // 4px 太细抓不住：命中区向两侧各放 8px。位移量不受这层 margin 影响 ——
            // 按下时记的是基准点，之后只用到 mouse.y 的**差值**。
            anchors.leftMargin: -Tokens.s1
            anchors.rightMargin: -Tokens.s1
            cursorShape: Qt.PointingHandCursor
            // 不让 Flickable 把这串拖动当成内容拖动抢走
            preventStealing: true

            property real pressY: 0
            property real pressContentY: 0

            onPressed: (mouse) => {
                pressY = mouse.y;
                pressContentY = root.flickable.contentY;
            }
            onPositionChanged: (mouse) => {
                if (!pressed || root.flickable === null)
                    return;
                root.flickable.contentY = Math.min(root.span, Math.max(0,
                    pressContentY + (mouse.y - pressY) * root.span / root.track));
            }
        }
    }
}
