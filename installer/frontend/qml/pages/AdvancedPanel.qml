// 高级安装（面板）。
//
// 形态是**面板**，不是向导里的新步骤：从欢迎页右上角进入，关闭即回到简易流。
// 心理模型只有「进去看 / 出来」，没有「走到岔路口」。
//
// ── 界面里出现的每一项，都对照过后端现状 ──────────────────────────────
// 真控件：后端已支持的（目标盘、主机名、语言、时区；用户名与 root 密码
//         已实现只是 CLI 没暴露 —— 见 tech/07 §6 的 issue 3/4）
// 禁用+标注：机制已有、GUI 没接的（系统分区大小 —— plan_layout 收整个盘）
// 只出现在「即将支持」一行：v0.1 明确不做的（LUKS / LVM / 双系统 / BIOS）
//                         与要后端加能力的（文件系统选择、跳过某些阶段）
//
// 这样评审判的是「高级安装要往哪长」，而界面里没有任何**点了没反应**的控件。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

Window {
    id: panel
    width: 1280
    height: 800
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint

    property string language: "zh_CN.UTF-8"
    property string timezone: "Asia/Shanghai"
    property string keyboard: "us"
    property string hostName: "mipl"
    property string userName: "mipl"
    property bool setRootPassword: false
    ///: 变更过的字段数 —— 让「我偏离了默认」可见（简易流里的蓝点同源）
    property int changedCount: 0

    readonly property var defaults: ({
        language: "zh_CN.UTF-8",
        timezone: "Asia/Shanghai",
        hostName: "mipl",
        userName: "mipl",
        setRootPassword: false
    })

    function recount() {
        var n = 0;
        if (language !== defaults.language) n++;
        if (timezone !== defaults.timezone) n++;
        if (hostName !== defaults.hostName) n++;
        if (userName !== defaults.userName) n++;
        if (setRootPassword !== defaults.setRootPassword) n++;
        changedCount = n;
    }

    Component.onCompleted: recount()

    signal closed()

    // ── 遮罩：点它就关 ────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(23 / 255, 27 / 255, 36 / 255, 0.32)

        MouseArea {
            anchors.fill: parent
            onClicked: panel.closed()
        }
    }

    // ── 面板 ──────────────────────────────────────────────────────────
    Rectangle {
        id: sheet
        anchors.centerIn: parent
        width: 1000
        height: Math.min(700, panel.height - Tokens.s5 * 2)
        radius: Tokens.rPanel
        color: Tokens.pageBg
        border.width: 1
        border.color: Tokens.border

        // 挡住遮罩的点击，否则点面板内部也会关掉
        MouseArea { anchors.fill: parent }

        // ── 面板页头 ────────────────────────────────────────────────
        Item {
            id: sheetHead
            x: Tokens.s4
            y: Tokens.s4
            width: sheet.width - Tokens.s4 * 2
            height: headRow.height

            RowLayout {
                id: headRow
                width: parent.width
                spacing: Tokens.s3

                Column {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: "高级安装"
                        font: Tokens.heading
                        color: Tokens.text
                    }
                    Text {
                        text: panel.changedCount === 0
                              ? "下面全部是默认值 —— 不动它们等于没进来过。"
                              : "已修改 " + panel.changedCount + " 项。"
                        font: Tokens.small
                        color: panel.changedCount === 0 ? Tokens.textFaint : Tokens.accentAction
                    }
                }

                Button {
                    text: "返回简易安装"
                    variant: "secondary"
                    onClicked: panel.closed()
                }
            }
        }

        // ── 面板内容 ────────────────────────────────────────────────
        Flickable {
            x: Tokens.s4
            y: sheetHead.y + sheetHead.height + Tokens.s3
            width: sheet.width - Tokens.s4 * 2
            height: sheet.height - y - Tokens.s4
            contentWidth: width
            contentHeight: groups.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: groups
                width: parent.width
                spacing: Tokens.s3

                // ── 分区 ────────────────────────────────────────────
                Card {
                    width: parent.width
                    title: "分区"

                    Column {
                        width: parent.width
                        spacing: Tokens.s2

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s2

                            Text {
                                text: "系统分区大小"
                                font: Tokens.body
                                color: Tokens.disabledText
                                Layout.preferredWidth: 180
                            }
                            Rectangle {
                                Layout.preferredWidth: 120
                                Layout.preferredHeight: 44
                                radius: Tokens.rControl
                                color: Tokens.disabledBg
                                border.width: 1
                                border.color: Tokens.border
                                Text {
                                    anchors.centerIn: parent
                                    text: "512 MiB"
                                    font: Tokens.technical
                                    color: Tokens.disabledText
                                }
                            }
                            Badge {
                                variant: "neutral"
                                text: "即将支持"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Text {
                            width: parent.width
                            text: "v0.1 按整块盘规划：1 MiB 对齐 + 系统分区 512 MiB + 数据分区占剩余。"
                                  + "调整分区大小要后端先支持，见 tech/07 §6 的 issue。"
                            font: Tokens.small
                            color: Tokens.textFaint
                            wrapMode: Text.WordWrap
                        }

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s2
                            Text {
                                text: "目标盘"
                                font: Tokens.body
                                color: Tokens.text
                                Layout.preferredWidth: 180
                            }
                            Text {
                                text: "在「选择系统磁盘」那一页选"
                                font: Tokens.small
                                color: Tokens.textFaint
                            }
                            Item { Layout.fillWidth: true }
                        }

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s2
                            Text {
                                text: "文件系统"
                                font: Tokens.body
                                color: Tokens.disabledText
                                Layout.preferredWidth: 180
                            }
                            Rectangle {
                                Layout.preferredWidth: 160
                                Layout.preferredHeight: 44
                                radius: Tokens.rControl
                                color: Tokens.disabledBg
                                border.width: 1
                                border.color: Tokens.border
                                Text {
                                    anchors.centerIn: parent
                                    text: "ext4"
                                    font: Tokens.technical
                                    color: Tokens.disabledText
                                }
                            }
                            Badge {
                                variant: "neutral"
                                text: "即将支持"
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                // ── 系统 ────────────────────────────────────────────
                Card {
                    width: parent.width
                    title: "系统"

                    Column {
                        width: parent.width
                        spacing: Tokens.s3

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s3

                            Field {
                                fieldWidth: 360
                                label: "语言"
                                text: panel.language
                                onEdited: {
                                    panel.language = text;
                                    panel.recount();
                                }
                            }
                            Field {
                                fieldWidth: 360
                                label: "时区"
                                text: panel.timezone
                                onEdited: {
                                    panel.timezone = text;
                                    panel.recount();
                                }
                            }
                        }

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s3

                            Field {
                                fieldWidth: 360
                                label: "键盘布局"
                                text: panel.keyboard
                                readOnly: true
                                help: "v0.1 固定 us（后端写死 KEYMAP=us，见 tech/07 §6 的 issue 4）。"
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                // ── 账户 ────────────────────────────────────────────
                Card {
                    width: parent.width
                    title: "账户"

                    Column {
                        width: parent.width
                        spacing: Tokens.s3

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s3

                            Field {
                                fieldWidth: 360
                                label: "用户名"
                                text: panel.userName
                                onEdited: {
                                    panel.userName = text;
                                    panel.recount();
                                }
                            }
                            Field {
                                fieldWidth: 360
                                label: "主机名"
                                text: panel.hostName
                                onEdited: {
                                    panel.hostName = text;
                                    panel.recount();
                                }
                            }
                        }

                        RowLayout {
                            width: parent.width
                            spacing: Tokens.s2

                            Rectangle {
                                Layout.alignment: Qt.AlignVCenter
                                width: 22
                                height: 22
                                radius: 6
                                color: panel.setRootPassword ? Tokens.accentAction : Tokens.cardBg
                                border.width: panel.setRootPassword ? 0 : 1
                                border.color: Tokens.borderField

                                Icon {
                                    anchors.centerIn: parent
                                    visible: panel.setRootPassword
                                    name: "check"
                                    size: 15
                                    color: Tokens.textOnAccent
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        panel.setRootPassword = !panel.setRootPassword;
                                        panel.recount();
                                    }
                                }
                            }
                            Text {
                                Layout.alignment: Qt.AlignVCenter
                                text: "给 root 设密码（默认保持锁定，只用 sudo）"
                                font: Tokens.body
                                color: Tokens.text
                                wrapMode: Text.WordWrap
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                // ── 安装方式 ────────────────────────────────────────
                Card {
                    width: parent.width
                    title: "安装方式"

                    Column {
                        width: parent.width
                        spacing: Tokens.s2

                        Repeater {
                            model: [
                                {
                                    k: "只做分区",
                                    v: "后端 --steps 已支持，GUI 未接"
                                },
                                {
                                    k: "跳过写入引导项",
                                    v: "后端 --steps 已支持，GUI 未接"
                                },
                                {
                                    k: "跳过装包（留空系统）",
                                    v: "后端 --steps 已支持，GUI 未接"
                                },
                                {
                                    k: "LUKS 全盘加密",
                                    v: "v0.1 明确不做"
                                },
                                {
                                    k: "LVM / btrfs 子卷",
                                    v: "v0.1 明确不做"
                                },
                                {
                                    k: "保留已有系统（双系统）",
                                    v: "v0.1 明确不做"
                                },
                                {
                                    k: "BIOS(legacy) 引导",
                                    v: "v0.1 只支持 UEFI"
                                }
                            ]
                            delegate: RowLayout {
                                required property var modelData
                                width: parent.width
                                spacing: Tokens.s2

                                Text {
                                    text: modelData.k
                                    font: Tokens.body
                                    color: Tokens.disabledText
                                    Layout.preferredWidth: 220
                                }
                                Text {
                                    text: modelData.v
                                    font: Tokens.small
                                    color: Tokens.textFaint
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        Text {
                            width: parent.width
                            text: "这些是高级安装**将来**会长出来的地方，现在都还没有实现 —— "
                                  + "所以这里只列出来，不画成能点的开关。"
                            font: Tokens.small
                            color: Tokens.textFaint
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }
}
