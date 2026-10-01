// MiplRadio —— 08 §4.1「Checkbox / Radio」的覆写件（Radio）。
// 底座：Qt Quick Controls Basic 的 RadioButton。互斥由使用方的 ButtonGroup 提供（同 QQC 语义）。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

RadioButton {
    id: control

    // MD3 单选圆 20px = l + xs（4px 网格内）
    readonly property real ringSize: MiplSpace.l + MiplSpace.xs
    readonly property real dotSize: MiplSpace.s + 2

    // 08 §3.8：Enter 与 Space 同义（QQC Basic 只处理 Space）
    function _activateKey() {
        if (control.enabled) {
            control.toggle()
            control.clicked()
        }
    }
    Keys.onReturnPressed: control._activateKey()
    Keys.onEnterPressed: control._activateKey()

    spacing: MiplSpace.l
    font.family: MiplType.family
    font.pixelSize: MiplType.bodyLarge.size
    font.weight: MiplType.bodyLarge.weight
    font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(control.text) ? MiplType.cjkTracking
                                                                        : MiplType.bodyLarge.tracking

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? MiplColor.onSurface : MiplColor.onSurfaceVariant
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        leftPadding: control.indicator ? control.indicator.width + control.spacing : 0
    }

    indicator: Item {
        implicitWidth: control.ringSize
        implicitHeight: control.ringSize

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: !control.enabled ? MiplColor.onSurfaceVariant
                        : control.checked ? MiplColor.primary
                        : control.hovered || control.activeFocus ? MiplColor.onSurface
                        : MiplColor.onSurfaceVariant
        }

        // 状态层只覆盖在圆环上，不铺满矩形
        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: control.checked ? MiplColor.primary : MiplColor.onSurface
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

        Rectangle {
            anchors.centerIn: parent
            width: control.dotSize
            height: control.dotSize
            radius: height / 2
            visible: control.checked
            color: control.enabled ? MiplColor.primary : MiplColor.onSurfaceVariant
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.height / 2 + 3
            color: "transparent"
            visible: control.activeFocus
            border.width: 2
            border.color: MiplColor.primary
        }
    }
}
