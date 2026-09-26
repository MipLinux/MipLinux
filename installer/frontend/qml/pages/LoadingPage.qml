// P0 · 首屏加载态。
//
// 存在的唯一理由：[Issue #53](https://github.com/MipLinux/MipLinux/issues/53) 实测
// 「从图形出现到窗口画出来要 10 秒以上（黑屏 + 鼠标先出现）」。
// 那 10 秒不该是设计遗漏 —— 这一页让它是**有意设计的状态**，而不是一块黑屏。
//
// 根因不在本线，这里不试图修它。要点只有一条：
// **窗口一显示就画**，不等任何后端调用（不查网络、不列盘、不读配置）。
//
// 根是 Item：整个流程只有一个 Window（`qml/Main.qml`），这一页是它里面的第一屏
// （cage 是单窗口 kiosk 合成器，多开顶层窗口不成立 —— 见 PageShell 文件头）。

import QtQuick
import "../theme"

Item {
    id: loading
    width: 1280
    height: 800

    property string message: "正在准备安装环境…"
    property url logoSource: Qt.resolvedUrl("../../assets/mipl-logo-hero.png")

    /// **先出图，后出字**（2026-09-26 实测）：Live 里 fontconfig 的第一次字体扫描
    /// 要 18 秒（见 `mipl-kiosk` 里的预热注释），而第一帧能不能提交决定了**黑屏什么
    /// 时候结束**。所以首帧只画 LOGO（不碰字体），下一帧再把文字显出来 ——
    /// 万一预热没跑完，那 18 秒也发生在「已经有画面」之后，而不是一片黑里。
    property bool showText: false

    Timer {
        interval: 50
        running: true
        onTriggered: loading.showText = true
    }

    Rectangle {
        anchors.fill: parent
        color: Tokens.pageBg
    }

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
            // 首帧不画它（见 showText 的说明）：这一行是**第一处要字体**的东西
            visible: loading.showText
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
