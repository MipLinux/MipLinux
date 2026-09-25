// 结束页 —— 与欢迎页**首尾呼应**（2026-09-25 评审）。
//
// 欢迎页只有四样东西：LOGO / 产品名 / 一行说明 / 一个主按钮。这一页一一对应：
//
//        欢迎页                          结束页
//        [ LOGO 200px ]                  [ LOGO 200px ]        ← 同一个资源、同样一次淡入
//        MipLinux（大字）                装好了（大字）
//        基于 Arch Linux 的滚动发行版       Live 介质可以拔掉，重启就进入新系统。
//        中文与 NVIDIA 开箱即用
//        [开始安装] [高级安装]            [立即重启]
//
// **这一页不放任何多余信息。** 装了什么、分区方案、引导方式、root 状态、主机名、
// 耗时、「第一次登录之后」那几条 —— 上一版全在这儿，评审口径是全部拿掉：
// 装完的机器就在眼前，要查什么进系统查。这一页只承担两件事 ——
// **说清「结束了」**，和**给一个「现在重启」**。
//
// 首尾呼应不是装饰：这是同一个窗口的第一帧与最后一帧。长得一样，用户就知道
// 「回到起点了，这件事办完了」；末帧多塞一张表格，那个感觉就没了。
//
// 「Live 介质可以拔掉」这句留着 —— 它是**动作**（现在该拔盘了），不是**信息**：
// 不说，用户会在拔 U 盘时犹豫（tech/07 §P5 要求明确这一句）。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    // 与欢迎页一样**不用页头**：没有标题、副标题、状态、返回 —— 页头高度为 0，
    // 内容区自然上移，整页居中。
    title: ""
    subtitle: ""
    backText: ""

    primaryText: "立即重启"

    signal rebootRequested()

    // ── 内容：LOGO + 一句「装好了」+ 一行接下来做什么 ───────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s4

        // 与欢迎页**同一个表达式**：整块落在视觉中心偏上（中心偏上比正中更稳）。
        // 两页用同一个数百，首尾的位置才对得上。
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

            // 一次淡入，收尾即定格 —— 与欢迎页同一段动画（不循环、不加装饰）
            NumberAnimation on opacity {
                from: 0
                to: 1
                duration: Tokens.motionNormal * 2
                easing.type: Easing.OutCubic
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "装好了"
            font: Tokens.display
            color: Tokens.text
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            horizontalAlignment: Text.AlignHCenter
            text: "Live 介质可以拔掉，重启就进入新系统。"
            font: Tokens.body
            color: Tokens.textMuted
        }

        // 与欢迎页**对齐**用的留白。这一页比欢迎页少一行定位语，内容区又是垂直居中的，
        // 块矮就整体往下沉 —— 底下补一段才落回同一个高度。
        //
        // **16 这个数是量出来的，不是算出来的：** 欢迎页那条居中表达式读的是内容自身的
        // 高度（循环绑定），拿它推导的值不可信（试过 16 / 24 / 32，只有 16 让两页的
        // 首个非背景行同为 y=223）。两页要长期对齐，得先把版式数学统一到一处；
        // 在那之前，改欢迎页的定位语行数就要回来重新量这一页。
        Item {
            width: parent.width
            height: 16
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.rebootRequested()
}
