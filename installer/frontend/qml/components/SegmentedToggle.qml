// 分段切换：欢迎页的中 / EN，以及需要「非此即彼」的少量场合。
//
// 用它而不是下拉框是因为选项少（2–3 个）、且切换要立刻可见 ——
// 少一次点击、少一个需要展开的控件。

import QtQuick
import "../theme"

Rectangle {
    id: toggle

    //: 显示文案数组，例如 ["中文", "EN"]
    property var options: []
    property int currentIndex: 0
    signal activated(int index)

    implicitWidth: row.implicitWidth + 4
    implicitHeight: 40
    radius: Tokens.rPill
    color: Tokens.subtleBg
    border.width: 1
    border.color: Tokens.border

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 2

        Repeater {
            model: toggle.options
            delegate: Rectangle {
                id: segment
                required property int index
                required property string modelData

                width: label.implicitWidth + Tokens.s3
                height: 34
                radius: Tokens.rPill
                color: segment.index === toggle.currentIndex ? Tokens.cardBg : "transparent"
                border.width: segment.index === toggle.currentIndex ? 1 : 0
                border.color: Tokens.accentBorder

                Text {
                    id: label
                    anchors.centerIn: parent
                    text: segment.modelData
                    font: segment.index === toggle.currentIndex ? Tokens.bodyStrong : Tokens.body
                    color: segment.index === toggle.currentIndex ? Tokens.accentAction : Tokens.textMuted
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: toggle.activated(segment.index)
                }
            }
        }
    }
}
