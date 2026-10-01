// MiplTextField —— 08 §4.1「Text field（filled / outlined）」的覆写件。
// 底座：Qt Quick Controls Basic 的 TextField（text / echoMode / 输入法 / 键盘 / 无障碍语义都沿用）。
// 浮动标签与 supporting text 画在 background 里 —— 这样不用把 TextField 包成另一个控件，
// 使用方仍然拿得到 TextField 的全部 API。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

TextField {
    id: control

    enum Variant { Filled, Outlined }

    property int variant: MiplTextField.Filled
    property string label: ""
    property string supportingText: ""
    property bool error: false

    readonly property bool floatingLabel: control.activeFocus || control.displayText.length > 0
    readonly property color accentColor: control.error ? MiplColor.error : MiplColor.primary
    readonly property color supportingColor: control.error ? MiplColor.error : MiplColor.onSurfaceVariant

    // MD3 filled / outlined 高度 56 = page + s；另外给输入行留足一行 bodyLarge 的行高 ——
    // QQC 的 TextInput implicitHeight 偏小，只按它算会让输入文字和浮动标签挤在一起。
    // 走 control.contentItem：裸写 contentItem 在独立实例化时解析不到，会报 ReferenceError
    readonly property real inputHeight: Math.max(control.contentItem ? control.contentItem.implicitHeight : 0,
                                                MiplType.bodyLarge.lineHeight)
    implicitHeight: Math.max(MiplSpace.page + MiplSpace.s, inputHeight + topPadding + bottomPadding)
    implicitWidth: MiplSpace.page * 5

    topPadding: control.label.length > 0
                ? (control.variant === MiplTextField.Outlined ? MiplSpace.l : MiplSpace.xl)
                : MiplSpace.m
    bottomPadding: control.supportingText.length > 0 ? MiplSpace.xl : MiplSpace.m

    font.family: MiplType.family
    font.pixelSize: MiplType.bodyLarge.size
    font.weight: MiplType.bodyLarge.weight
    font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(control.text) ? MiplType.cjkTracking
                                                                         : MiplType.bodyLarge.tracking
    color: control.enabled ? MiplColor.onSurface : MiplColor.onSurfaceVariant
    placeholderTextColor: MiplColor.onSurfaceVariant
    selectionColor: MiplColor.primary
    selectedTextColor: MiplColor.onPrimary
    selectByMouse: true

    Accessible.role: Accessible.EditableText
    Accessible.name: control.label.length > 0 ? control.label : control.placeholderText

    background: Rectangle {
        id: bg

        radius: MiplShape.extraSmall
        color: control.variant === MiplTextField.Filled
               ? (control.enabled ? MiplColor.surfaceContainerHighest : MiplColor.surfaceContainer)
               : "transparent"
        border.width: control.variant === MiplTextField.Outlined ? 1 : 0
        border.color: control.error ? MiplColor.error
                    : control.activeFocus ? MiplColor.primary
                    : MiplColor.outline

        // filled 的底部主色线（08 §3.1 的 primary / error）
        Rectangle {
            visible: control.variant === MiplTextField.Filled
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: control.error ? MiplColor.error
                 : control.activeFocus ? MiplColor.primary
                 : MiplColor.onSurfaceVariant
        }

        // 浮动标签：filled 在框内上浮；outlined 骑在描边上（底下垫一块页面底色把描边断开）
        Text {
            id: labelText

            visible: control.label.length > 0
            text: control.label
            x: MiplSpace.l
            y: control.variant === MiplTextField.Outlined
               ? (control.floatingLabel ? -(height / 2 + 1) : (bg.height - height) / 2)
               : (control.floatingLabel ? MiplSpace.s : (bg.height - height) / 2)
            color: control.error ? MiplColor.error
                 : control.activeFocus ? MiplColor.primary
                 : MiplColor.onSurfaceVariant
            font.family: MiplType.family
            font.pixelSize: control.floatingLabel ? MiplType.bodySmall.size : MiplType.bodyLarge.size
            font.weight: MiplType.bodyLarge.weight
            font.letterSpacing: MiplType.cjkTracking
            textFormat: Text.PlainText

            Behavior on y {
                NumberAnimation {
                    duration: MiplMotion.short3
                    easing.type: Easing.Bezier
                    easing.bezierCurve: MiplMotion.easingStandardDecelerate
                }
            }
            Behavior on font.pixelSize {
                NumberAnimation {
                    duration: MiplMotion.short3
                    easing.type: Easing.Bezier
                    easing.bezierCurve: MiplMotion.easingStandardDecelerate
                }
            }

            Rectangle {
                visible: control.variant === MiplTextField.Outlined && control.floatingLabel
                anchors.fill: parent
                anchors.leftMargin: -MiplSpace.xs
                anchors.rightMargin: -MiplSpace.xs
                color: MiplColor.surface
                z: -1
            }
        }

        // supporting text（错误态也走这里，颜色由 error 决定）
        Text {
            visible: control.supportingText.length > 0
            text: control.supportingText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: MiplSpace.l
            anchors.rightMargin: MiplSpace.l
            anchors.bottomMargin: MiplSpace.xs
            color: control.supportingColor
            font.family: MiplType.family
            font.pixelSize: MiplType.bodySmall.size
            font.letterSpacing: MiplType.cjkTracking
            textFormat: Text.PlainText
            elide: Text.ElideRight
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
