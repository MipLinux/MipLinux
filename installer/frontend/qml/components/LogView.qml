// 滚动日志：等宽、深色底、自动追尾。
//
// 这是装包阶段唯一的「还活着」证据 —— 后端每条命令都经 Runner 报出来
// （util.py 的 self.reporter.command(argv)），日志在动就说明没卡死。
//
// 行格式约定（TextReporter 的两种前缀）：
//   "$ <命令>"  → 命令行，次要色
//   其余        → 旁白 / 事件 detail，主色

import QtQuick
import "../theme"

Rectangle {
    id: log

    //: 每行一条；以 "$ " 开头的当命令行渲染
    property var lines: []
    /// 贴底自动滚动。用户往上翻时应当置 false，否则回看历史会被拽回去。
    property bool autoScroll: true
    property bool empty: lines.length === 0
    property string emptyText: "尚无输出"

    radius: Tokens.rCard
    color: "#101728"     // 日志底：比页面底深得多，与卡片明确分开
    border.width: 1
    border.color: "#1E2A44"
    clip: true

    Text {
        anchors.centerIn: parent
        visible: log.empty
        text: log.emptyText
        font: Tokens.small
        color: "#5A6B8C"
    }

    Flickable {
        id: flick
        anchors.fill: parent
        anchors.margins: Tokens.s2
        // 右边多留一条滚动条的位置：没有它，日志比框长的时候看不出自己在哪
        anchors.rightMargin: Tokens.s2 + Tokens.s1
        contentWidth: width
        contentHeight: column.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        // 用户一上手就停止追尾：正在回看历史时被拽回底部是最烦人的一种行为
        onMovementStarted: log.autoScroll = false

        Column {
            id: column
            width: flick.width
            spacing: 2

            Repeater {
                model: log.lines
                delegate: Text {
                    required property string modelData
                    readonly property bool isCommand: modelData.startsWith("$ ")
                    width: column.width
                    text: modelData
                    font: Tokens.technicalSmall
                    color: isCommand ? "#7C93BF" : "#D8E2F5"
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }
            }
        }

        onContentHeightChanged: if (log.autoScroll) Qt.callLater(_stick)

        function _stick() {
            if (log.autoScroll)
                flick.contentY = Math.max(0, flick.contentHeight - flick.height);
        }
    }

    // 全项目唯一那份细滚动条（components/ScrollBar.qml）——与时区 / 语言 / 键盘
    // 三页的列表同一个组件、同一个摆法：贴住**滚动内容**的右缘，放得下时整根不画。
    // 它的颜色是对浅底的（borderField / accentDecor），压在这块深底上一样看得清。
    ScrollBar {
        flickable: flick
        x: log.width - Tokens.s1 - width
        y: flick.y
        height: flick.height
    }
}
