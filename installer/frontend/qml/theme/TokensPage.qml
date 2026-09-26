// 设计令牌总览 —— 步骤 1 的评审用页面。
//
// 这个页面**不是产品界面**，它的唯一职责是让「颜色 / 圆角 / 字体 / 间距」在被写进
// 任何一页之前先被人看一眼。改 Tokens.qml 之后跑一次：
//
//     python3 installer/frontend/tools/shots.py --page tokens --out /tmp/shots
//
// 对比度那一列是实测值（不是估算），出处见 docs/work/tech/07-M2界面设计.md。

import QtQuick
import QtQuick.Window
import "../theme"

Window {
    id: page
    width: 1280
    height: 800
    visible: true
    color: Tokens.pageBg
    title: "MipLinux 安装器 · 设计令牌"

    readonly property var swatches: [
        { name: "accentDecor", value: Tokens.accentDecor, note: "LOGO 主色 · 只装饰 · 对白 4.20:1" },
        { name: "accentAction", value: Tokens.accentAction, note: "填充按钮底 · 白字 5.85:1" },
        { name: "accentPress", value: Tokens.accentPress, note: "按下态 · 白字 8.56:1" },
        { name: "accentTint", value: Tokens.accentTint, note: "选中底 / 进度轨道" },
        { name: "accentBorder", value: Tokens.accentBorder, note: "选中描边 · 仅装饰" },
        { name: "pageBg", value: Tokens.pageBg, note: "页面底 · 不用纯白" },
        { name: "cardBg", value: Tokens.cardBg, note: "卡片 / 抬升面" },
        { name: "subtleBg", value: Tokens.subtleBg, note: "悬停 / 分组底" },
        { name: "border", value: Tokens.border, note: "分隔与卡片描边" },
        { name: "borderField", value: Tokens.borderField, note: "输入框描边" },
        { name: "text", value: Tokens.text, note: "主文字 · 对底 16.07:1" },
        { name: "textMuted", value: Tokens.textMuted, note: "次要文字 · 对白 6.77:1" },
        { name: "textFaint", value: Tokens.textFaint, note: "提示 · 只放卡片上 4.55:1" },
        { name: "danger", value: Tokens.danger, note: "危险文字 4.95:1" },
        { name: "dangerFill", value: Tokens.dangerFill, note: "危险填充 · 白字 5.62:1" },
        { name: "dangerTint", value: Tokens.dangerTint, note: "危险浅底" },
        { name: "success", value: Tokens.success, note: "成功 5.04:1" },
        { name: "successTint", value: Tokens.successTint, note: "成功浅底" },
        { name: "warning", value: Tokens.warning, note: "警告 5.00:1" },
        { name: "warningTint", value: Tokens.warningTint, note: "警告浅底" },
        { name: "focusRing", value: Tokens.focusRing, note: "焦点环" },
        { name: "disabledBg", value: Tokens.disabledBg, note: "禁用填充" }
    ]

    readonly property var radii: [
        { name: "rControl", value: Tokens.rControl, note: "输入框 / 小控件" },
        { name: "rPill", value: Tokens.rPill, note: "按钮（胶囊）" },
        { name: "rCard", value: Tokens.rCard, note: "卡片" },
        { name: "rPanel", value: Tokens.rPanel, note: "大面板 / 主视觉" }
    ]

    readonly property var spaces: [
        { name: "s1", value: Tokens.s1 },
        { name: "s2", value: Tokens.s2 },
        { name: "s3", value: Tokens.s3 },
        { name: "s4", value: Tokens.s4 },
        { name: "s5", value: Tokens.s5 },
        { name: "s6", value: Tokens.s6 }
    ]

    readonly property var specimens: [
        { name: "fsTitle 30 / display", spec: Tokens.display, sample: "选择系统磁盘" },
        { name: "fsHeading 20 / heading", spec: Tokens.heading, sample: "分区方案预览" },
        { name: "fsBody 16 / body", spec: Tokens.body, sample: "盘上现有数据将全部丢失，且无法恢复。" },
        { name: "fsBody 16 / bodyStrong", spec: Tokens.bodyStrong, sample: "系统分区（512 MiB）" },
        { name: "fsSmall 14 / small", spec: Tokens.small, sample: "v0.1 默认值，装后可改" },
        { name: "fsMicro 12 / micro", spec: Tokens.micro, sample: "第 2 步，共 3 步" },
        { name: "fsSmall 14 / technical 等宽", spec: Tokens.technical, sample: "/dev/vda  40.0 GiB  EXT4" }
    ]

    // 这页是**评审用的固定版式**，不是产品界面 —— 所以不用 Flickable，
    // 直接一个 Column 铺满，取图时把画布给够就能一张图看全（--size 或 TALL_SIZE）。
    Column {
        id: column
        x: Tokens.pagePadding
        y: Tokens.s6
        width: page.width - Tokens.pagePadding * 2
        spacing: Tokens.s5

            // ── 页头 ────────────────────────────────────────────────
            Column {
                spacing: Tokens.s1
                Text {
                    text: "设计令牌"
                    font: Tokens.display
                    color: Tokens.text
                }
                Text {
                    text: "浅色 · 大圆角 · 年轻。颜色只在这份 Tokens.qml 里定义一次 —— "
                          + "界面代码里出现字面量色值就算破线。"
                    font: Tokens.body
                    color: Tokens.textMuted
                }
            }

            // ── 颜色 ────────────────────────────────────────────────
            Column {
                width: parent.width
                spacing: Tokens.s3

                Text { text: "颜色"; font: Tokens.heading; color: Tokens.text }

                Flow {
                    width: parent.width
                    spacing: Tokens.s3

                    Repeater {
                        model: page.swatches
                        delegate: Column {
                            required property var modelData
                            width: 200
                            spacing: Tokens.s1

                            Rectangle {
                                width: parent.width
                                height: 64
                                radius: Tokens.rControl
                                color: modelData.value
                                border.width: 1
                                border.color: Tokens.border
                            }
                            Text {
                                text: modelData.name
                                font: Tokens.technical
                                color: Tokens.text
                            }
                            Text {
                                width: parent.width
                                text: modelData.note
                                font: Tokens.micro
                                color: Tokens.textFaint
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }

            // ── 圆角 ────────────────────────────────────────────────
            Column {
                width: parent.width
                spacing: Tokens.s3

                Text { text: "圆角（「大圆角」的具体值）"; font: Tokens.heading; color: Tokens.text }

                Row {
                    spacing: Tokens.s4

                    Repeater {
                        model: page.radii
                        delegate: Column {
                            required property var modelData
                            spacing: Tokens.s1

                            Rectangle {
                                width: 140
                                height: 84
                                radius: modelData.value
                                color: Tokens.accentDecor
                            }
                            Text {
                                text: modelData.name + " = " + modelData.value
                                font: Tokens.technical
                                color: Tokens.text
                            }
                            Text {
                                text: modelData.note
                                font: Tokens.micro
                                color: Tokens.textFaint
                            }
                        }
                    }
                }
            }

            // ── 间距 ────────────────────────────────────────────────
            Column {
                width: parent.width
                spacing: Tokens.s2

                Text { text: "间距（8px 基准）"; font: Tokens.heading; color: Tokens.text }

                Repeater {
                    model: page.spaces
                    delegate: Row {
                        required property var modelData
                        spacing: Tokens.s2

                        Text {
                            width: 40
                            text: modelData.name
                            font: Tokens.technical
                            color: Tokens.text
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            width: 40
                            text: modelData.value + "px"
                            font: Tokens.technical
                            color: Tokens.textMuted
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Rectangle {
                            width: modelData.value * 2
                            height: 14
                            radius: 7
                            color: Tokens.accentBorder
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // ── 字体 ────────────────────────────────────────────────
            Column {
                width: parent.width
                spacing: Tokens.s3

                Text { text: "字体与字号"; font: Tokens.heading; color: Tokens.text }

                Rectangle {
                    width: parent.width
                    radius: Tokens.rCard
                    color: Tokens.cardBg
                    border.width: 1
                    border.color: Tokens.border
                    implicitHeight: specimensColumn.height + Tokens.cardPadding * 2

                    Column {
                        id: specimensColumn
                        x: Tokens.cardPadding
                        y: Tokens.cardPadding
                        width: parent.width - Tokens.cardPadding * 2
                        spacing: Tokens.s3

                        Repeater {
                            model: page.specimens
                            delegate: Column {
                                required property var modelData
                                width: specimensColumn.width
                                spacing: 2

                                Text {
                                    text: modelData.name
                                    font: Tokens.technicalSmall
                                    color: Tokens.textFaint
                                }
                                Text {
                                    text: modelData.sample
                                    font: modelData.spec
                                    color: Tokens.text
                                }
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: "只用 Live 环境里确实存在、且实测 fc-match 解析得到的两族："
                          + "Noto Sans CJK SC 与 Maple Mono NF CN。显式指定字体族，不依赖 fallback —— "
                          + "宿主的 sans-serif:lang=zh-cn 会落到 wqy-zenhei，与 Live 不是同一个结果。"
                    font: Tokens.small
                    color: Tokens.textFaint
                    wrapMode: Text.WordWrap
                }
            }
        }
}
