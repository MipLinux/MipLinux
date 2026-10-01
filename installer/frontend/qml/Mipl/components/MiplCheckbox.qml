// MiplCheckbox —— 08 §4.1「Checkbox / Radio」的覆写件（Checkbox）。
// 底座：Qt Quick Controls Basic 的 CheckBox（checked / 三态以外的键盘与无障碍语义沿用）。
// 勾不用字体字形：Live 的 noto-fonts 覆盖不到 U+2713，回退会出豆腐块 —— 用两根圆头短杆画。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

CheckBox {
    id: control

    // MD3 勾选框 18px：4px 网格外的固定档，取 l + 2，主体随界面层缩放
    readonly property real boxSize: MiplSpace.l + 2

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
        implicitWidth: control.boxSize
        implicitHeight: control.boxSize
        // 设计格是 18px，u 只是比例（不是 MiplScale.factor 的倍数）
        readonly property real u: width / 18

        Rectangle {
            id: box
            anchors.fill: parent
            radius: MiplShape.extraSmall
            color: control.checked ? (control.enabled ? MiplColor.primary : MiplColor.onSurfaceVariant) : "transparent"
            border.width: 2
            border.color: !control.enabled ? MiplColor.onSurfaceVariant
                        : control.checked ? MiplColor.primary
                        : control.hovered || control.activeFocus ? MiplColor.onSurface
                        : MiplColor.onSurfaceVariant

            // 状态层：hover 0.08 / focus 0.12 / pressed 0.12（08 §3.5）
            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: control.checked ? MiplColor.onPrimary : MiplColor.onSurface
                opacity: !control.enabled ? 0
                       : control.down ? 0.12
                       : control.hovered ? 0.08
                       : control.activeFocus ? 0.12 : 0
                Behavior on opacity {
                    NumberAnimation {
                        duration: MiplMotion.short2
                        easing.type: Easing.Bezier
                        easing.bezierCurve: MiplMotion.easingStandard
                    }
                }
            }
        }

        // 勾：短臂 "\" + 长臂 "/"
        Item {
            anchors.fill: parent
            visible: control.checked

            Rectangle {
                width: 2 * parent.parent.u
                height: 4.3 * parent.parent.u
                radius: width / 2
                x: 6 * parent.parent.u - width / 2
                y: 11 * parent.parent.u - height / 2
                rotation: -45
                color: MiplColor.onPrimary
            }
            Rectangle {
                width: 2 * parent.parent.u
                height: 8.9 * parent.parent.u
                radius: width / 2
                x: 10.5 * parent.parent.u - width / 2
                y: 9.25 * parent.parent.u - height / 2
                rotation: 45
                color: MiplColor.onPrimary
            }
        }

        // 焦点环：2px primary（08 §3.8）
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: MiplShape.extraSmall + 3
            color: "transparent"
            visible: control.activeFocus
            border.width: 2
            border.color: MiplColor.primary
        }
    }
}
