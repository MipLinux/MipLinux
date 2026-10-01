// MiplChip —— 08 §4.1「Chip（filter）」的自建件：可多选的标签式筛选。
// 底座：AbstractButton（checkable），checked 的最终归属交给使用方。
// 选中勾不用字体字形（Live 的 noto-fonts 覆盖不到 U+2713），用两根圆头短杆画。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

AbstractButton {
    id: control

    checkable: true
    // MD3 filter chip 高 32 = xxl
    readonly property real chipHeight: MiplSpace.xxl

    // 08 §3.8：Enter 与 Space 同义（选中/取消）。QQC Basic 只处理 Space
    function _activateKey() {
        if (control.enabled) {
            control.toggle()
            control.clicked()
        }
    }
    Keys.onReturnPressed: control._activateKey()
    Keys.onEnterPressed: control._activateKey()

    implicitHeight: chipHeight
    implicitWidth: Math.max(MiplSpace.page + MiplSpace.s, contentRow.implicitWidth + MiplSpace.l * 2)
    leftPadding: MiplSpace.l
    rightPadding: MiplSpace.l
    topPadding: 0
    bottomPadding: 0

    Accessible.role: Accessible.CheckBox
    Accessible.name: control.text
    Accessible.checked: control.checked

    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight

        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: MiplSpace.s

            // 选中勾：18 设计格的两根短杆
            Item {
                visible: control.checked
                width: MiplSpace.l
                height: MiplSpace.l
                anchors.verticalCenter: parent.verticalCenter
                readonly property real u: width / 18

                Rectangle {
                    width: 2 * parent.u
                    height: 4.3 * parent.u
                    radius: width / 2
                    x: 6 * parent.u - width / 2
                    y: 11 * parent.u - height / 2
                    rotation: -45
                    color: MiplColor.onSecondaryContainer
                }
                Rectangle {
                    width: 2 * parent.u
                    height: 8.9 * parent.u
                    radius: width / 2
                    x: 10.5 * parent.u - width / 2
                    y: 9.25 * parent.u - height / 2
                    rotation: 45
                    color: MiplColor.onSecondaryContainer
                }
            }

            Text {
                id: chipLabel
                anchors.verticalCenter: parent.verticalCenter
                text: control.text
                color: !control.enabled ? MiplColor.onSurfaceVariant
                     : control.checked ? MiplColor.onSecondaryContainer
                     : MiplColor.onSurfaceVariant
                font.family: MiplType.family
                font.pixelSize: MiplType.labelLarge.size
                font.weight: MiplType.labelLarge.weight
                font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                            : MiplType.labelLarge.tracking
                textFormat: Text.PlainText
            }
        }
    }

    background: Rectangle {
        radius: control.height / 2
        color: control.checked
               ? (control.enabled ? MiplColor.secondaryContainer : MiplColor.surfaceContainer)
               : "transparent"
        border.width: control.checked ? 0 : 1
        border.color: control.enabled ? MiplColor.outline : MiplColor.outlineVariant

        // 状态层：hover 0.08 / focus 0.12 / pressed 0.12（08 §3.5）
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.checked ? MiplColor.onSecondaryContainer : MiplColor.onSurface
            opacity: !control.enabled ? 0
                   : control.down ? 0.12
                   : control.hovered ? 0.08
                   : control.activeFocus ? 0.12 : 0
            Behavior on opacity {
                NumberAnimation {
                    duration: MiplMotion.short2 * MiplMotion.motionScale
                    easing.type: Easing.Bezier
                    easing.bezierCurve: MiplMotion.easingStandard
                }
            }
        }

        // 焦点环：2px primary 外描边（08 §3.8）
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            visible: control.activeFocus
            border.width: 2
            border.color: MiplColor.primary
        }
    }
}
