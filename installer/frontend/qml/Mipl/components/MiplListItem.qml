// MiplListItem —— 08 §4.1「List item（1–3 行）」的覆写件。
// 底座：Qt Quick Controls Basic 的 ItemDelegate（点击、键盘、无障碍语义沿用）。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

ItemDelegate {
    id: control

    property string secondaryText: ""
    property string tertiaryText: ""
    property string leadingText: ""
    property string trailingText: ""
    // 放进卡片时用 MiplShape.medium 之类；默认全宽直边
    property real cornerRadius: 0

    readonly property int lineCount: 1 + (secondaryText.length > 0 ? 1 : 0) + (tertiaryText.length > 0 ? 1 : 0)
    // MD3 列表项高度 56 / 72 / 88 = page+s / page+xl / page+xl+l
    readonly property real minHeight: lineCount === 1 ? MiplSpace.page + MiplSpace.s
                                     : lineCount === 2 ? MiplSpace.page + MiplSpace.xl
                                     : MiplSpace.page + MiplSpace.xl + MiplSpace.l

    implicitHeight: Math.max(minHeight, contentItem.implicitHeight + topPadding + bottomPadding)
    implicitWidth: MiplSpace.page * 6
    padding: MiplSpace.l
    spacing: MiplSpace.l
    // QQC 的 ItemDelegate 默认不进 Tab 焦点链；列表项是可选控件，必须 Tab 可达（08 §3.8）
    activeFocusOnTab: true

    // 08 §3.8：Enter 触发主动作（选中该项）。QQC 只处理 Space
    function _activateKey() {
        if (control.enabled)
            control.clicked()
    }
    Keys.onReturnPressed: control._activateKey()
    Keys.onEnterPressed: control._activateKey()

    contentItem: Item {
        implicitWidth: MiplSpace.page * 4
        implicitHeight: textColumn.implicitHeight

        Text {
            id: leadingText
            visible: control.leadingText.length > 0
            text: control.leadingText
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            color: control.enabled ? MiplColor.onSurfaceVariant : MiplColor.onSurfaceVariant
            font.family: MiplType.family
            font.pixelSize: MiplSpace.xl
            textFormat: Text.PlainText
        }

        Column {
            id: textColumn
            anchors.left: leadingText.visible ? leadingText.right : parent.left
            anchors.leftMargin: leadingText.visible ? control.spacing : 0
            anchors.right: trailingText.visible ? trailingText.left : parent.right
            anchors.rightMargin: trailingText.visible ? control.spacing : 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0

            Text {
                width: parent.width
                text: control.text
                color: control.enabled ? MiplColor.onSurface : MiplColor.onSurfaceVariant
                font.family: MiplType.family
                font.pixelSize: MiplType.bodyLarge.size
                font.weight: MiplType.bodyLarge.weight
                font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                            : MiplType.bodyLarge.tracking
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }

            Text {
                width: parent.width
                visible: control.secondaryText.length > 0
                text: control.secondaryText
                color: MiplColor.onSurfaceVariant
                font.family: MiplType.family
                font.pixelSize: MiplType.bodyMedium.size
                font.letterSpacing: MiplType.cjkTracking
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }

            Text {
                width: parent.width
                visible: control.tertiaryText.length > 0
                text: control.tertiaryText
                color: MiplColor.onSurfaceVariant
                font.family: MiplType.family
                font.pixelSize: MiplType.bodySmall.size
                font.letterSpacing: MiplType.cjkTracking
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
        }

        Text {
            id: trailingText
            visible: control.trailingText.length > 0
            text: control.trailingText
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            color: MiplColor.onSurfaceVariant
            font.family: MiplType.family
            font.pixelSize: MiplType.bodyMedium.size
            textFormat: Text.PlainText
        }
    }

    background: Rectangle {
        color: "transparent"
        radius: control.cornerRadius

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.highlighted ? MiplColor.secondaryContainer : MiplColor.onSurface
            opacity: !control.enabled ? 0
                   : control.highlighted ? (control.down ? 0.16 : 0.12)
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

        // 焦点环：2px primary（08 §3.8）
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            visible: control.activeFocus
            border.width: 2
            border.color: MiplColor.primary
        }
    }
}
