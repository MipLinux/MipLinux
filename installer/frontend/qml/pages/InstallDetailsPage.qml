// 安装详情页 —— **开始安装之前**给用户核对的那一屏（2026-09-25 评审定位置）。
//
//                          [ 清单图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 安装详情                                      │
//        │ 目标盘        /dev/vda · QEMU HARDDISK · 40 GiB│
//        │ 分区          系统分区 512 MiB (vfat) + …      │
//        │ 引导          systemd-boot（UEFI）            │
//        │ 账户          mipl（可用 sudo）               │
//        │ root          保持锁定，用 sudo 提权           │
//        │ 语言·键盘·时区 zh_CN.UTF-8 · us · Asia/Shanghai│
//        │ 主机名        mipl                            │
//        └──────────────────────────────────────────────┘
//        返回                                  [开始安装]
//
// ── 这一页在这条流程里的位置 ──────────────────────────────────────────
//   … → 磁盘 → 分区 → 逐字确认擦除 → 主机名 → 账户 → **安装详情（这一页）** → 安装 → 结束
// 所有决定都做完之后、动盘之前，把「将要装成什么样」摊成一张单子让人**核对**一次。
// 因此账户页的主按钮是「继续」，**「开始安装」在这一页** —— 最后一颗实心按钮属于
// 最后一个确认动作。
//
// ── 评审删掉的两块（别再捡回来）────────────────────────────────────────
// 1. 页头右上角那句状态「还没动盘」。
// 2. 「开始之后」整节（盘会被清掉 / 要联网 / M3 还没装的那三句）。
// 这一屏现在**只有事实**：一行一件事的表，加上一颗「开始安装」。
// 代价说清楚：删掉之后，界面上不再出现「整块盘会被清掉」这句（它在**确认擦除**页
// 说过一次），也不再出现「中文输入法 / CJK 字体 / NVIDIA 驱动由 M3 落地」这句 ——
// 后者现在整条流程里都没有了（要放回来得另找位置，别悄悄塞回这一屏）。
//
// ── 与「确认擦除」页的分工（守卫不重复）────────────────────────────────
// 擦盘那道守卫（逐字输入设备路径）已经在前一屏做过了，这一页**不做第二次** ——
// 同一个动作上叠两道同款守卫只会让人麻木地点过去，那比只有一道更危险
// （同一条理由见 PartitionPage 文件头）。
//
// ── 三条口径 ──────────────────────────────────────────────────────────
// 1. **每个字都是流程里真实选定的值**（由 shell 带进来），前端不推导、不美化 ——
//    与选盘页「后端担保不了的话一律不写」同一条。
// 2. **单列**（评审口径）：标签在左、值在右，一行一件事，不分两栏。
// 3. **页面本身不滚**：卡片内容区按可用高收口，放不下时滚的是卡片里面
//    （与语言 / 键盘 / 时区、账户页同一套，滚动条是全项目那一份 4px 细条）。
//
// ⚠️ 这一页**不是预览日志**：真装的时候会跑哪些命令、走到哪一步，那是安装页的事
// （`InstallPage.qml`，它接后端 events.PHASES 的事件流）。这一页只讲「装成什么样」。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    // 页头只留「返回」（评审删掉了右上角那句状态说明）
    title: ""
    subtitle: ""
    backText: "返回"

    // 一列表格：宽度按内容定
    contentWidth: 660

    primaryText: "开始安装"

    signal installRequested()
    signal backRequested()

    // ── 数据（真身由 shell 从安装流程里带进来）──────────────────────────
    property string targetDisk: "/dev/vda"
    property string diskSummary: "QEMU HARDDISK · 40.0 GiB"
    property string partitionSummary: "系统分区 512 MiB (vfat) + 数据分区（剩余，ext4）"
    property string bootloader: "systemd-boot（UEFI）"
    property string userName: "mipl"
    property bool rootHasPassword: false
    property string localeName: "zh_CN.UTF-8"
    property string keymap: "us"
    property string timezone: "Asia/Shanghai"
    property string hostName: "mipl"

    readonly property var facts: [
        {
            k: "目标盘",
            v: page.targetDisk + " · " + page.diskSummary
        },
        {
            k: "分区",
            v: page.partitionSummary
        },
        {
            k: "引导",
            v: page.bootloader
        },
        {
            k: "账户",
            v: page.userName + "（可用 sudo）"
        },
        {
            k: "root",
            v: page.rootHasPassword ? "设成与账户相同的密码" : "保持锁定，用 sudo 提权"
        },
        {
            k: "语言 · 键盘 · 时区",
            v: page.localeName + " · " + page.keymap + " · " + page.timezone
        },
        {
            k: "主机名",
            v: page.hostName
        }
    ]

    // ── 卡片内容区的滚动（与语言 / 键盘 / 时区、账户页同一套）────────────
    //: 图标 52 + 图标间距 24 + 卡片内边距 48 + 卡片标题 29 + 标题间距 16
    readonly property int fixedChrome: 169
    readonly property real innerHeight:
        Math.max(120, page.contentAvailableHeight - page.fixedChrome)

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "clipboard-list"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s2
            title: "安装详情"

            Item {
                id: detailsPanel
                width: parent.width
                height: Math.min(detailsColumn.implicitHeight, page.innerHeight)

                Flickable {
                    id: detailsFlick
                    // 让出右侧 12px 给滚动条，免得条子压在文字上
                    width: parent.width - 12
                    height: parent.height
                    contentWidth: width
                    contentHeight: detailsColumn.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height
                    clip: interactive
                    pixelAligned: false

                    Column {
                        id: detailsColumn
                        width: parent.width
                        spacing: Tokens.s3

                        // ── 将要装成什么样：一行一件事 ──────────────
                        // 七行**合成一个子列**（内部 s1 行距），不是七个子项：
                        // 外面那层 s3 会把这七行撑开成一大片空隙。表就该密一点。
                        Column {
                            width: parent.width
                            spacing: Tokens.s1

                            Repeater {
                                model: page.facts
                                delegate: RowLayout {
                                    required property var modelData
                                    width: parent.width
                                    spacing: Tokens.s2

                                    Text {
                                        text: modelData.k
                                        font: Tokens.body
                                        color: Tokens.textMuted
                                        Layout.preferredWidth: 156
                                        Layout.alignment: Qt.AlignTop
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        text: modelData.v
                                        font: Tokens.technical
                                        color: Tokens.text
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignTop
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }
                    }
                }

                ScrollBar {
                    flickable: detailsFlick
                    x: detailsPanel.width - width
                    y: 0
                    height: detailsPanel.height
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.installRequested()
    onBackClicked: page.backRequested()
}
