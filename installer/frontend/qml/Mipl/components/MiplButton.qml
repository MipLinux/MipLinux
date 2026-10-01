// MiplButton —— 08 §4.1「Button（filled / tonal / outlined / text）」的覆写件。
// 底座：Qt Quick Controls Basic（08 §5 路线 B）。布局、焦点、键盘与无障碍语义由 AbstractButton 提供。
// 纪律：只取 Mipl* token（外部尺寸用 MiplSpace 的组合表达，好跟着界面层缩放走）；
//       不乘 MiplScale.factor、不碰 devicePixelRatio —— token 单例内部已经乘过一次。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

Button {
    id: control

    enum Variant { Filled, Tonal, Outlined, Text }

    property int variant: MiplButton.Filled

    readonly property color contentColor: {
        switch (variant) {
        case MiplButton.Tonal:
            return MiplColor.onSecondaryContainer
        case MiplButton.Outlined:
        case MiplButton.Text:
            return MiplColor.primary
        default:
            return MiplColor.onPrimary
        }
    }

    readonly property color containerColor: {
        switch (variant) {
        case MiplButton.Tonal:
            return MiplColor.secondaryContainer
        case MiplButton.Outlined:
        case MiplButton.Text:
            return "transparent"
        default:
            return MiplColor.primary
        }
    }

    // 禁用态：MD3 是 on-surface 12% 容器 + 38% 内容
    readonly property color disabledContentColor: Qt.rgba(MiplColor.onSurface.r, MiplColor.onSurface.g,
                                                          MiplColor.onSurface.b, 0.38)
    readonly property color disabledContainerColor: variant === MiplButton.Outlined || variant === MiplButton.Text
                                                    ? "transparent"
                                                    : Qt.rgba(MiplColor.onSurface.r, MiplColor.onSurface.g,
                                                              MiplColor.onSurface.b, 0.12)

    // 中文串字距归零（08 §3.2 的 CJK 追加规则）
    readonly property bool cjkText: /[\u3400-\u9fff\uf900-\ufaff]/.test(text)

    // 08 §3.8：Enter 触发主动作。QQC Basic 的 AbstractButton 只处理 Space，
    // Return / 小键盘 Enter 要自己补（实测：不加时按钮有焦点、按 Enter 也毫无反应）
    function _activateKey() {
        if (control.enabled)
            control.clicked()
    }
    Keys.onReturnPressed: control._activateKey()
    Keys.onEnterPressed: control._activateKey()

    // MD3 最小可点高度 48dp（08 §3.4 的 page 档），随界面层缩放。
    // 走 control.contentItem：裸写 contentItem 在独立实例化时解析不到，会报 ReferenceError
    readonly property real contentHeight: control.contentItem ? control.contentItem.implicitHeight : 0
    implicitHeight: Math.max(MiplSpace.page, contentHeight + MiplSpace.l)
    leftPadding: MiplSpace.xl
    rightPadding: MiplSpace.xl
    topPadding: MiplSpace.s
    bottomPadding: MiplSpace.s

    font.family: MiplType.family
    font.pixelSize: MiplType.labelLarge.size
    font.weight: MiplType.labelLarge.weight
    font.letterSpacing: control.cjkText ? MiplType.cjkTracking : MiplType.labelLarge.tracking

    Accessible.role: Accessible.Button
    Accessible.name: control.text

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? control.contentColor : control.disabledContentColor
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        // 长文案换行，不用省略号（08 §3.2）
        wrapMode: Text.WordWrap
        width: Math.min(implicitWidth, control.availableWidth)
    }

    background: Rectangle {
        implicitWidth: MiplSpace.page + MiplSpace.xl
        implicitHeight: MiplSpace.page
        // corner-full：按 08 §3.3 取控件高度的一半
        radius: control.height / 2
        color: control.enabled ? control.containerColor : control.disabledContainerColor
        border.width: control.variant === MiplButton.Outlined ? 1 : 0
        border.color: control.enabled ? MiplColor.outline
                                      : Qt.rgba(MiplColor.onSurface.r, MiplColor.onSurface.g, MiplColor.onSurface.b, 0.12)

        // 状态层：hover 0.08 / focus 0.12 / pressed 0.12（08 §3.5）
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.variant === MiplButton.Filled ? MiplColor.onPrimary
                 : control.variant === MiplButton.Tonal ? MiplColor.onSecondaryContainer
                 : MiplColor.primary
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

        // 焦点环：2px primary 外描边（08 §3.8），画在控件外侧以免挤压文案
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
