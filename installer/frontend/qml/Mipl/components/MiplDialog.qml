// MiplDialog —— 08 §4.1「Dialog（basic）」的覆写件：标题 + 正文 + 两个文字动作。
// 底座：Qt Quick Controls Basic 的 Dialog（模态、Esc 关闭、焦点、无障碍语义沿用）。
// 键盘：打开时焦点落在主动作上 —— Enter 触发主动作；Esc 只做返回（08 §3.8，永不触发破坏性动作）。
// 边界：这是 basic dialog，不给自定义内容区；要塞任意内容请直接用 QQC Dialog 再改 skin。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

Dialog {
    id: control

    property string message: ""
    property string acceptText: qsTr("确定")
    property string dismissText: qsTr("取消")
    property bool acceptEnabled: true

    modal: true
    focus: true
    // 只有「返回」语义的关闭方式（08 §3.8）
    closePolicy: Popup.CloseOnEscape
    padding: MiplSpace.xl
    spacing: MiplSpace.l
    anchors.centerIn: parent
    // MD3 对话框宽 280–560：min 用 page*6，max 用 page*10；长正文靠 wrapMode 换行
    implicitWidth: Math.max(MiplSpace.page * 6, contentItem.implicitWidth + leftPadding + rightPadding)
    width: Math.min(implicitWidth, MiplSpace.page * 10)

    // 遮罩用 scrim（08 §3.1），透明度是 MD3 的固定档
    Overlay.modal: Rectangle {
        color: Qt.rgba(MiplColor.scrim.r, MiplColor.scrim.g, MiplColor.scrim.b, 0.32)
    }

    header: Text {
        visible: control.title.length > 0
        text: control.title
        color: MiplColor.onSurface
        font.family: MiplType.family
        font.pixelSize: MiplType.headlineSmall.size
        font.weight: MiplType.headlineSmall.weight
        font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                    : MiplType.headlineSmall.tracking
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }

    contentItem: Text {
        visible: control.message.length > 0
        text: control.message
        color: MiplColor.onSurfaceVariant
        font.family: MiplType.family
        font.pixelSize: MiplType.bodyMedium.size
        font.letterSpacing: MiplType.cjkTracking
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }

    footer: Item {
        implicitWidth: footerRow.implicitWidth
        implicitHeight: footerRow.implicitHeight

        Row {
            id: footerRow
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: MiplSpace.s

            MiplButton {
                visible: control.dismissText.length > 0
                text: control.dismissText
                variant: MiplButton.Text
                onClicked: control.reject()
            }

            MiplButton {
                id: acceptButton
                text: control.acceptText
                variant: MiplButton.Filled
                enabled: control.acceptEnabled
                onClicked: control.accept()
            }
        }
    }

    onOpened: acceptButton.forceActiveFocus()

    background: Rectangle {
        // MD3 对话框容器：surface-container-high（08 §3.5）+ extra-large 圆角（08 §3.3）
        color: MiplColor.surfaceContainerHigh
        radius: MiplShape.extraLarge
        border.width: 1
        border.color: MiplColor.outlineVariant
    }
}
