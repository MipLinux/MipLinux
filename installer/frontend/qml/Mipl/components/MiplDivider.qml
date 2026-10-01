// MiplDivider —— 08 §4.1「Divider（full-width / inset）」的组合件。
// 底座：纯 Rectangle（Qt 没有对应控件）。层级靠 outline-variant 描边，不用阴影（08 §3.5）。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import Mipl 1.0

Rectangle {
    id: control

    // MD3 inset 分隔线：左侧留一个 l 档（08 §3.4 的内边距档）
    property bool inset: false
    property bool vertical: false
    // 竖线要两端留白时置 true（MD3 divider 的上下内缩）
    property bool verticalInset: false

    color: "transparent"
    implicitWidth: vertical ? 1 : MiplSpace.page * 6
    implicitHeight: vertical ? MiplSpace.page * 3 : 1

    Rectangle {
        visible: !control.vertical
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: control.inset ? MiplSpace.l : 0
        anchors.verticalCenter: parent.verticalCenter
        height: 1
        color: MiplColor.outlineVariant
    }

    Rectangle {
        visible: control.vertical
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: control.verticalInset ? MiplSpace.s : 0
        anchors.bottomMargin: control.verticalInset ? MiplSpace.s : 0
        anchors.horizontalCenter: parent.horizontalCenter
        width: 1
        color: MiplColor.outlineVariant
    }
}
