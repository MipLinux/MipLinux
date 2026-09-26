// 磁盘分区页 —— 与语言 / 键盘 / 时区三页同一套：**大图标 + 一张主卡片**，不要页头。
//
//                          [ 硬盘图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 磁盘分区                                       │
//        │ 设备  /dev/vda    QEMU HARDDISK · 40.0 GiB    │
//        │ ┌──────────────────────────────────────────┐ │
//        │ │▌                                          │ │  ← 按容量比例的条
//        │ └──────────────────────────────────────────┘ │
//        │ ● 系统分区            512 MiB      vfat       │
//        │ ● 数据分区            39.5 GiB     ext4       │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// ── 这一页与「选择系统磁盘」是怎么分工的 ─────────────────────────────
// 选盘那页（`DiskPage.qml`）负责「**擦哪块**」：列出候选、自动选中唯一可用的、
// 并且用「逐字输入设备路径」承担那个不可逆动作的守卫。
// 这一页负责「**怎么分**」：把方案画出来给人看一眼。
//
// **不做「技术细节」折叠区**（原来有，2026-09-25 删）：GPT / 对齐 / ESP 类型 / 卷标
// 这些行话对普通安装是噪音（他们只关心「我的东西会不会没」），对高级用户又远远不够
// （他们要的是能改分区表，而 v0.1 不提供）—— 两头都不讨好，那就别放。
//
// **守卫不重复。** 逐字确认只在选盘那页做一次；这一页不做第二次 —— 同一个动作上
// 叠两道同款守卫，只会让人麻木地点过去（那比只有一道更危险）。
//
// ⚠️ 两件事要一起看（都写在 tech/07）：
//   1. v0.1 只有这一套自动方案（1 MiB 对齐 + 512 MiB ESP + 剩余 ext4），
//      **界面上不能改**：改系统分区大小要后端加能力，按「不显示不能用的开关」
//      的口径，这里不画一个点了不生效的输入框。
//   2. 现有的 `DiskPage.qml` 里有一张「将要发生的事」卡，与本页内容重叠 ——
//      拆页还是保留，是需要维护者拍板的事，不在本屏里自作主张。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    title: ""
    subtitle: ""
    backText: "返回"
    // 内容宽**窄一档**（660）：这两页是一列短表单 / 一列短条目，
    // 拉到 880 会变成「两端的字隔着半个屏幕」。宽度按内容定，不是全站一个数
    contentWidth: 660
    // 宽度用**文档默认值**（tech/07 §2.6：pagePadding 48、contentMaxWidth 880）——
    // 卡片 880 宽、左右各留 200。曾经这几页把 660 写死过（当时觉得「一列短条目
    // 880 太散」），但那样与其余各页的外边距不一致，已统一（2026-09-25）。

    // ── 数据（原型注入；真身由后端给，见 tech/07 §6）───────────────────
    property string device: "/dev/vda"
    property string diskModel: "QEMU HARDDISK"
    property string diskSize: "40.0 GiB"

    /// `share` 是**按容量**的比例（512 MiB / 40.0 GiB = 0.0125），
    /// 只用来画那条比例条；`size` 才是给人看的字。两者都由后端算，前端不推导。
    property var partitions: [
        {
            kind: "system",
            name: "系统分区",
            size: "512 MiB",
            fs: "vfat",
            share: 0.0125
        },
        {
            kind: "data",
            name: "数据分区",
            size: "39.5 GiB",
            fs: "ext4",
            share: 0.9875
        }
    ]

    primaryText: "继续"

    signal continueRequested()
    signal backRequested()

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "hard-drive"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s2
            title: "磁盘分区"

            Column {
                width: parent.width
                spacing: Tokens.s3

                // ── 哪块盘 ─────────────────────────────────────────
                RowLayout {
                    width: parent.width
                    spacing: Tokens.s2

                    Text {
                        text: "设备"
                        font: Tokens.small
                        color: Tokens.textFaint
                        Layout.alignment: Qt.AlignVCenter
                    }
                    Text {
                        text: page.device
                        font: Tokens.technical
                        color: Tokens.text
                        Layout.alignment: Qt.AlignVCenter
                    }
                    Text {
                        text: page.diskModel + " · " + page.diskSize
                        font: Tokens.small
                        color: Tokens.textMuted
                        Layout.alignment: Qt.AlignVCenter
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                // ── 按容量比例的条 ─────────────────────────────────
                // 圆角与裁剪都交给外层容器：两段各自不加圆角，接缝才是一条直线。
                // 512 MiB 在 40 GiB 的盘上只有 ~1.2%（约 8px）—— 所以真正说明
                // 「哪段是什么」的是下面那两行图例，条只负责给出**量的直觉**。
                Rectangle {
                    id: bar
                    width: parent.width
                    height: 20
                    radius: 6
                    color: Tokens.subtleBg
                    clip: true

                    Row {
                        anchors.fill: parent

                        Repeater {
                            model: page.partitions
                            delegate: Rectangle {
                                required property var modelData
                                width: bar.width * modelData.share
                                height: bar.height
                                color: modelData.kind === "system" ? Tokens.accentDecor
                                                                    : Tokens.borderField
                            }
                        }
                    }
                }

                // ── 图例：条上那两段分别是什么 ─────────────────────
                Column {
                    width: parent.width
                    spacing: Tokens.s1 * 1.5

                    Repeater {
                        model: page.partitions
                        delegate: RowLayout {
                            required property var modelData
                            width: parent.width
                            spacing: Tokens.s2

                            Rectangle {
                                Layout.alignment: Qt.AlignVCenter
                                width: 10
                                height: 10
                                radius: 5
                                color: modelData.kind === "system" ? Tokens.accentDecor
                                                                   : Tokens.borderField
                            }
                            Text {
                                text: modelData.name
                                font: Tokens.body
                                color: Tokens.text
                                Layout.fillWidth: true
                            }
                            Text {
                                text: modelData.size
                                font: Tokens.technical
                                color: Tokens.textMuted
                                Layout.preferredWidth: 96
                                Layout.alignment: Qt.AlignVCenter
                            }
                            Text {
                                text: modelData.fs
                                font: Tokens.technicalSmall
                                color: Tokens.textFaint
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                    }
                }

            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.continueRequested()
    onBackClicked: page.backRequested()
}
