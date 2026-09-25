// P0 · 首屏加载态。
//
// 存在的唯一理由：[Issue #53](https://github.com/MipLinux/MipLinux/issues/53) 实测
// 「从图形出现到窗口画出来要 10 秒以上（黑屏 + 鼠标先出现）」。
// 那 10 秒不该是设计遗漏 —— 这一页让它是**有意设计的状态**，而不是一块黑屏。
//
// 根因不在本线，这里不试图修它。要点只有一条：
// **窗口一显示就画**，不等任何后端调用（不查网络、不列盘、不读配置）。

import QtQuick
import "../theme"

Window {
    id: loading
    width: 1280
    height: 800
    visible: true
    color: Tokens.pageBg

    property string message: "正在准备安装环境…"
    property url logoSource: Qt.resolvedUrl("../../assets/mipl-logo-hero.png")

    Column {
        anchors.centerIn: parent
        spacing: Tokens.s4

        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            source: loading.logoSource
            sourceSize.width: 112
            sourceSize.height: 112
            width: 112
            height: 112
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            // 只在启动时呼吸一次，不循环 —— 见 Tokens.qml 的动效约定
            opacity: 0
            NumberAnimation on opacity {
                from: 0
                to: 1
                duration: Tokens.motionNormal * 2
                easing.type: Easing.OutCubic
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: loading.message
            font: Tokens.body
            color: Tokens.textMuted
        }

        // 不确定态进度条：这根条**不表示任何百分比**，它只表示「在等」。
        // 用不确定态是诚实的 —— 我们确实不知道还要多久。
        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 240
            height: 4

            Rectangle {
                anchors.fill: parent
                radius: 2
                color: Tokens.accentTint
            }

            Rectangle {
                id: pulse
                width: 72
                height: 4
                radius: 2
                color: Tokens.accentDecor
                x: 0

                SequentialAnimation on x {
                    loops: Animation.Infinite
                    NumberAnimation {
                        from: 0
                        to: 240 - pulse.width
                        duration: 1100
                        easing.type: Easing.InOutQuad
                    }
                    NumberAnimation {
                        from: 240 - pulse.width
                        to: 0
                        duration: 1100
                        easing.type: Easing.InOutQuad
                    }
                }
            }
        }
    }
}
