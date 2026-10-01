// MiplBadge —— 08 §4.1「Badge（small）」的自建件。
// 底座：纯 Rectangle（Qt 没有对应控件）。挂在图标/标题角上时由使用方锚定。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import Mipl 1.0

Rectangle {
    id: control

    property string text: ""
    // dot = 只有圆点，不显示数字
    property bool dot: false

    // 小徽标：16 = MiplSpace.l；有数字时按内容加宽，最小仍是圆的
    implicitWidth: control.dot ? MiplSpace.l
                               : Math.max(MiplSpace.l, label.implicitWidth + MiplSpace.s)
    implicitHeight: MiplSpace.l
    radius: height / 2
    color: MiplColor.error

    Accessible.role: Accessible.StaticText
    Accessible.name: control.dot ? qsTr("有新内容") : control.text

    Text {
        id: label
        anchors.centerIn: parent
        visible: !control.dot && control.text.length > 0
        text: control.text
        color: MiplColor.onError
        font.family: MiplType.family
        font.pixelSize: MiplType.labelSmall.size
        font.weight: MiplType.labelSmall.weight
        textFormat: Text.PlainText
    }
}
