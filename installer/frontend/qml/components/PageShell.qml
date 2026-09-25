// 页面骨架 —— 五页共用一套**固定的操作逻辑**。
//
// 之前每页自己摆按钮，位置与样式各不相同，这是「操作逻辑不统一」的根子。
// 现在收进这里，每页只能声明「两个动作是什么」，不能自己决定它们长什么样、放哪：
//
//   ┌────────────────────────────────────────────────────┐
//   │ ← 返回                              [右上角状态]   │  ← 有返回动作时才显示
//   │                                                     │
//   │ 页面标题                                            │
//   │ 一句话说明                                          │
//   │                                                     │
//   │ 内容区（自适应高度，不需要滚动）                    │
//   │                                                     │
//   │                                          [主按钮]   │  ← 右下角，永远只一个实心按钮
//   └────────────────────────────────────────────────────┘
//
// **四条硬约束：**
//   1. 主按钮永远在右下角，永远只一个，且是唯一实心按钮；
//   2. 返回永远在左上角，是文字链接，不是按钮；
//   3. 次要动作（放弃、重试…）跟主按钮同排、在它左边，用描边按钮；
//   4. 内容区优先**一屏放得下** —— 放不下就该删内容，而不是加滚动条。
//
// ── 第 4 条的例外：小屏 ─────────────────────────────────────────────
// 主画布 1280×800 上每一页都必须不滚动；**1024×600 上允许滚动** ——
// 最小屏是硬需求，浏览器式地「把窗口改高一点」不是所有人都做得到。
// 放不下时才出现滚动条，样式是自定义的 4px 圆头细条（不用系统滚动条：
// 它的粗细、颜色、圆角都由平台主题决定，同一份界面在不同机器上长得不一样）。
// 放得下时 `interactive` 为 false，滚轮事件照常穿透给页面。
//
// ── 宽度绑定的单一来源（踩过一次）──────────────────────────────────────
// 最外层不是自动定宽的 Column，而是显式给宽的 Item（pageWidth）。
// Column 的 implicitWidth 取「最宽子项」，子项的宽又常按父宽算 —— 接上就是
// QQuickItem::polish() 循环（实测刷屏）。内部宽度一律从 pageWidth 往下走。

import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "../theme"

Window {
    id: shell

    // ── 接口 ──────────────────────────────────────────────────────────
    property string title: ""
    property string subtitle: ""
    /// 右上角状态文字（可选）：欢迎页用它显示「需要处理 N 项」
    property string statusText: ""
    property string statusTone: ""       // "" | "warn" | "danger"
    /// 左上角返回动作；空字符串 = 没有返回
    property string backText: ""
    /// 页头最右的次要链接（欢迎页用「高级模式」）。
    /// 放页头而不是行动区，是为了让「往前一步」永远只属于行动区那**一个**实心按钮 ——
    /// 页头里的东西永远不是主流程的一部分。
    property string headerLinkText: ""
    /// 主按钮（右下角，唯一实心按钮）
    property string primaryText: ""
    property bool primaryEnabled: true
    /// 次要动作（与主按钮同排、在左）
    property string secondaryText: ""
    property bool secondaryVisible: false
    /// 危险主按钮（擦盘那种不可逆动作）
    property bool primaryDanger: false

    /// 主内容区
    property alias content: body.data

    signal backClicked()
    signal primaryClicked()
    signal secondaryClicked()
    signal headerLinkClicked()

    width: 1280
    height: 800
    visible: true
    color: Tokens.pageBg

    /// 内容列宽度上限。默认 880；内容少的页面（网络列表）可以调窄 ——
    /// 一列 880px 的表单在 1280 的屏上其实难读，窄一点更像设置面板。
    property real contentWidth: Tokens.contentMaxWidth

    /// 内容列宽度：单一来源，内部不再回读父宽
    readonly property real pageWidth:
        Math.min(shell.width - Tokens.pagePadding * 2, shell.contentWidth)

    /// 内容区**最多**能用多高（页头下沿到行动区上沿，已扣掉上下的 s4 留白）。
    ///
    /// 页面按它决定「内部列表开几行」这类事 —— 目的是让**内部组件滚**，
    /// 而不是整页滚出第二根滚动条（语言页的 500 条 locale 就是这么处理的）。
    /// 它只看页头与行动区，不看页面内容，所以不会与页面的内容高度互相牵制。
    readonly property real contentAvailableHeight:
        Math.max(0, actionBar.y - (head.y + head.height + Tokens.s4) - Tokens.s4)

    /// 内容实际占多高。
    ///
    /// **不能直接用 `body.height`**：`Column` 的 implicitHeight 是抛光阶段算的，
    /// 而这个值又反过来参与下面的居中表达式 —— 实测它会**停在很早的一次测量上**
    /// （某页 body.height 报 76，而里面的卡片实际 528），于是内容画到行动区底下。
    /// 自己按子项求和，测量过程与布局无关。
    function contentHeight() {
        var total = 0;
        var kids = body.children;
        for (var i = 0; i < kids.length; i++) {
            total += kids[i].height;
            if (kids[i].visible !== false && i < kids.length - 1)
                total += body.spacing;
        }
        return total;
    }

    // ── 页头 ──────────────────────────────────────────────────────────
    Item {
        id: head
        x: (shell.width - shell.pageWidth) / 2
        y: Tokens.s5
        width: shell.pageWidth
        height: headColumn.height

        Column {
            id: headColumn
            width: parent.width
            spacing: Tokens.s3

            // 第一行：返回（左）+ 状态 + 页头链接（右）。
            // 三者都没有时这一行高度为 0 —— 不占空白。
            RowLayout {
                width: parent.width
                spacing: Tokens.s3
                visible: shell.backText !== "" || shell.statusText !== ""
                         || shell.headerLinkText !== ""

                Text {
                    visible: shell.backText !== ""
                    text: shell.backText
                    font: Tokens.body
                    color: Tokens.accentAction

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -Tokens.s2
                        cursorShape: Qt.PointingHandCursor
                        onClicked: shell.backClicked()
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    visible: shell.statusText !== ""
                    text: shell.statusText
                    font: Tokens.small
                    color: shell.statusTone === "danger" ? Tokens.danger
                                                         : (shell.statusTone === "warn" ? Tokens.warning
                                                                                        : Tokens.textMuted)
                }

                Text {
                    visible: shell.headerLinkText !== ""
                    text: shell.headerLinkText
                    font: Tokens.body
                    color: Tokens.accentAction

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -Tokens.s2
                        cursorShape: Qt.PointingHandCursor
                        onClicked: shell.headerLinkClicked()
                    }
                }
            }

            // 标题块
            Column {
                width: parent.width
                spacing: Tokens.s1

                Text {
                    width: parent.width
                    text: shell.title
                    font: Tokens.display
                    color: Tokens.text
                    wrapMode: Text.WordWrap
                    visible: text !== ""
                }
                Text {
                    width: parent.width
                    text: shell.subtitle
                    font: Tokens.body
                    color: Tokens.textMuted
                    wrapMode: Text.WordWrap
                    visible: text !== ""
                }
            }
        }
    }

    // ── 行动区：固定贴底 ───────────────────────────────────────────────
    //
    // 它是一整条**不透明**的底栏（底色与页面底一致），高度 = 按钮 + 上下的留白。
    // 为什么必须不透明：内容偶尔会算高一点（实测首页右卡比内容区高 39px），
    // 底栏透明时按钮就会压在卡片上 —— 一条实心底栏是最后一道遮蔽。
    // 内容区从 actionBar.y 起算，所以正常情况下它本来也不该越界。
    Rectangle {
        id: actionBar
        x: 0
        y: shell.height - height
        width: shell.width
        height: actionRow.implicitHeight + Tokens.s2 * 2
        color: Tokens.pageBg

        RowLayout {
            id: actionRow
            x: (shell.width - shell.pageWidth) / 2
            y: Tokens.s2
            width: shell.pageWidth
            spacing: Tokens.s2

            Item { Layout.fillWidth: true }   // 把所有按钮推到右边

            Button {
                visible: shell.secondaryVisible
                text: shell.secondaryText
                variant: "secondary"
                onClicked: shell.secondaryClicked()
            }

            Button {
                // 没有主行动时**整颗不画**：留一颗空胶囊在右下角比没有按钮更糟
                // （安装页在跑的时候就是只有「取消安装」一个次要动作）。
                visible: shell.primaryText !== ""
                text: shell.primaryText
                enabled: shell.primaryEnabled
                variant: shell.primaryDanger ? "danger" : "primary"
                onClicked: shell.primaryClicked()
            }
        }
    }

    // ── 内容区：能居中就居中，放不下才滚动（小屏），**不裁内容** ────────
    //
    // 内容**垂直居中**放在页头与行动区之间：kiosk 是全屏的，内容贴着页头、
    // 按钮贴着地，中间空一大块会显得没做完。居中之后上下留白对称。
    // 内容比可用空间高时退回顶部对齐（floor 那一半），不让它被切掉上边。
    Item {
        id: contentArea
        x: (shell.width - shell.pageWidth) / 2
        y: Math.max(head.y + head.height + Tokens.s4,
                    head.y + head.height
                    + (actionBar.y - head.y - head.height - shell.contentHeight()) / 2)
        width: shell.pageWidth
        height: Math.max(0, actionBar.y - y - Tokens.s4)

        Flickable {
            id: flick
            anchors.fill: parent
            contentWidth: width
            // 用 `contentHeight()` 而不是 `body.height`：后者在抛光阶段会被
            // 停在很早的一次测量上（这个坑在文件头的宽度那一节也踩过）。
            contentHeight: shell.contentHeight()
            boundsBehavior: Flickable.StopAtBounds
            // 放得下就不接管拖动/滚轮；放不下才让页面滚起来。
            interactive: contentHeight > height
            // **只在滚动时才裁。** 无条件 clip 会切掉那些有意画到内容列之外的东西
            // （安装页的日志框就贴着窗口右缘），那属于各页自己的版面，不是这里的活。
            clip: interactive
            // 默认的 pixelAligned 会把内容对齐到整像素，于是居中算出来的半个像素
            // 被抹掉 —— 每页的整体版面会跟改动前差 1px（不是错，但会让「这次截图
            // 和上次不一样」变成每次都要解释的事）。这一页的内容列本来就是整数宽，
            // 关掉它，**放得下时的版面与改动前逐像素一致**。
            pixelAligned: false

            Column {
                id: body
                width: flick.width
                spacing: Tokens.s3
            }
        }
    }

    // ── 自定义滚动条：4px 圆头细条，只在真的放不下时出现 ──────────────────
    //
    // 位置贴着内容列的右缘（不是窗口右缘）—— 页宽 880 时窗口右缘离内容有 200px，
    // 条子放那儿会跟它要滚的东西失去联系。压住内容也不需要：它在内容列之外。
    // 样式与拖动逻辑在 components/ScrollBar.qml（全项目唯一一份）。
    ScrollBar {
        flickable: flick
        x: contentArea.x + contentArea.width + Tokens.s1
        y: contentArea.y
        height: contentArea.height
    }
}
