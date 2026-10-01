// MiplSwitch —— 08 §4.1「Switch」的覆写件。
// 底座：Qt Quick Controls Basic 的 Switch（checked / 键盘 Space 切换 / 无障碍语义都沿用）。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

Switch {
    id: control

    // MD3 轨道 52×32 = (page + xs) × xxl；拇指 24 / 选中 28 —— 全用 token 组合，跟着界面层缩放走
    readonly property real trackWidth: MiplSpace.page + MiplSpace.xs
    readonly property real trackHeight: MiplSpace.xxl
    readonly property real thumbSize: control.checked ? MiplSpace.xl + MiplSpace.xs : MiplSpace.xl
    readonly property real thumbInset: (trackHeight - thumbSize) / 2

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
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        leftPadding: control.indicator ? control.indicator.width + control.spacing : 0
    }

    indicator: Item {
        implicitWidth: control.trackWidth
        implicitHeight: control.trackHeight
        x: control.text ? control.leftPadding : control.leftPadding

        Rectangle {
            id: track
            anchors.fill: parent
            radius: height / 2
            color: control.checked
                   ? (control.enabled ? MiplColor.primary : MiplColor.onSurfaceVariant)
                   : (control.enabled ? MiplColor.surfaceContainerHighest : MiplColor.surfaceContainer)
            border.width: control.checked ? 0 : 2
            border.color: control.enabled ? MiplColor.outline : MiplColor.onSurfaceVariant

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
                        duration: MiplMotion.short2 * MiplMotion.motionScale
                        easing.type: Easing.Bezier
                        easing.bezierCurve: MiplMotion.easingStandard
                    }
                }
            }
        }

        Rectangle {
            id: thumb
            width: control.thumbSize
            height: control.thumbSize
            radius: height / 2
            y: (control.trackHeight - height) / 2
            x: control.checked ? control.trackWidth - width - control.thumbInset : control.thumbInset
            color: control.checked
                   ? (control.enabled ? MiplColor.onPrimary : MiplColor.surface)
                   : (control.enabled ? MiplColor.outline : MiplColor.onSurfaceVariant)

            Behavior on x {
                NumberAnimation {
                    duration: MiplMotion.short4 * MiplMotion.motionScale
                    easing.type: Easing.Bezier
                    easing.bezierCurve: MiplMotion.easingEmphasizedDecelerate
                }
            }
            Behavior on width {
                NumberAnimation {
                    duration: MiplMotion.short4 * MiplMotion.motionScale
                    easing.type: Easing.Bezier
                    easing.bezierCurve: MiplMotion.easingEmphasizedDecelerate
                }
            }
        }

        // 焦点环：2px primary（08 §3.8）
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
