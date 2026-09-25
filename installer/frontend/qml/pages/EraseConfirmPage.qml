// 确认擦除页 —— 从「选择系统磁盘」拆出来的（2026-09-25）。
//
// 版式与其余各页**同一套**：不要页头标题、顶部一个大图标、内容全在一张主卡里。
//
//                          [ 警示图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 确认擦除                                       │
//        │ ┌──────────────────────────────────────────┐ │
//        │ │ ✕ 盘上现有数据将全部丢失，且无法恢复。      │ │  ← 危险块（内嵌）
//        │ │   包括其它操作系统、个人文件与恢复分区……    │ │
//        │ └──────────────────────────────────────────┘ │
//        │ 设备：/dev/vda                                │
//        │ 请原样输入设备路径以确认                       │
//        │ [ /dev/vda            ]                      │
//        └──────────────────────────────────────────────┘
//        返回                          [擦除这块盘并继续]
//
// ── 为什么单独一屏 ─────────────────────────────────────────────────
// 选盘页的每块盘要摊开「里面有什么」（型号 / 分区图 / 摘要），行变高之后一屏
// 装不下这个不可逆动作的守卫；而这个动作本来也不该和「挑盘」挤在一起 ——
// 挑盘是浏览，确认是签字。
//
// ── 守卫一字未改 ───────────────────────────────────────────────────
// 「逐字输入设备路径」与 [cli.py](../../../backend/mipl_installer/cli.py) 里那套
// 是同一种语义：不可撤销的动作，成本要落在**动作本身**上，而不是多点几下。
// 主按钮只有在这里、且输入完全一致时才可点（这一处**故意**保留置灰 —— 它守的是
// 不可逆动作，不是「下一步」）。
//
// 与选盘页的关系：从选盘页带过来 `device`，这一页不改盘、也不画方案（方案在
// `PartitionPage.qml`）—— 它只回答一件事：**你确定要擦这块盘吗**。

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
    // 与选盘页同宽（默认 880）—— 两页是同一条链上的前后两屏

    /// 选盘页带过来的设备（真身由 shell 传）
    property string device: "/dev/vda"
    //: 用户逐字输入的内容
    property string typed: ""

    readonly property bool confirmed: typed.trim() === device && device !== ""

    primaryText: "擦除这块盘并继续"
    primaryDanger: true
    primaryEnabled: page.confirmed

    signal confirmedRequested(string device)
    signal backRequested()

    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "triangle-alert"
            size: 52
            color: Tokens.danger
        }

        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）——
            // 曾经这几页为了多塞一行压到 12，导致卡片内容左缘比别人少 12px，已统一
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s1
            title: "确认擦除"

            Column {
                width: parent.width
                spacing: Tokens.s2

                // 危险信息三件套同现：警示图标（页顶）+ 危险色 + 说清后果的文字。
                // 颜色只是加强，不是唯一的信息载体（见 tech/07 §2.1 第 2 条）。
                Alert {
                    width: parent.width
                    variant: "danger"
                    title: "盘上现有数据将全部丢失，且无法恢复。"
                    message: "包括其它操作系统、个人文件与恢复分区。这一步之后无法撤销，"
                           + "安装器也不提供「缩小已有分区」这类操作。"
                }

                // 设备本身要露脸：确认的是**这一块**，不是「某一块」
                Text {
                    text: "设备：" + page.device
                    font: Tokens.technical
                    color: Tokens.text
                }

                Field {
                    // 输入的是一个短设备路径，不该铺满 880 的行宽
                    fieldWidth: Math.min(parent.width, 420)
                    fieldHeight: 44
                    label: "请原样输入设备路径以确认"
                    placeholder: page.device
                    text: page.typed
                    error: page.typed !== "" && !page.confirmed
                           ? "与设备路径不一致。要放弃就点「返回」。" : ""
                    onEdited: page.typed = text
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.confirmedRequested(page.device)
    onBackClicked: page.backRequested()
}
