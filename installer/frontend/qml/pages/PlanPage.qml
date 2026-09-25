// 安装计划页。
//
// 欢迎页不放任何信息，所以这个安装的**全部事实**都摆在这一页：
// 装到哪、装成什么、用什么账户、检查过没过、会采用哪些默认值。
// 用户在这一页就能把整件事确认完，后面两页只是让他改其中两项。
//
// 三条自我约束：
//   · **不需要滚动**：内容区固定一屏，放不下就删内容，不加滚动条。
//   · **文案直白**：短句、说明事实、不寒暄、不堆形容词。
//   · **操作统一**：唯一实心按钮在右下角，写着下一步会做什么。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    title: "安装计划"
    subtitle: "确认下面这些，然后开始。每一步都还能返回修改。"
    headerLinkText: "高级安装"

    // ── 数据：全部来自后端或磁盘枚举；没有数据时如实说没有 ─────────────
    property var disk: null              // { path, model, size } 或 null
    property string localeText: "zh_CN.UTF-8"
    property string keyboardText: "us"
    property string timezoneText: "Asia/Shanghai"

    property var checks: [
        {
            label: "网络",
            state: "ok",
            value: "已连接（有线）"
        },
        {
            label: "目标盘",
            state: "fail",
            value: "未检测到"
        },
        {
            label: "EFI 引导",
            state: "ok",
            value: "UEFI"
        }
    ]

    readonly property int failedCount: {
        var n = 0;
        for (var i = 0; i < checks.length; i++) {
            if (checks[i].state === "fail")
                n++;
        }
        return n;
    }

    //: 缺磁盘时主按钮也不置灰 —— 点了给的是解释，不是沉默。
    //: 「选盘」是下一页的事，所以按钮写的是扫描，不是「开始安装」。
    statusText: failedCount > 0 ? "有 " + failedCount + " 项需要处理" : ""
    statusTone: failedCount > 0 ? "warn" : ""

    primaryText: page.disk ? "选择系统磁盘" : "重新扫描磁盘"

    signal chooseDiskRequested()
    signal customizeRequested()

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        // 并排两张卡：计划与检查。这一页最该看清的就是这两块。
        RowLayout {
            width: parent.width
            spacing: Tokens.s2

            Card {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "将要安装"

                Column {
                    width: parent.width
                    spacing: Tokens.s2

                    // 目标盘：没有盘就不假装知道，后面的值列留空
                    RowLayout {
                        width: parent.width
                        spacing: Tokens.s2

                        Text {
                            text: "目标盘"
                            font: Tokens.body
                            color: Tokens.textMuted
                            Layout.preferredWidth: 72
                        }
                        Text {
                            text: page.disk ? page.disk.path : "未检测到"
                            font: Tokens.technical
                            color: page.disk ? Tokens.text : Tokens.danger
                        }
                        Text {
                            visible: page.disk !== null
                            text: page.disk ? page.disk.size : ""
                            font: Tokens.technical
                            color: Tokens.textFaint
                        }
                        Item { Layout.fillWidth: true }
                    }

                    // 缺磁盘时把原因和办法写在这里 —— 它比一句「有 1 项需要处理」有用
                    Text {
                        width: parent.width
                        visible: page.disk === null
                        text: "安装器需要一整块盘。QEMU 里用 mipl.sh installer 挂一块。"
                        font: Tokens.small
                        color: Tokens.textFaint
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Tokens.s2

                        Text {
                            text: "分区"
                            font: Tokens.body
                            color: Tokens.textMuted
                            Layout.preferredWidth: 72
                        }
                        Text {
                            text: "系统分区 512 MiB（vfat）"
                            font: Tokens.technical
                            color: Tokens.text
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Tokens.s2

                        Text {
                            text: "根分区"
                            font: Tokens.body
                            color: Tokens.textMuted
                            Layout.preferredWidth: 72
                        }
                        Text {
                            text: page.disk ? "盘上剩余空间（ext4）" : "—"
                            font: Tokens.technical
                            color: page.disk ? Tokens.text : Tokens.textFaint
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Tokens.s2

                        Text {
                            text: "账户"
                            font: Tokens.body
                            color: Tokens.textMuted
                            Layout.preferredWidth: 72
                        }
                        Text {
                            text: "下一步设置"
                            font: Tokens.technical
                            color: Tokens.textFaint
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        width: parent.width
                        text: "整块盘会被重新分区，盘上数据全部清除。v0.1 不支持双系统与 BIOS 引导。"
                        font: Tokens.small
                        color: Tokens.textFaint
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // 右列只用**一张** Card：RowLayout 里塞 Column 会塌 ——
            // Column 的 implicitWidth 取最宽子项，而子项又绑着 parent.width，
            // 结果算出个极小值，整列被压没（实测）。
            Card {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "开始前的检查"

                Column {
                    width: parent.width
                    spacing: Tokens.s3

                    ReadyCheck {
                        width: parent.width
                        labelWidth: 88
                        items: page.checks
                    }

                    // 分隔：下面是另一件事（将采用的默认值），不是检查项
                    Rectangle {
                        width: parent.width
                        height: 1
                        color: Tokens.border
                    }

                    Column {
                        width: parent.width
                        spacing: Tokens.s2

                        Text {
                            text: "将采用的默认值"
                            font: Tokens.bodyStrong
                            color: Tokens.text
                        }

                        Repeater {
                            model: [
                                { k: "语言", v: page.localeText },
                                { k: "键盘", v: page.keyboardText },
                                { k: "时区", v: page.timezoneText }
                            ]
                            delegate: RowLayout {
                                required property var modelData
                                width: parent.width
                                spacing: Tokens.s2

                                Text {
                                    text: modelData.k
                                    font: Tokens.body
                                    color: Tokens.textMuted
                                    Layout.preferredWidth: 88
                                }
                                Text {
                                    text: modelData.v
                                    font: Tokens.technical
                                    color: Tokens.text
                                }
                                Item { Layout.fillWidth: true }
                            }
                        }

                        Text {
                            width: parent.width
                            text: "装完可以改，也可以现在从右上角「高级安装」里改。"
                            font: Tokens.small
                            color: Tokens.textFaint
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.chooseDiskRequested()
    onHeaderLinkClicked: page.customizeRequested()
}
