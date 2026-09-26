// 选择系统磁盘 —— 重写版（2026-09-25）。
//
// 版式与其余各页**同一套**：不要页头标题、顶部一个大图标、内容全在一张主卡里、
// 返回在左上角、主按钮在行动区。
//
//                          [ 硬盘图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 系统磁盘                                       │
//        │ 整块盘会被重新分区，上面原有的一切都会被清除。   │
//        │ ┌──────────────────────────────────────┐  ▐  │
//        │ │ ◉ /dev/vda                            │  ▐  │  ← 列表自己滚
//        │ │   QEMU HARDDISK            40.0 GiB   │  ▐  │
//        │ │   [────────────────────────────────]  │  ▐  │
//        │ │   整块未使用                           │  ▐  │
//        │ ├──────────────────────────────────────┤  ▐  │
//        │ │ ○ /dev/nvme0n1   [正在使用][已有分区表]│  ▐  │
//        │ │   Samsung SSD 990 PRO 2TB   1.8 TiB   │  ▐  │
//        │ │   [▬][▬▬▬▬▬▬▬][───────────────────]   │  ▐  │
//        │ │   EFI 100 MiB · Windows (NTFS) 200 GiB│  ▐  │
//        │ └──────────────────────────────────────┘  ▐  │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// ── 为什么每块盘要摊开「里面有什么」──────────────────────────────
// 用户分不清 `/dev/nvme0n1` 与 `/dev/nvme1n1` 哪个是自己的 Windows 盘 ——
// 这正是整盘擦除**最容易擦错**的地方。所以每块盘给出三样能认出来的东西：
//   1. 型号与容量（人对「我这个是三星 2T」有印象，对 nvme0n1 没有）；
//   2. **一张按容量的分区图**：盘上现有每个分区在条上的位置与大小；
//   3. 一行文字摘要：`EFI 100 MiB · Windows (NTFS) 200 GiB · 未分配 1.6 TiB`。
// 数据都来自后端（`disk.py` 的 sysfs 探测 + `blkid` 读文件系统），前端不推导。
//
// ── 铁律：界面上每个字都必须是后端能**确证**的事实 ────────────────────
// 这一页曾经写过「EFI 100 MiB · **Windows** (NTFS) 200 GiB」与「整盘一个分区
// （ISO9660）—— **像是启动盘**」。那是前端替后端下结论：NTFS 不等于 Windows，
// ISO9660 也不等于启动盘 —— 后端要拿什么保证这两句话是对的？
//
// 所以口径是：**只显示能从系统里读出来的东西**，每条都能指出出处：
//   · 设备 / 型号 / 容量 / 可移动    → sysfs（`/sys/block/*`）
//   · 分区表类型、每个分区的类型与大小 → GPT/MBR 分区表
//   · 文件系统类型与卷标              → `blkid`（读超级块，**不挂载**）
//   · 「正在使用」                    → 它就是当前 Live 介质的来源
//   · 「太小」                        → 一条容量阈值
// 推断出来的话一律不写；宁可少说一句，不能让界面上出现后端担保不了的话。
//
// ── 这一页不管什么 ───────────────────────────────────────────────
// · **不画分区方案**：那是「磁盘分区」页（`PartitionPage.qml`）的事。
// · **不做擦除确认**：拆到 `EraseConfirmPage.qml`（逐字输入设备路径那道守卫）。
// · **不写「已经替你选好」这类说明**：只有一块可用盘时仍然自动选中（省一次点击），
//   但不再用一行字解释 —— 选中的圈本身就是反馈。
//
// ── 重写修掉的旧问题（记在这里，免得被当成「换了个样式」）────────────
// 重写前这一页是 PageShell 之前的写法：自己在 Window 上挂了两个按钮（于是浮在
// 窗口左上角）、页面底部还留着一个**没有文字的主按钮**，内容也超出可视区 300+px。
//
// ── 数据来自后端（2026-09-26）─────────────────────────────────────────
// `Backend.candidates()` 给候选盘：sysfs 枚举 + `blkid` 补文件系统类型与卷标。
// 这一页**不读 sysfs、不数分区、不算容量比例** —— 记录的字段形状由
// `bridge/records.py` 定下（`path/model/size/summary/segments/selectable/badges`）。
// 下面的 `candidates` 默认值只在**没有后端**时生效（取图与流程烟测要可复现的图）。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    title: ""
    subtitle: ""
    backText: "返回"
    // 宽度用**默认值**（Tokens.contentMaxWidth = 880，左右各 200）——
    // 重写时我照抄了列表页的 660，把外边距从 200 撑成了 310，已改回。
    // 660 那几页（网络 / 语言 / 键盘 / 时区）是「一列短条目」的形态，与这张
    // 四列（设备 / 型号 / 容量 / 状态）的盘表不是一回事。

    primaryText: "继续"
    primaryEnabled: page.disk !== null

    signal chosen(string device)
    signal backRequested()

    // ── 数据 ──────────────────────────────────────────────────────────
    /// `segments` 是盘上现有的分区（按容量比例画条），`summary` 是同一件事的文字版。
    /// 两者同源：条给一眼扫的人，文字给要读清楚的人。
    property var candidates: [
        {
            path: "/dev/vda",
            model: "QEMU HARDDISK",
            size: "40.0 GiB",
            summary: "整块未使用",
            segments: [
                {
                    kind: "free",
                    share: 1.0
                }
            ],
            selectable: true,
            badges: []
        },
        {
            path: "/dev/nvme0n1",
            model: "Samsung SSD 990 PRO 2TB",
            size: "1.8 TiB",
            summary: "EFI 100 MiB · NTFS 200 GiB · 未分配 1.6 TiB",
            segments: [
                {
                    kind: "efi",
                    share: 0.00005
                },
                {
                    kind: "os",
                    share: 0.108
                },
                {
                    kind: "free",
                    share: 0.89195
                }
            ],
            selectable: false,
            badges: [
                {
                    t: "正在使用",
                    v: "danger"
                },
                {
                    t: "已有分区表",
                    v: "warning"
                }
            ]
        },
        {
            path: "/dev/sdb",
            model: "SanDisk Cruzer Blade",
            size: "14.3 GiB",
            summary: "整盘一个分区（ISO9660）",
            segments: [
                {
                    kind: "os",
                    share: 1.0
                }
            ],
            selectable: false,
            badges: [
                {
                    t: "太小",
                    v: "danger"
                },
                {
                    t: "可移动设备",
                    v: "warning"
                }
            ]
        },
        {
            path: "/dev/sdc",
            model: "WDC WD20EZBX-00A",
            size: "1.8 TiB",
            summary: "整盘一个 ext4 分区（卷标 DATA）",
            segments: [
                {
                    kind: "os",
                    share: 1.0
                }
            ],
            selectable: true,
            badges: [
                {
                    t: "已有分区表",
                    v: "warning"
                }
            ]
        }
    ]

    readonly property var usable: {
        var out = [];
        for (var i = 0; i < candidates.length; i++) {
            if (candidates[i].selectable)
                out.push(candidates[i]);
        }
        return out;
    }

    /// 恰好一块可用盘 → 自动选中（省一次点击，不解释）
    readonly property bool autoSelected: usable.length === 1

    property int selectedIndex: -1
    readonly property var disk: selectedIndex >= 0 ? candidates[selectedIndex] : null

    Component.onCompleted: {
        if (autoSelected)
            selectedIndex = candidates.indexOf(usable[0]);
    }

    // ── 列表的排版预算（与语言 / 键盘 / 时区三页同一套算法）──────────────
    /// 一行 = 设备行 24 + 间距 6 + 型号行 18 + 间距 6 + 分区条 12 + 间距 6
    ///      + 摘要行 18 + 行内上下留白 8 = 98
    readonly property int rowHeight: 98
    readonly property int rowSpacing: Tokens.s1
    /// 卡片里除列表以外的固定部分：图标 52 + 图标与卡片间距 24 + 卡片上下内边距 48
    /// + 卡片标题 27 + 标题与内容间距 8 + 后果说明 21 + 说明与列表间距 16 = 196
    readonly property int fixedChrome: 200
    readonly property int visibleRows:
        Math.max(1, Math.floor((page.contentAvailableHeight - page.fixedChrome
                                + page.rowSpacing) / (page.rowHeight + page.rowSpacing)))
    readonly property real listHeight:
        visibleRows * page.rowHeight + (visibleRows - 1) * page.rowSpacing
    readonly property real listContentHeight:
        candidates.length * page.rowHeight
        + Math.max(0, candidates.length - 1) * page.rowSpacing

    /// 分区图上每段的颜色：先能认出是什么，再谈好看
    function segmentColor(kind) {
        if (kind === "efi")
            return Tokens.accentDecor;          // 引导分区
        if (kind === "os")
            return Tokens.accentBorder;         // 盘上已有的分区（系统 / 数据 / 启动盘）
        // 未分配用 border 而不是 subtleBg：后者压在白卡上几乎看不见，
        // 于是「空盘」那一条会变成一片空白 —— 而空盘恰恰最该一眼看出来
        return Tokens.border;
    }

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
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）——
            // 曾经这几页为了多塞一行压到 12，导致卡片内容左缘比别人少 12px，已统一
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s1
            title: "系统磁盘"

            Column {
                width: parent.width
                spacing: Tokens.s2

                // 后果说明：它是**事实**（会发生什么），不是操作提示，所以留着。
                // 全靠颜色传达不行（见 tech/07 §2.1 第 2 条），文字在这里。
                Text {
                    width: parent.width
                    visible: page.usable.length > 0
                    text: "整块盘会被重新分区，上面原有的一切都会被清除。"
                    font: Tokens.small
                    color: Tokens.danger
                    wrapMode: Text.WordWrap
                }

                // 零块可用盘：给自检提示，不给一个空表格
                Alert {
                    width: parent.width
                    visible: page.usable.length === 0
                    variant: "warning"
                    title: "安装器看不到任何可用的整块盘"
                    message: "被排除的盘在下面列出了原因。装不进去时先看它们。"
                }

                Item {
                    id: listPanel
                    width: parent.width
                    height: page.listHeight

                    Flickable {
                        id: diskFlick
                        width: parent.width - 12
                        height: parent.height
                        contentWidth: width
                        // 自己按行数算，不读容器的 implicit 尺寸（那个在抛光阶段才定）
                        contentHeight: page.listContentHeight
                        boundsBehavior: Flickable.StopAtBounds
                        interactive: contentHeight > height
                        clip: interactive
                        pixelAligned: false

                        Column {
                            width: parent.width
                            spacing: page.rowSpacing

                            Repeater {
                                model: page.candidates
                                delegate: Rectangle {
                                    id: diskRow
                                    required property int index
                                    required property var modelData

                                    readonly property bool chosen:
                                        page.selectedIndex === diskRow.index
                                    readonly property bool dim: !diskRow.modelData.selectable

                                    width: parent.width
                                    height: page.rowHeight
                                    radius: Tokens.rControl
                                    color: diskRow.chosen ? Tokens.accentTint : "transparent"
                                    opacity: diskRow.dim ? 0.68 : 1.0

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: diskRow.modelData.selectable
                                        cursorShape: diskRow.modelData.selectable
                                                     ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        onClicked: page.selectedIndex = diskRow.index
                                    }

                                    Column {
                                        anchors.fill: parent
                                        anchors.leftMargin: Tokens.s2
                                        anchors.rightMargin: Tokens.s2
                                        anchors.topMargin: 4
                                        anchors.bottomMargin: 4
                                        spacing: 6

                                        // ── 一：设备 + 状态胶囊 ───────────
                                        RowLayout {
                                            width: parent.width
                                            spacing: Tokens.s2

                                            Rectangle {
                                                Layout.alignment: Qt.AlignVCenter
                                                width: 16
                                                height: 16
                                                radius: 8
                                                color: "transparent"
                                                border.width: diskRow.chosen ? 5 : 2
                                                border.color: diskRow.chosen
                                                              ? Tokens.accentAction
                                                              : (diskRow.dim
                                                                 ? Tokens.disabledText
                                                                 : Tokens.borderField)
                                            }

                                            Text {
                                                text: diskRow.modelData.path
                                                font: Tokens.bodyStrong
                                                color: diskRow.dim ? Tokens.textMuted
                                                                   : Tokens.text
                                                Layout.alignment: Qt.AlignVCenter
                                            }

                                            Item { Layout.fillWidth: true }

                                            Repeater {
                                                model: diskRow.modelData.badges
                                                delegate: Badge {
                                                    required property var modelData
                                                    variant: modelData.v
                                                    text: modelData.t
                                                    Layout.alignment: Qt.AlignVCenter
                                                }
                                            }
                                        }

                                        // ── 二：型号与容量（人认得出的就是这两个）─
                                        RowLayout {
                                            width: parent.width
                                            spacing: Tokens.s2

                                            Text {
                                                text: diskRow.modelData.model
                                                font: Tokens.technicalSmall
                                                color: Tokens.textFaint
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Text {
                                                text: diskRow.modelData.size
                                                font: Tokens.technicalSmall
                                                color: Tokens.textMuted
                                            }
                                        }

                                        // ── 三：盘上现有分区的比例图 ───────
                                        // 空盘的条只由「未分配」构成，压在白卡上几乎看不
                                        // 见 —— 所以条自己带一道描边，空盘也读得出来
                                        //「这里有一条、整条都没分配」。
                                        Rectangle {
                                            id: segBar
                                            width: parent.width
                                            height: 12
                                            radius: 4
                                            color: Tokens.subtleBg
                                            border.width: 1
                                            border.color: Tokens.border
                                            clip: true

                                            Row {
                                                anchors.fill: parent

                                                Repeater {
                                                    model: diskRow.modelData.segments
                                                    delegate: Rectangle {
                                                        required property var modelData
                                                        width: segBar.width * modelData.share
                                                        height: segBar.height
                                                        color: page.segmentColor(modelData.kind)
                                                    }
                                                }
                                            }
                                        }

                                        // ── 四：同一件事的文字版 ───────────
                                        Text {
                                            width: parent.width
                                            text: diskRow.modelData.summary
                                            font: Tokens.small
                                            color: Tokens.textMuted
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ScrollBar {
                        flickable: diskFlick
                        x: listPanel.width - width
                        y: 0
                        height: listPanel.height
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.chosen(page.disk.path)
    onBackClicked: page.backRequested()
}
