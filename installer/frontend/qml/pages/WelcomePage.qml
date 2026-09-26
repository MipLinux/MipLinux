// 欢迎页 —— **不放任何信息**。
//
// 这一页只做一件事：让人知道这是什么，然后往下走。
// 没有检查项、没有分区计划、没有默认值、没有状态提示 —— 那些都是**信息**，
// 一律归下一页（`PlanPage`）。混在这一页，「欢迎」就变成了一张要读的表格。
//
// 这一页只剩四样东西，全都不承载信息：
//   · LOGO
//   · 产品名
//   · 一个按钮，写着点下去会发生什么
//   · 一个次要入口：高级安装
//
// 不写标语、不写「开始前的检查」、不写版本号 —— 要判断什么不是欢迎页的职责。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    // 这一页**不用页头**：没有标题、副标题、状态、返回。
    // 页头高度为 0，内容区自然上移，视觉上就是整页居中。
    primaryText: "开始安装"
    secondaryText: "高级安装"
    secondaryVisible: true

    signal installRequested()
    signal customizeRequested()

    // ── 内容：只有 LOGO 与产品名 ───────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s4

        // 顶上留白，让整块内容落在视觉中心偏上 —— 中心偏上比正中更稳。
        // 160 是「页头为 0」时内容区的基础上移量。
        Item {
            width: parent.width
            height: Math.max(0, (parent.parent.height - 400) / 2 - 40)
        }

        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            source: Qt.resolvedUrl("../../assets/mipl-logo-hero.png")
            sourceSize.width: 200
            sourceSize.height: 200
            width: 200
            height: 200
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            opacity: 0

            // 一次淡入，收尾即定格。不循环、不加装饰。
            NumberAnimation on opacity {
                from: 0
                to: 1
                duration: Tokens.motionNormal * 2
                easing.type: Easing.OutCubic
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "MipLinux"
            font: Tokens.display
            color: Tokens.text
        }

        // 一行介绍，两行排。放在产品名下面、按钮上面 ——
        // 这是这一页唯一带信息的文字，刻意压到两句、不加形容词。
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            horizontalAlignment: Text.AlignHCenter
            text: "基于 Arch Linux 的滚动发行版\n中文与 NVIDIA 开箱即用"
            font: Tokens.body
            color: Tokens.textMuted
            lineHeight: 1.5
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.installRequested()
    onSecondaryClicked: page.customizeRequested()
}
