// MiplTopAppBar —— 08 §4.1「Top app bar（small）」的自建件：页面标题 + 返回 + 右侧动作位。
// 底座：Rectangle + MiplIconButton。层级用 surface + 1px outline-variant 底边（08 §3.5），不用阴影。
// 用法：右侧动作塞进默认属性（会落进 actionsRow），例如主题切换按钮、缩放菜单。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

Rectangle {
    id: control

    property string title: ""
    property bool showBack: true
    // MD3 small app bar 高 64 = page + l
    readonly property real barHeight: MiplSpace.page + MiplSpace.l

    signal backClicked()

    default property alias actionsData: actionsRow.data

    implicitHeight: barHeight
    implicitWidth: MiplSpace.page * 8
    color: MiplColor.surface

    // 底边描边：app bar 与内容之间的层级
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: MiplColor.outlineVariant
    }

    MiplIconButton {
        id: backButton

        visible: control.showBack
        iconName: "back"
        tip: qsTr("返回")
        anchors.left: parent.left
        anchors.leftMargin: MiplSpace.xs
        anchors.verticalCenter: parent.verticalCenter

        onClicked: control.backClicked()
    }

    Text {
        id: titleText

        anchors.left: control.showBack ? backButton.right : parent.left
        anchors.leftMargin: control.showBack ? MiplSpace.s : MiplSpace.l
        anchors.right: actionsRow.left
        anchors.rightMargin: MiplSpace.s
        anchors.verticalCenter: parent.verticalCenter
        text: control.title
        color: MiplColor.onSurface
        font.family: MiplType.family
        font.pixelSize: MiplType.titleLarge.size
        font.weight: MiplType.titleLarge.weight
        font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                    : MiplType.titleLarge.tracking
        elide: Text.ElideRight
        textFormat: Text.PlainText
    }

    Row {
        id: actionsRow
        anchors.right: parent.right
        anchors.rightMargin: MiplSpace.s
        anchors.verticalCenter: parent.verticalCenter
        spacing: MiplSpace.xs
    }
}
