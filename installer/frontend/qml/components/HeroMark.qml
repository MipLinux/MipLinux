// 主视觉 LOGO。
//
// **刻意不做装饰。** 这里曾经在 LOGO 外面画一圈轨道环 + 一颗星光做「描线动画」，
// 已经去掉了：LOGO 自己已经是一枚完整的图形（蓝色渐变圆 + 海豹 + 山形 M + 星光），
// 再给它套一层环、加一颗星，是替它说话，不是让它说话。
// 「情绪价值」由版面留白、字体与动效的克制来给，不靠在标志上叠东西。
//
// 现在只做两件事：
//   1. 把 LOGO 显示出来（透明底，直接压在所在面的颜色上）
//   2. 一次很短的淡入，收尾即定格 —— 没有循环动画

import QtQuick
import "../theme"

Item {
    id: hero

    property url logoSource: ""
    /// LOGO 显示边长
    property int logoSize: 240

    implicitWidth: logoSize
    implicitHeight: logoSize

    Text {
        anchors.centerIn: parent
        visible: hero.logoSource.toString() === ""
        text: "LOGO 未生成\n跑 tools/build-assets.sh"
        horizontalAlignment: Text.AlignHCenter
        font: Tokens.technicalSmall
        color: Tokens.textFaint
    }

    Image {
        anchors.fill: parent
        source: hero.logoSource
        sourceSize.width: hero.logoSize
        sourceSize.height: hero.logoSize
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        opacity: 0

        // 一次淡入，收尾即定格。
        NumberAnimation on opacity {
            from: 0
            to: 1
            duration: Tokens.motionNormal * 2
            easing.type: Easing.OutCubic
        }
    }
}
