// 时区页 —— 与语言页 / 键盘页同一套：**大图标 + 一张主卡片**，不要页头。
//
//                          [ 时钟图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 时区                                           │
//        │ [ 筛选时区（城市或地区）                     ] │
//        │ ┌──────────────────────────────────────┐  ▐  │
//        │ │ ◉ Asia/Shanghai            UTC+08:00  │  ▐  │  ← 列表自己滚
//        │ │ ○ Asia/Tokyo               UTC+09:00  │  ▐  │
//        │ │ ○ Asia/Seoul               UTC+09:00  │  ▐  │
//        │ │ ○ Asia/Singapore           UTC+08:00  │  ▐  │
//        │ │ ○ Asia/Bangkok             UTC+07:00  │  ▐  │
//        │ │ ○ Asia/Jakarta             UTC+07:00  │  ▐  │
//        │ │ ○ Asia/Manila              UTC+08:00  │  ▐  │
//        │ └──────────────────────────────────────┘  ▐  │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// ── 这一页**不做**什么（都是刻意的）──────────────────────────────────
//
// 1. **不放世界地图。** 别的安装器常用「点地图选时区」，我们不做：地图要画边界，
//    而地图与地名在不同司法辖区有各自的规范与审批要求 —— 那不是安装器该承担的东西，
//    也不是靠改代码能规避的。**没有地图，这一页就不涉及任何边界表述。**
//
// 2. **不放原始 tzdata 名单里的敏感地名。** tzdata 里有一批时区名本身带政治表述
//    （同一片地方的不同叫法、有争议地区的归属写法）。本原型只放**地名中性**的常见项；
//    真正要发布的名单应当是**一份经维护者审定的产物**，不是把 `timedatectl
//    list-timezones`（本机 598 条）原样倒出来 —— 这一点连同「怎么规避」见
//    tech/07 与 06 的登记项。
//
// 3. **列表里显示的是 IANA id，不是我们自己写的中文名。** 这是有意的取舍：
//    显示名一旦由我们撰写，**风险就从 tzdata 转到了我们身上**（哪个地方叫什么、
//    算不算独立条目，都是表述）。照实显示系统自己的标识符（`Asia/Shanghai`），
//    我们只呈现、不撰写。要加中文名，必须先有一份**审过的**名字表（见下面的待定项）。
//
// 4. **右边那列偏移是「当前」偏移，不是常量。** 夏令时地区的偏移一年里会变
//    （Europe/Paris 现在 +02:00，冬天 +01:00）。它只用来帮用户定位「我这儿是几点」，
//    真正写进系统的是 id —— 系统拿到 id 之后由 tzdata 自己处理夏令时。
//    数值是渲染当天用 `zoneinfo` 算的（本机 2026-09-25）。
//
// ── 与后端的关系 ─────────────────────────────────────────────────────
// 时区**后端已经支持**：`cli.py:63` 有 `--timezone`（默认 `Asia/Shanghai`），
// `TargetConfig.timezone` 在 `configure.py` 里落成 `/etc/localtime` 的软链。
// 缺的是两件与界面有关的事（见 tech/07 §6）：
//   · 后端要能给出**经审定的**候选名单（前端不写死，理由同语言页）；
//   · 写 `/etc/localtime` 之前要校验目标存在 —— 现在传错名字是**静默**产生悬空软链。

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

    /// 结构与语言 / 键盘两页一致：`id` 会写进系统，`offset` 只作定位用。
    /// `Asia/Shanghai` 置顶 —— 它是后端默认值，也是这一页默认选中的那个，
    /// 置顶能保证「不用滚就看得见自己选的是什么」。
    property var zones: [
        { id: "Asia/Shanghai", offset: "UTC+08:00" },
        { id: "Asia/Tokyo", offset: "UTC+09:00" },
        { id: "Asia/Seoul", offset: "UTC+09:00" },
        { id: "Asia/Singapore", offset: "UTC+08:00" },
        { id: "Asia/Bangkok", offset: "UTC+07:00" },
        { id: "Asia/Jakarta", offset: "UTC+07:00" },
        { id: "Asia/Manila", offset: "UTC+08:00" },
        { id: "Asia/Kolkata", offset: "UTC+05:30" },
        { id: "Asia/Karachi", offset: "UTC+05:00" },
        { id: "Asia/Dubai", offset: "UTC+04:00" },
        { id: "Europe/Istanbul", offset: "UTC+03:00" },
        { id: "Europe/Moscow", offset: "UTC+03:00" },
        { id: "Europe/London", offset: "UTC+01:00" },
        { id: "Europe/Paris", offset: "UTC+02:00" },
        { id: "Europe/Berlin", offset: "UTC+02:00" },
        { id: "Europe/Madrid", offset: "UTC+02:00" },
        { id: "Europe/Rome", offset: "UTC+02:00" },
        { id: "Europe/Warsaw", offset: "UTC+02:00" },
        { id: "Europe/Stockholm", offset: "UTC+02:00" },
        { id: "America/New_York", offset: "UTC-04:00" },
        { id: "America/Chicago", offset: "UTC-05:00" },
        { id: "America/Denver", offset: "UTC-06:00" },
        { id: "America/Los_Angeles", offset: "UTC-07:00" },
        { id: "America/Sao_Paulo", offset: "UTC-03:00" },
        { id: "America/Mexico_City", offset: "UTC-06:00" },
        { id: "Australia/Sydney", offset: "UTC+10:00" },
        { id: "Australia/Perth", offset: "UTC+08:00" },
        { id: "Pacific/Auckland", offset: "UTC+12:00" },
        { id: "Africa/Cairo", offset: "UTC+03:00" },
        { id: "Africa/Johannesburg", offset: "UTC+02:00" },
        { id: "UTC", offset: "UTC+00:00" }
    ]

    /// 选中的是哪个 id（不是第几行）—— 列表会被筛选改变行数，记下标会错位
    property string selectedZone: "Asia/Shanghai"

    property string query: ""

    /// 按 id 与 offset 一起匹配：输入「shanghai」「东京」的拼音找不到，
    /// 但输入 `+08` / `tokyo` 能命中 —— 在只有 id 可用的情况下，这已经最实用
    readonly property var filteredZones: {
        var q = query.trim().toLowerCase();
        if (q === "")
            return zones;
        var out = [];
        for (var i = 0; i < zones.length; i++) {
            if (zones[i].id.toLowerCase().indexOf(q) >= 0
                    || zones[i].offset.toLowerCase().indexOf(q) >= 0)
                out.push(zones[i]);
        }
        return out;
    }

    readonly property int rowHeight: 44
    readonly property int rowSpacing: Tokens.s1

    /// 与语言 / 键盘页同一笔账：图标 52 + 间距 24 + 卡片内边距 24 + 卡片标题 27
    /// + 标题与内容间距 8 + 筛选框 44 + 筛选框与列表间距 16 = 195，预留 200
    readonly property int fixedChrome: 224
    readonly property int visibleRows:
        Math.max(2, Math.floor((page.contentAvailableHeight - page.fixedChrome
                                + page.rowSpacing) / (page.rowHeight + page.rowSpacing)))
    readonly property real listHeight:
        visibleRows * page.rowHeight + (visibleRows - 1) * page.rowSpacing

    readonly property real listContentHeight:
        filteredZones.length * page.rowHeight
        + Math.max(0, filteredZones.length - 1) * page.rowSpacing

    // 这一页现在是**高级安装的分支**（语言 / 键盘 / 时区 / 主机名 四项之一），
    // 不是主流程里的下一步 —— 所以是「完成」，不是「继续」（2026-09-25 评审）。
    primaryText: "完成"

    signal chosen(string zone)
    signal backRequested()

    onQueryChanged: zoneFlick.contentY = 0

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "clock"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）——
            // 曾经这几页为了多塞一行压到 12，导致卡片内容左缘比别人少 12px，已统一
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s1
            title: "时区"

            Column {
                width: parent.width
                spacing: Tokens.s2

                Field {
                    fieldWidth: parent.width
                    fieldHeight: 44
                    label: ""
                    placeholder: "筛选时区（城市或 UTC 偏移）"
                    text: page.query
                    onEdited: page.query = text
                }

                Item {
                    id: listPanel
                    width: parent.width
                    height: page.listHeight

                    Flickable {
                        id: zoneFlick
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
                                model: page.filteredZones
                                delegate: Rectangle {
                                    id: zoneRow
                                    required property int index
                                    required property var modelData

                                    readonly property bool chosen:
                                        zoneRow.modelData.id === page.selectedZone

                                    width: parent.width
                                    height: page.rowHeight
                                    radius: Tokens.rControl
                                    color: zoneRow.chosen ? Tokens.accentTint : "transparent"

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: page.selectedZone = zoneRow.modelData.id
                                    }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: Tokens.s2
                                        anchors.rightMargin: Tokens.s2
                                        spacing: Tokens.s2

                                        Rectangle {
                                            Layout.alignment: Qt.AlignVCenter
                                            width: 16
                                            height: 16
                                            radius: 8
                                            color: "transparent"
                                            border.width: zoneRow.chosen ? 5 : 2
                                            border.color: zoneRow.chosen
                                                          ? Tokens.accentAction
                                                          : Tokens.borderField
                                        }

                                        // IANA id：界面显示什么，系统里就是什么
                                        Text {
                                            text: zoneRow.modelData.id
                                            font: Tokens.technical
                                            color: zoneRow.chosen ? Tokens.accentAction
                                                                  : Tokens.text
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            visible: zoneRow.modelData.id === "Asia/Shanghai"
                                            text: "默认"
                                            font: Tokens.small
                                            color: Tokens.textFaint
                                            Layout.alignment: Qt.AlignVCenter
                                        }

                                        // **当前**偏移，只作定位用；写进系统的是上面的 id
                                        Text {
                                            text: zoneRow.modelData.offset
                                            font: Tokens.technicalSmall
                                            color: Tokens.textFaint
                                            Layout.alignment: Qt.AlignVCenter
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Tokens.s2
                        anchors.top: parent.top
                        anchors.topMargin: Tokens.s2
                        visible: page.filteredZones.length === 0
                        text: "没有匹配的时区 —— 换个词，或清空筛选看全部。"
                        font: Tokens.small
                        color: Tokens.textMuted
                    }

                    ScrollBar {
                        flickable: zoneFlick
                        x: listPanel.width - width
                        y: 0
                        height: listPanel.height
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.chosen(page.selectedZone)
    onBackClicked: page.backRequested()
}
