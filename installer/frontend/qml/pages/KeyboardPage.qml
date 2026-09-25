// 键盘布局页 —— 与语言页同一套：**大图标 + 一张主卡片**，不要页头。
//
//                          [ 键盘图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 键盘布局                                       │
//        │ [ 筛选键盘布局（名字或地区代码）             ] │
//        │ ┌──────────────────────────────────────┐  ▐  │
//        │ │ ◉ us                                  │  ▐  │  ← 列表自己滚
//        │ │ ○ us-acentos                          │  ▐  │
//        │ │ ○ be-latin1                           │  ▐  │
//        │ │ ○ br-abnt2                            │  ▐  │
//        │ │ ○ cz                                  │  ▐  │
//        │ │ ○ de                                  │  ▐  │
//        │ │ ○ de-latin1-nodeadkeys                │  ▐  │
//        │ └──────────────────────────────────────┘  ▐  │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// ── 这一页为什么长这样（四条，都不是审美选择）────────────────────────
//
// 1. **列表里只有 id，没有「中文名」。** 本机 `localectl list-keymaps` 有 **252 条**，
//    形如 `us` / `de-latin1-nodeadkeys`（最长 35 字符）。kbd 包里**没有**任何人类
//    可读的名字（不像 locale 有语言名可用），所以要么照实显示 id，要么我们**自己编
//    一份名字表** —— 编出来的表会漂移、会编错，而且和「包清单唯一来源」是同一类毛病。
//    所以：照实显示 id，用**筛选框**解决「252 条里怎么找」。
//    （真接线时这份名单由后端给：`localectl list-keymaps` 或扫
//    `/usr/share/kbd/keymaps`，不由前端写死。）
//
// 2. **不放「试一试」输入框**（很多安装器有）。因为这一页选的是**控制台**键位
//    （写进 `/etc/vconsole.conf` 的 `KEYMAP=`），而安装器跑在 cage/Wayland 会话里：
//    用户在界面里敲的字走的是 XKB，**不经过**控制台的键位翻译表；`loadkeys` 改的
//    也只是 VT 那张表。所以放一个测试框，敲出来的字根本不反映所选布局 —— 那是骗人。
//    要真给预览，只能画一张布局图（另有一摊工作量，先不做）。
//
// 3. **只覆盖控制台。** 图形会话里的键位由桌面环境自己设（niri / Hyprland 各有各的
//    配置），不在这一页的范围 —— 与 Issue #64 里的界定一致。
//
// 4. ⚠️ **这一页整个依赖 Issue #64。** 后端 v0.1 把 `KEYMAP=us` 写死
//    （`configure.py:100-103`，`TargetConfig` 里根本没有这个字段），所以今天
//    **除了 `us` 之外，选哪个都不会真的生效**。这一页是按 #64 落地后的样子画的，
//    不是「已经能用」。按「不显示不能用的开关」的口径，这一页在 #64 落地前
//    **不应该进 ISO 的可用路径**（可以在原型里评审）。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    title: ""
    subtitle: ""
    backText: "返回"
    // 宽度用**文档默认值**（tech/07 §2.6：pagePadding 48、contentMaxWidth 880）——
    // 卡片 880 宽、左右各留 200。曾经这几页把 660 写死过（当时觉得「一列短条目
    // 880 太散」），但那样与其余各页的外边距不一致，已统一（2026-09-25）。

    /// 真实的 keymap id（本机 `localectl list-keymaps` 里核过都在），
    /// `us` 置顶 —— 它是 v0.1 唯一的实际值，也是中文用户打拼音的常用布局。
    property var keymaps: [
        "us",
        "us-acentos",
        "be-latin1",
        "br-abnt2",
        "cz",
        "de",
        "de-latin1",
        "de-latin1-nodeadkeys",
        "dk",
        "es",
        "fi",
        "fr",
        "fr-bepo",
        "fr-latin9",
        "hu",
        "il",
        "it2",
        "jp106",
        "nl",
        "no",
        "pl",
        "pt-latin1",
        "ro",
        "ru",
        "tr_q-latin5",
        "ua-utf",
        "uk"
    ]

    /// 选中的是哪个 id（不是第几行）—— 列表会被筛选改变行数，记下标会错位
    property string selectedKeymap: "us"

    /// 筛选关键词：252 条里找一条，靠滚是折磨（与语言页同一个理由）
    property string query: ""

    readonly property var filteredKeymaps: {
        var q = query.trim().toLowerCase();
        if (q === "")
            return keymaps;
        var out = [];
        for (var i = 0; i < keymaps.length; i++) {
            if (keymaps[i].toLowerCase().indexOf(q) >= 0)
                out.push(keymaps[i]);
        }
        return out;
    }

    /// 行高与行距沿用网络页 / 语言页那两个数
    readonly property int rowHeight: 44
    readonly property int rowSpacing: Tokens.s1

    /// 列表视口高度：与语言页同一笔账（图标 52 + 间距 24 + 卡片内边距 24
    /// + 卡片标题 27 + 标题与内容间距 8 + 筛选框 44 + 筛选框与列表间距 16 = 195），
    /// 预留 200，再 `floor` 到整行。理由见语言页同一段注释。
    readonly property int fixedChrome: 224
    readonly property int visibleRows:
        Math.max(2, Math.floor((page.contentAvailableHeight - page.fixedChrome
                                + page.rowSpacing) / (page.rowHeight + page.rowSpacing)))
    readonly property real listHeight:
        visibleRows * page.rowHeight + (visibleRows - 1) * page.rowSpacing

    /// 列表内容高：自己按条数算，不读容器的 implicit 尺寸（那个在抛光阶段才定）
    readonly property real listContentHeight:
        filteredKeymaps.length * page.rowHeight
        + Math.max(0, filteredKeymaps.length - 1) * page.rowSpacing

    primaryText: "继续"

    signal chosen(string keymap)
    signal backRequested()

    /// 换了筛选词就回到列表顶部
    onQueryChanged: keyFlick.contentY = 0

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "keyboard"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）——
            // 曾经这几页为了多塞一行压到 12，导致卡片内容左缘比别人少 12px，已统一
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s1
            title: "键盘布局"

            Column {
                width: parent.width
                spacing: Tokens.s2

                // ── 筛选框 ─────────────────────────────────────────
                Field {
                    fieldWidth: parent.width
                    fieldHeight: 44
                    label: ""
                    placeholder: "筛选键盘布局（名字或地区代码）"
                    text: page.query
                    onEdited: page.query = text
                }

                // ── 列表：卡片内自己滚 ──────────────────────────────
                Item {
                    id: listPanel
                    width: parent.width
                    height: page.listHeight

                    Flickable {
                        id: keyFlick
                        width: parent.width - 12
                        height: parent.height
                        contentWidth: width
                        contentHeight: page.listContentHeight
                        boundsBehavior: Flickable.StopAtBounds
                        interactive: contentHeight > height
                        clip: interactive
                        pixelAligned: false

                        Column {
                            width: parent.width
                            spacing: page.rowSpacing

                            Repeater {
                                model: page.filteredKeymaps
                                delegate: Rectangle {
                                    id: keyRow
                                    required property int index
                                    required property var modelData

                                    readonly property bool chosen:
                                        keyRow.modelData === page.selectedKeymap

                                    width: parent.width
                                    height: page.rowHeight
                                    radius: Tokens.rControl
                                    color: keyRow.chosen ? Tokens.accentTint : "transparent"

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: page.selectedKeymap = keyRow.modelData
                                    }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: Tokens.s2
                                        anchors.rightMargin: Tokens.s2
                                        spacing: Tokens.s2

                                        // 单选圈：与网络页 / 磁盘页 / 语言页同一个画法
                                        Rectangle {
                                            Layout.alignment: Qt.AlignVCenter
                                            width: 16
                                            height: 16
                                            radius: 8
                                            color: "transparent"
                                            border.width: keyRow.chosen ? 5 : 2
                                            border.color: keyRow.chosen
                                                          ? Tokens.accentAction
                                                          : Tokens.borderField
                                        }

                                        // id 本身就是**会写进 vconsole.conf 的那个值**，
                                        // 所以用等宽字：界面显示什么，系统里就是什么
                                        Text {
                                            text: keyRow.modelData
                                            font: Tokens.technical
                                            color: keyRow.chosen ? Tokens.accentAction
                                                                 : Tokens.text
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        // 唯一说得清的一个标记：v0.1 只有 us 真的生效
                                        Text {
                                            visible: keyRow.modelData === "us"
                                            text: "默认"
                                            font: Tokens.small
                                            color: Tokens.textFaint
                                            Layout.alignment: Qt.AlignVCenter
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // 过滤后一条都没有：说一句，而不是留一块空白
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Tokens.s2
                        anchors.top: parent.top
                        anchors.topMargin: Tokens.s2
                        visible: page.filteredKeymaps.length === 0
                        text: "没有匹配的键盘布局 —— 换个词，或清空筛选看全部。"
                        font: Tokens.small
                        color: Tokens.textMuted
                    }

                    ScrollBar {
                        flickable: keyFlick
                        x: listPanel.width - width
                        y: 0
                        height: listPanel.height
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.chosen(page.selectedKeymap)
    onBackClicked: page.backRequested()
}
