// 高级安装页 —— 2026-09-25 评审定内容：**语言 / 键盘 / 时区 / 主机名**。
//
//                          [ 滑块图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 高级安装                                      │
//        │ 这四项都有默认值；不动它就是默认。             │
//        │ ┌──────────────────────────────────────────┐ │
//        │ │ 语言        zh_CN.UTF-8              ›    │ │  ← 整行可点
//        │ │ 键盘        us                       ›    │ │
//        │ │ 时区        Asia/Shanghai            ›    │ │
//        │ │ 主机名      mipl                     ›    │ │
//        │ └──────────────────────────────────────────┘ │
//        └──────────────────────────────────────────────┘
//        返回
//
// ── 为什么是这四项，以及它们为什么不在主流程里 ─────────────────────────
// 主流程只留「这台机器装成什么样」的硬决定（网络 → 盘 → 分区 → 擦除确认 →
// 账户 → 安装详情 → 安装）；语言 / 键盘 / 时区 / 主机名都有**能用的默认值**
// （zh_CN.UTF-8 / us / Asia/Shanghai / mipl），要改的人自然会来这一页，
// 不改的人不该被拦四道 —— 一屏一决策，主流程越短越好（tech/07 §3）。
//
// 旧的「安装计划」页（`PlanPage.qml`）与旧的高级面板（分区 / 系统 / 账户 /
// 安装方式）**都已作废**：前者被 语言 / 键盘 / 时区 / 主机名 / 安装详情 五屏
// 瓜分干净，后者的三项在主流程里已有更清楚的位置。
//
// ── 改过的项带一个蓝点（不是文字）──────────────────────────────────────
// 与默认值不同就在行首点一个小圆点（`Tokens.accentDecor`，纯装饰）：
// 让人一眼看出「我动过什么」，而不必读字。默认值来自 `FlowDefaults`。
//
// 这一页**没有主按钮**：它是分支，不是向导里的一步，出去就是「返回」
// （PageShell 在 `primaryText` 为空时整颗不画主按钮）。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    title: ""
    subtitle: ""
    backText: "返回"

    // 一行一条短条目，宽度按内容定
    contentWidth: 660

    /// 每一行：去哪一页、显示什么、当前值、是否已经被改过（与默认值不同）
    property var rows: [
        {
            page: "language",
            label: "语言",
            value: "zh_CN.UTF-8",
            changed: false
        },
        {
            page: "keyboard",
            label: "键盘",
            value: "us",
            changed: false
        },
        {
            page: "timezone",
            label: "时区",
            value: "Asia/Shanghai",
            changed: false
        },
        {
            page: "hostname",
            label: "主机名",
            value: "mipl",
            changed: false
        }
    ]

    signal rowChosen(string pageName)
    signal backRequested()

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "sliders-horizontal"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s2
            title: "高级安装"

            Column {
                width: parent.width
                spacing: Tokens.s2

                Text {
                    width: parent.width
                    text: "这四项都有默认值 —— 不动它就是默认。"
                    font: Tokens.small
                    color: Tokens.textMuted
                    wrapMode: Text.WordWrap
                }

                // 设置清单：一行一个可点区域，行间用 1px 细线分（不是卡片套卡片）
                Column {
                    width: parent.width
                    spacing: 0

                    Repeater {
                        model: page.rows
                        delegate: Item {
                            required property var modelData
                            required property int index

                            width: parent.width
                            height: 56

                            Rectangle {
                                anchors.top: parent.top
                                width: parent.width
                                height: 1
                                color: Tokens.border
                                visible: parent.index > 0
                            }

                            Rectangle {
                                anchors.fill: parent
                                radius: Tokens.rControl
                                color: rowArea.containsMouse ? Tokens.subtleBg : "transparent"

                                Behavior on color {
                                    ColorAnimation { duration: Tokens.motionFast }
                                }
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Tokens.s2
                                anchors.rightMargin: Tokens.s2
                                spacing: Tokens.s2

                                // 改过就打一个蓝点（装饰，不承担信息）
                                Rectangle {
                                    Layout.alignment: Qt.AlignVCenter
                                    width: 8
                                    height: 8
                                    radius: 4
                                    color: Tokens.accentDecor
                                    visible: modelData.changed
                                }

                                Text {
                                    text: modelData.label
                                    font: Tokens.body
                                    color: Tokens.text
                                    Layout.alignment: Qt.AlignVCenter
                                }

                                Item { Layout.fillWidth: true }

                                Text {
                                    text: modelData.value
                                    font: Tokens.technical
                                    color: Tokens.textMuted
                                    Layout.alignment: Qt.AlignVCenter
                                    elide: Text.ElideRight
                                }

                                Icon {
                                    name: "chevron-right"
                                    size: 16
                                    color: Tokens.textFaint
                                    Layout.alignment: Qt.AlignVCenter
                                }
                            }

                            MouseArea {
                                id: rowArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.rowChosen(modelData.page)
                            }
                        }
                    }
                }
            }
        }
    }

    onBackClicked: page.backRequested()
}
