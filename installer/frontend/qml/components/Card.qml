// 卡片：白底 + 大圆角 + 一像素描边。
//
// 故意**不做重投影** —— QEMU 下是 pixman 软件渲染，重投影很贵。
// 层次主要靠描边与底色（pageBg 浅灰 / cardBg 纯白）区分。

import QtQuick
import "../theme"

Rectangle {
    id: card

    property alias title: titleLabel.text
    default property alias content: body.data

    //: true 时给一层「抬升」观感：描边更浅、底色纯白（用在欢迎页主视觉容器）
    property bool raised: false

    //: 内边距。默认 24；字段多的页面（账户页）可以调到 20 把整页压进一屏 ——
    //: 内容顶到行动区就必须滚动，而滚动是被尽量推迟的最后一招。
    property int padding: Tokens.cardPadding

    implicitWidth: Tokens.contentMaxWidth
    implicitHeight: column.implicitHeight + card.padding * 2
    radius: raised ? Tokens.rPanel : Tokens.rCard
    color: Tokens.cardBg
    border.width: 1
    border.color: raised ? "transparent" : Tokens.border

    //: 卡片内「标题」与「内容」之间的间距。默认 24；
    //: 内容高的卡片（网络列表）可以压到 8，把省下的高度让给内容。
    property int titleSpacing: Tokens.s3

    Column {
        id: column
        x: card.padding
        y: card.padding
        width: parent.width - card.padding * 2
        spacing: card.titleSpacing

        Text {
            id: titleLabel
            visible: text !== ""
            width: parent.width
            font: Tokens.heading
            color: Tokens.text
            wrapMode: Text.WordWrap
        }

        Column {
            id: body
            width: parent.width
            spacing: Tokens.s2
        }
    }
}
