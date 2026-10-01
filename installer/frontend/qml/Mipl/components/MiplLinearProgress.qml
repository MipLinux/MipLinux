// MiplLinearProgress —— 08 §4.1「Linear progress indicator（determinate / indeterminate）」的覆写件。
// 底座：Qt Quick Controls Basic 的 ProgressBar（value / from / to / position / indeterminate 都沿用）。
// 步骤感：08 §4.1 的注 —— MD3 没有 stepper，不自造；用本组件 + 「第 N / M 步」文字表达。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

ProgressBar {
    id: control

    property int step: 0
    property int stepCount: 0
    property bool showStepLabel: false

    readonly property string stepText: control.stepCount > 0
                                       ? qsTr("第 %1 / %2 步").arg(control.step).arg(control.stepCount)
                                       : ""

    padding: 0
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0

    // Basic 默认背景是一根 palette 色的条，深色底上会是一条白杠；轨道画在 contentItem 里，这里留空
    background: Item {}

    // 首帧零动效（08 §3.6）：循环动效等第一帧之后再挂上
    property bool _animStarted: false

    Timer {
        interval: 16
        repeat: false
        running: control.indeterminate
        onTriggered: control._animStarted = true
    }

    contentItem: Item {
        implicitWidth: MiplSpace.page * 4
        implicitHeight: (labelText.visible ? labelText.implicitHeight + MiplSpace.s : 0) + MiplSpace.xs

        Text {
            id: labelText
            visible: control.showStepLabel && control.stepText.length > 0
            text: control.stepText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            color: MiplColor.onSurfaceVariant
            font.family: MiplType.family
            font.pixelSize: MiplType.bodySmall.size
            font.letterSpacing: MiplType.cjkTracking
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        Rectangle {
            id: track
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: labelText.visible ? labelText.bottom : parent.top
            anchors.topMargin: labelText.visible ? MiplSpace.s : 0
            height: MiplSpace.xs
            radius: height / 2
            color: MiplColor.surfaceContainerHighest
            border.width: 1
            border.color: MiplColor.outlineVariant
            clip: true

            // 确定态：活动条按 position 伸缩
            Rectangle {
                visible: !control.indeterminate
                width: track.width * Math.max(0, Math.min(1, control.position))
                height: parent.height
                radius: parent.radius
                color: control.enabled ? MiplColor.primary : MiplColor.onSurfaceVariant
            }

            // 不确定态：一条短杆循环扫过
            Rectangle {
                id: indeterminateBar
                visible: control.indeterminate
                width: track.width * 0.35
                height: parent.height
                radius: parent.radius
                color: control.enabled ? MiplColor.primary : MiplColor.onSurfaceVariant
            }
        }
    }

    SequentialAnimation {
        running: control.indeterminate && control._animStarted
        loops: Animation.Infinite

        NumberAnimation {
            target: indeterminateBar
            property: "x"
            from: -indeterminateBar.width
            to: track.width
            duration: MiplMotion.extraLong4
            easing.type: Easing.Bezier
            easing.bezierCurve: MiplMotion.easingStandard
        }
    }
}
