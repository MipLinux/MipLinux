// MiplSnackbar —— 08 §4.1「Snackbar」的自建件：非阻塞提示 + 一个可选动作。
// 底座：Qt Quick Controls 的 Popup（不遮罩、不抢焦点；Esc 关掉只算返回，不是破坏性动作）。
// 配色：MD3 用 inverse-surface / inverse-on-surface / inverse-primary。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

Popup {
    id: control

    property string message: ""
    property string actionText: ""
    // 展示时长（ms）；0 = 不自动关闭
    property int autoHideDuration: 4000
    signal actionTriggered()

    function show(msg) {
        control.message = msg
        control.open()
    }

    // 浮在父项（页面 / 窗口内容）底部，两侧留页面安全边距
    modal: false
    dim: false
    focus: false
    closePolicy: Popup.CloseOnEscape
    padding: MiplSpace.l
    leftPadding: MiplSpace.l
    rightPadding: MiplSpace.s
    topPadding: MiplSpace.m
    bottomPadding: MiplSpace.m
    // 浮在父项（页面 / 窗口内容）底部，两侧留页面安全边距。
    // 不用 Popup 的 anchors（它的锚点组只有 centerIn / fill），直接给 x / y。
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? Math.round(parent.height - height - MiplSpace.l) : 0
    width: Math.min(implicitWidth, parent ? parent.width - MiplSpace.page : implicitWidth)

    enter: Transition {
        NumberAnimation {
            property: "opacity"
            from: 0
            to: 1
            duration: MiplMotion.short4 * MiplMotion.motionScale
            easing.type: Easing.Bezier
            easing.bezierCurve: MiplMotion.easingStandardDecelerate
        }
    }
    exit: Transition {
        NumberAnimation {
            property: "opacity"
            from: 1
            to: 0
            duration: MiplMotion.short3 * MiplMotion.motionScale
            easing.type: Easing.Bezier
            easing.bezierCurve: MiplMotion.easingStandardAccelerate
        }
    }

    Timer {
        interval: control.autoHideDuration
        running: control.opened && control.autoHideDuration > 0
        onTriggered: control.close()
    }

    contentItem: Item {
        implicitWidth: Math.min(MiplSpace.page * 10,
                                messageText.implicitWidth + MiplSpace.xl
                                + (actionButton.visible ? actionButton.implicitWidth : 0))
        implicitHeight: Math.max(messageText.implicitHeight,
                                 actionButton.visible ? actionButton.implicitHeight : 0)

        Text {
            id: messageText
            anchors.left: parent.left
            anchors.right: actionButton.visible ? actionButton.left : parent.right
            anchors.rightMargin: actionButton.visible ? MiplSpace.s : 0
            anchors.verticalCenter: parent.verticalCenter
            text: control.message
            color: MiplColor.inverseOnSurface
            font.family: MiplType.family
            font.pixelSize: MiplType.bodyMedium.size
            font.letterSpacing: MiplType.cjkTracking
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        // 动作是文字按钮：MD3 snackbar 动作用 inverse-primary
        AbstractButton {
            id: actionButton

            visible: control.actionText.length > 0
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            implicitHeight: MiplSpace.page - MiplSpace.s
            implicitWidth: actionLabel.implicitWidth + MiplSpace.l * 2
            leftPadding: MiplSpace.l
            rightPadding: MiplSpace.l

            Accessible.role: Accessible.Button
            Accessible.name: control.actionText

            onClicked: {
                control.actionTriggered()
                control.close()
            }

            // 08 §3.8：Enter 触发动作（QQC Basic 只认 Space）
            Keys.onReturnPressed: actionButton.clicked()
            Keys.onEnterPressed: actionButton.clicked()

            contentItem: Text {
                id: actionLabel
                text: control.actionText
                anchors.centerIn: parent
                color: MiplColor.inversePrimary
                font.family: MiplType.family
                font.pixelSize: MiplType.labelLarge.size
                font.weight: MiplType.labelLarge.weight
                font.letterSpacing: MiplType.cjkTracking
                textFormat: Text.PlainText
            }

            background: Rectangle {
                radius: height / 2
                color: "transparent"

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: MiplColor.inversePrimary
                    opacity: actionButton.down ? 0.12 : actionButton.hovered ? 0.08 : actionButton.activeFocus ? 0.12 : 0
                    Behavior on opacity {
                        NumberAnimation {
                            duration: MiplMotion.short2 * MiplMotion.motionScale
                            easing.type: Easing.Bezier
                            easing.bezierCurve: MiplMotion.easingStandard
                        }
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -3
                    radius: parent.radius + 3
                    color: "transparent"
                    visible: actionButton.activeFocus
                    border.width: 2
                    border.color: MiplColor.inversePrimary
                }
            }
        }
    }

    background: Rectangle {
        color: MiplColor.inverseSurface
        radius: MiplShape.extraSmall
        border.width: 1
        border.color: MiplColor.outlineVariant
    }
}
