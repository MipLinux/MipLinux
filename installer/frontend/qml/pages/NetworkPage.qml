// 网络连接页。
//
// 版式：
//
//                     [ WiFi 图标 ]
//        ┌──────────────────────────────────────┐
//        │ 无线网络                              │  ← 主卡片
//        │ ┌──────────────────────────────────┐ │
//        │ │ ⏻ 有线网络              已连接     │ │  ← 有线是**内嵌**的二级小卡
//        │ │   enp1s0  192.168.1.23           │ │
//        │ └──────────────────────────────────┘ │
//        │ 可用网络 · 5 个            刷新列表   │
//        │ ◉ HomeWiFi-5G     [锁] -48 [已连接]  │  ← 连接状态挂在**条目右侧**
//        │ ┌──────────────────────────────┐     │  ← 选中需要密码的网络 →
//        │ │ 这个网络需要密码                │     │     密码框贴着这一行展开,
//        │ │ [ 输入无线密码 ]              │     │     同一块底色，不是另起一块
//        │ └──────────────────────────────┘     │
//        │ ○ TP-LINK_2.4G         [锁]  -61     │
//        │ 其它网络（手动输入名称）               │
//        └──────────────────────────────────────┘
//      返回                                              [连接]
//
// **连接状态一律挂在条目右侧**，不在卡片标题下面单起一行：那一行说不清
// 「是有线还是哪张无线网」，还得让人自己对回去；挂在条目上就没有这个对应问题。
//
// **没有「跳过」**：MipLinux 是在线安装镜像，装包全程要走网络，
// 所以「先跳过网、回头再连」不是一条真出路 —— 放一个走得通但不该走的出口，
// 只会把人送进装到一半才发现没网的境地。网络是这一步的前提条件，不是可选项。
//
// **这一页永远出现在流程里**（2026-09-25 评审定的）：无论插没插网线都展示，
// 让人亲眼看到「网络是什么状态」—— 直接跳过这一步会留下不安。
// 于是主按钮跟着状态走：
//   · 没通 → 「连接」（缺密码时点了当场说清，见下）
//   · 通了 → 「继续」（这一页的活儿干完了，往前走）
//
// **「连接」不置灰**：没了「跳过」，置灰就是这个页面上唯一的出路点不动 ——
// 用户只会卡在这儿猜。所以按钮永远可点，缺密码时点了当场说清缺什么
// （呼应 design 口径「未就绪不置灰按钮 —— 置灰让人猜为什么；点了把问题说清」）。
//
// 三条与前几页一致的规矩：按钮统一在行动区、文案只讲事实、能一屏放得下就不滚动
// （小屏放不下时由 `PageShell` 给出可滚动的自定义细条，见该组件）。
// 页头只留「返回」——图标与条目上的状态已经说清「在哪、什么状态」。
//
// ⚠️ 后端没有列网能力（`nmcli` 是现成的，但没人调用它）——
// 这里的 networks 是原型注入值。要真连网需要一条后端 issue，见 tech/07 §6。
// 流程壳（`qml/Main.qml`）现在靠注入 `wiredConnected` 模拟「已连接有线」。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    // 这一页不用大标题与副标题：图标 + 条目上的状态足够。
    title: ""
    subtitle: ""
    backText: "返回"
    // 宽度用**文档默认值**（tech/07 §2.6：pagePadding 48、contentMaxWidth 880）——
    // 卡片 880 宽、左右各留 200。曾经这几页把 660 写死过（当时觉得「一列短条目
    // 880 太散」），但那样与其余各页的外边距不一致，已统一（2026-09-25）。

    // ── 有线：没接就整块不出现 ─────────────────────────────────────────
    // 默认 false：这一页只在**未联网**时出现，插着网线就不会走到这里。
    // 留着这块是因为人可能在这一页上现插网线 —— 插上就该看见它。
    property bool wiredConnected: false
    property string wiredName: "enp1s0"
    property string wiredIPv4: "192.168.1.23"

    // ── 无线 ──────────────────────────────────────────────────────────
    property string connectedSsid: ""
    /// [{ ssid, dbm, secured }]
    property var networks: [
        { ssid: "HomeWiFi-5G", dbm: -48, secured: true },
        { ssid: "TP-LINK_2.4G", dbm: -61, secured: true },
        { ssid: "CMCC-8fJ2", dbm: -67, secured: true },
        { ssid: "Xiaomi_AX3000", dbm: -73, secured: true },
        { ssid: "ChinaNet-guest", dbm: -79, secured: false }
    ]

    property int selectedIndex: 0
    readonly property var selected: selectedIndex >= 0 ? networks[selectedIndex] : null
    property string password: ""

    // ── 列表的排版预算 ─────────────────────────────────────────────────
    // 「行与行拉开距离」与「一页画几行」是同一笔账，必须一起定：
    //   行高 44 + 行距 8 = 每行占 52，画 3 行 = 148px
    // 44 是**可点面积下限**（与下面密码框同一个数、同一套理由），8 是呼吸位 ——
    // 原来 5 行 × 30px、行距 0，圆圈几乎贴在一起，误点率与观感都差。
    // 装不下的一律不画，靠列表末尾的「其它网络」兜 —— 页眉会如实说少列了几个。
    // 小屏（1024×600）放不下时不再硬挤，由 PageShell 给滚动条。
    readonly property int rowHeight: 44
    readonly property int rowSpacing: Tokens.s1
    readonly property int maxRows: 3

    /// 只画信号最强的 maxRows 个。**这是前缀**，所以 delegate 的 index 与
    /// networks 的下标仍然一一对应（selectedIndex 也就不用换算）；
    /// 以后若改成按别的规则排序，这层对应关系要一起改。
    readonly property var visibleNetworks: networks.slice(0, maxRows)
    readonly property bool truncated: networks.length > maxRows

    readonly property bool online: wiredConnected || connectedSsid !== ""
    readonly property bool needsPassword: selected !== null && selected.secured

    /// 「点了连接但还缺密码」—— 不给按钮置灰，改成点完当场说清（见文件头）。
    property bool passwordMissing: false

    // 通了就往前走，没通就连接 —— 这一页永远在流程里（见文件头）
    primaryText: page.online ? "继续" : "连接"

    signal refreshRequested()
    signal connectRequested(string ssid, string password)
    signal manualEntryRequested()
    signal continueRequested()
    signal backRequested()

    /// 主按钮的唯一出口：通了就是「继续」；没通则缺什么就在缺的地方说，
    /// 不靠置灰暗示。
    function submit() {
        if (page.online) {
            page.continueRequested();
            return;
        }
        if (page.needsPassword && page.password.length === 0) {
            page.passwordMissing = true;
            return;
        }
        page.passwordMissing = false;
        page.connectRequested(page.selected ? page.selected.ssid : "", page.password);
    }

    // 信号强度直接用 Lucide 的三档图标（wifi / wifi-low / wifi-zero），
    // 不再自己画弧线凑档位。
    function iconOf(dbm) {
        if (dbm >= -60) return "wifi";
        if (dbm >= -75) return "wifi-low";
        return "wifi-zero";
    }

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        // 顶部一个图标，居中。这一页唯一的图形。
        // 52 而不是 72：这一页的主角是那张卡，图标只负责「这是网络」，
        // 省下的 20px 让给列表行距 —— 一屏放得下优先于装饰。
        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: page.online ? "wifi" : "wifi-off"
            size: 52
            color: page.online ? Tokens.accentDecor : Tokens.textFaint
        }

        // ── 主卡片 ─────────────────────────────────────────────────────
        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）——
            // 曾经这几页为了多塞一行压到 12，导致卡片内容左缘比别人少 12px，已统一
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s1
            title: "无线网络"

            Column {
                width: parent.width
                // 卡片内元素多（内嵌有线 + 页眉 + 网络行），纵向按紧档排
                spacing: Tokens.s1 * 1.5

                // ── 有线：内嵌的二级小卡 ─────────────────────────────
                // 浅一档的底色 + 更小圆角，明确它是主卡里的一个子块，
                // 而不是与主卡并列的第二张卡。
                Rectangle {
                    width: parent.width
                    height: wiredRow.height + Tokens.s2 * 2
                    visible: page.wiredConnected
                    radius: Tokens.rControl
                    color: Tokens.subtleBg
                    border.width: 1
                    border.color: Tokens.border

                    RowLayout {
                        id: wiredRow
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: Tokens.s2
                        anchors.rightMargin: Tokens.s2
                        spacing: Tokens.s2

                        Icon {
                            name: "ethernet-port"
                            size: 16
                            color: Tokens.success
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Column {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                text: "有线网络"
                                font: Tokens.body
                                color: Tokens.text
                            }
                            Text {
                                text: page.wiredName + "   " + page.wiredIPv4
                                font: Tokens.technicalSmall
                                color: Tokens.textFaint
                            }
                        }

                        Text {
                            text: "已连接"
                            font: Tokens.small
                            color: Tokens.success
                            Layout.alignment: Qt.AlignVCenter
                        }
                    }
                }

                // ── 列表页眉：刷新在卡片内部 ────────────────────────
                RowLayout {
                    width: parent.width
                    spacing: Tokens.s2

                    Text {
                        // 扫到几个就报几个 —— 页面上只画前 maxRows 个，但不能让
                        // 「5 个」变成「4 个」：少列的那几个要在这里说清。
                        text: page.truncated
                              ? "可用网络 · " + page.networks.length + " 个（列出信号最强的 "
                                + page.maxRows + " 个）"
                              : "可用网络 · " + page.networks.length + " 个"
                        font: Tokens.small
                        color: Tokens.textFaint
                        Layout.fillWidth: true
                    }

                    Text {
                        text: "刷新列表"
                        font: Tokens.small
                        color: Tokens.accentAction
                        Layout.alignment: Qt.AlignVCenter

                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -Tokens.s2
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.refreshRequested()
                        }
                    }
                }

                // ── 网络行 ─────────────────────────────────────────────
                Column {
                    width: parent.width
                    spacing: page.rowSpacing

                    Repeater {
                        model: page.visibleNetworks
                        delegate: Rectangle {
                            id: netItem
                            required property int index
                            required property var modelData

                            readonly property bool chosen: page.selectedIndex === netItem.index
                            /// 展开条件：这一行被选中，且它需要密码
                            readonly property bool expanded: netItem.chosen && netItem.modelData.secured
                            /// 这个 SSID 就是当前连着的那个
                            readonly property bool connected:
                                page.connectedSsid !== "" && modelData.ssid === page.connectedSsid

                            // 整块（行 + 密码框）共用这一个底色：选中时是一整块高亮，
                            // 而不是「高亮的行」加「另一块灰底的面板」——后者中间那道
                            // 颜色断层会让人看不出密码框属于哪一行。
                            width: parent.width
                            implicitHeight: block.height
                            radius: Tokens.rControl
                            color: netItem.chosen ? Tokens.accentTint : "transparent"

                            Column {
                                id: block
                                width: parent.width
                                spacing: 0

                                Rectangle {
                                    width: parent.width
                                    height: page.rowHeight
                                    color: "transparent"   // 底色由外层整块给

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            // 再点一次已选中的行 = 收起密码框
                                            page.selectedIndex = netItem.chosen ? -1 : netItem.index;
                                            page.password = "";
                                            page.passwordMissing = false;
                                        }
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
                                            border.width: netItem.chosen ? 5 : 2
                                            border.color: netItem.chosen ? Tokens.accentAction
                                                                         : Tokens.borderField
                                        }

                                        Icon {
                                            Layout.alignment: Qt.AlignVCenter
                                            name: page.iconOf(netItem.modelData.dbm)
                                            size: 18
                                            color: netItem.chosen ? Tokens.accentAction : Tokens.textMuted
                                        }

                                        Text {
                                            text: netItem.modelData.ssid
                                            font: Tokens.body
                                            color: Tokens.text
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        // 连接状态挂在**这一行**右侧（理由见文件头）
                                        Text {
                                            visible: netItem.connected
                                            text: "已连接"
                                            font: Tokens.small
                                            color: Tokens.success
                                            Layout.alignment: Qt.AlignVCenter
                                        }

                                        // 锁用矢量图标，不用 emoji（理由见 components/Icon.qml）
                                        Icon {
                                            visible: netItem.modelData.secured
                                            name: "lock"
                                            size: 15
                                            color: Tokens.textMuted
                                            Layout.alignment: Qt.AlignVCenter
                                        }
                                        Text {
                                            visible: !netItem.modelData.secured
                                            text: "开放"
                                            font: Tokens.small
                                            color: Tokens.warning
                                            Layout.alignment: Qt.AlignVCenter
                                        }

                                        Text {
                                            text: netItem.modelData.dbm + " dBm"
                                            font: Tokens.technicalSmall
                                            color: Tokens.textFaint
                                            Layout.alignment: Qt.AlignVCenter
                                        }
                                    }
                                }

                                // ── 展开的密码输入：与上面那行**同一块** ─────
                                Item {
                                    width: parent.width
                                    height: netItem.expanded ? panel.height + Tokens.s2 : 0
                                    clip: true
                                    visible: height > 0

                                    Behavior on height {
                                        NumberAnimation {
                                            duration: Tokens.motionNormal
                                            easing.type: Easing.OutCubic
                                        }
                                    }

                                    Column {
                                        id: panel
                                        x: Tokens.s2
                                        y: 0
                                        width: parent.width - Tokens.s2 * 2
                                        spacing: Tokens.s1

                                        Text {
                                            text: netItem.modelData.secured
                                                  // 不写「（WPA2）」：那是写死的断言，
                                                  // 真身该由 NetworkManager 报的安全类型填
                                                  ? "这个网络需要密码"
                                                  : "开放网络，数据不加密"
                                            font: Tokens.small
                                            color: Tokens.textMuted
                                        }

                                        // 这里的输入框压到 44px：整页最紧的一处，
                                        // 40px 会低于可点面积的下限（见 Field 的注释）
                                        Field {
                                            width: parent.width
                                            fieldWidth: parent.width
                                            fieldHeight: 44
                                            visible: netItem.modelData.secured
                                            label: ""
                                            text: page.password
                                            secret: true
                                            placeholder: "输入无线密码"
                                            onEdited: {
                                                page.password = text;
                                                if (text !== "")
                                                    page.passwordMissing = false;
                                            }
                                        }

                                        // 「点了连接但没填密码」在这里说清 ——
                                        // 而不是把「连接」按钮置灰（见文件头）
                                        Text {
                                            visible: page.passwordMissing && netItem.chosen
                                            width: parent.width
                                            text: "请输入密码"
                                            font: Tokens.small
                                            color: Tokens.danger
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // 隐藏网络：列表末尾的入口，不打断扫描结果
                    Rectangle {
                        width: parent.width
                        height: page.rowHeight
                        radius: Tokens.rControl
                        color: "transparent"

                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: Tokens.s2
                            anchors.verticalCenter: parent.verticalCenter
                            text: "其它网络（手动输入名称）"
                            font: Tokens.body
                            color: Tokens.accentAction

                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -Tokens.s1
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.manualEntryRequested()
                            }
                        }
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    // 只有一条出路：连上。没有「跳过」（理由见文件头）；也不置灰，缺密码由
    // `submit()` 在密码框下说清。
    onPrimaryClicked: page.submit()
    onBackClicked: page.backRequested()
}
