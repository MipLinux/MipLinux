// 语言选择页 —— 欢迎页之后的第一个真决策。
//
// 版式（与网络连接页**完全同一套**：只有大图标 + 一张主卡片，不要页头）：
//
//                          [ 地球图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 系统语言                                       │
//        │ ┌───────────────────┬───────────────────┐    │
//        │ │ ◉ 简体中文  zh_CN… │ ○ 繁體中文  zh_TW… │    │  ← 这一块自己滚
//        │ ├───────────────────┼───────────────────┤  ▐ │     （卡片内滚动条）
//        │ │ ○ English   en_US… │ ○ Čeština  cs_CZ… │  ▐ │
//        │ ├───────────────────┼───────────────────┤  ▐ │     全部 locale 都在这里，
//        │ │ ○ Dansk     da_DK… │ ○ Deutsch  de_DE… │  ▐ │     不做「手动输入」
//        │ ├───────────────────┼───────────────────┤  ▐ │
//        │ │ ○ Ελληνικά  el_GR… │ ○ Español  es_ES… │  ▐ │
//        │ ├───────────────────┼───────────────────┤  ▐ │
//        │ │ ○ Suomi     fi_FI… │ ○ Français fr_FR… │  ▐ │
//        │ ├───────────────────┼───────────────────┤  ▐ │
//        │ │ ○ Magyar    hu_HU… │ ○ Italiano it_IT… │  ▐ │
//        │ └───────────────────┴───────────────────┘    │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// **不放页头标题与副标题**：卡片标题「系统语言」已经说完「这一步选什么」，
// 再加一层大标题只是把同一句话说两遍 —— 与网络页同一条规矩。
//
// ── 三条口径 ─────────────────────────────────────────────────────────
//
// 1. **列全部语言，让列表自己滚。** 本机 `/etc/locale.gen` 有 **500 条** locale，
//    「全部」是这个量级 —— 做「手动输入 locale」等于把最难的一步推给用户。
//    所以：列表容纳全部，卡片高度固定，**只有列表滚**。
//    为什么不是整页滚：整页滚会把图标与卡片标题一起推走，用户滚到一半
//    就不知道自己正在选什么了。视口高由 `PageShell.contentAvailableHeight`
//    倒推并吸附到整行（见下面 `listHeight`），所以 1280×800 与 1024×600 都只
//    有这一根滚动条。
//    ⚠️ 真身里这份名单**不该由前端写死**：它得从目标系统的 `locale.gen` 读出来
//    （与「包清单唯一来源」同一条理由）—— 这是后端要补的能力，见 tech/07 §6 第 5 条。
//
// 2. **安装界面本身只有中文与 English；这里选的是「装好以后」系统的语言。**
//    这不是谦虚，是现状：前端文案全是硬编码中文，全仓库没有 `qsTr` / `QTranslator`。
//    **不在界面上解释这件事**：界面只有中文，需要这句解释的人恰好读不懂它。
//    真要让安装界面跟着切换，那是另一件事（要引 Qt 翻译层），不进 v0.1。
//
// 3. **列表比后端现在能做的宽。** 后端 `TargetConfig.locales` 只硬编码了
//    zh_CN / en_US 两行（configure.py 第 70 行），其它 locale 既不会写进
//    `locale.gen`、也不会 `locale-gen`。
//    ⚠️ 也就是说：**在后端放开 locale 生成之前，这一页只有前两项是真的能生效的**，
//    这是已知的、有 issue 跟着的缺口，不是漏掉的实现。
//
// ── 为什么不画键盘选择 ───────────────────────────────────────────────
// 后端 v0.1 把 `KEYMAP=us` 写死（configure.py 第 103 行）。按「不显示不能用的
// 开关」的口径，它不配一个点了没反应的控件；也**不在界面上写说明文字** ——
// 键盘该是一条能选的真控件，等后端放开 `KEYMAP` 之后再做（issue 待提）。
//
// ── 为什么是两列，而不是网络页那样的单列 ─────────────────────────────
// 语言名短（「日本語」不会像 SSID 那样长到要省略号），一屏内两列能多看一倍、
// 少滚一半。卡片、行高、单选圈、滚动条的写法都与网络页一致，所以看着仍是一家的。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    // 页头只留「返回」：标题与副标题交给卡片（见文件头）
    title: ""
    subtitle: ""
    backText: "返回"
    // 宽度用**文档默认值**（tech/07 §2.6：pagePadding 48、contentMaxWidth 880）——
    // 卡片 880 宽、左右各留 200。曾经这几页把 660 写死过（当时觉得「一列短条目
    // 880 太散」），但那样与其余各页的外边距不一致，已统一（2026-09-25）。

    /// `name` 用**它自己的语言**写：选语言这件事上，把语言名翻译成另一种语言，
    /// 是最容易让人选错的一步。`locale` 就是将来会写进 `LANG=` 的那个值。
    ///
    /// ⚠️ **这份列表在真身里不该由前端写**：本机 `/etc/locale.gen` 有 **500 条**
    /// locale，「全部列出」只能是数据而不是常量 —— 真接线时这份名单由后端从目标
    /// 系统的 `locale.gen` 读出来给前端（与「包清单唯一来源」同一条理由）。
    /// 这里按原型注入，顺序 = 中文两种置顶 + 其余按 locale 代码字典序。
    property var languages: [
        { name: "简体中文", locale: "zh_CN.UTF-8" },
        { name: "繁體中文", locale: "zh_TW.UTF-8" },
        { name: "English", locale: "en_US.UTF-8" },
        { name: "Čeština", locale: "cs_CZ.UTF-8" },
        { name: "Dansk", locale: "da_DK.UTF-8" },
        { name: "Deutsch", locale: "de_DE.UTF-8" },
        { name: "Ελληνικά", locale: "el_GR.UTF-8" },
        { name: "Español", locale: "es_ES.UTF-8" },
        { name: "Suomi", locale: "fi_FI.UTF-8" },
        { name: "Français", locale: "fr_FR.UTF-8" },
        { name: "Magyar", locale: "hu_HU.UTF-8" },
        { name: "Italiano", locale: "it_IT.UTF-8" },
        { name: "日本語", locale: "ja_JP.UTF-8" },
        { name: "한국어", locale: "ko_KR.UTF-8" },
        { name: "Nederlands", locale: "nl_NL.UTF-8" },
        { name: "Norsk", locale: "nb_NO.UTF-8" },
        { name: "Polski", locale: "pl_PL.UTF-8" },
        { name: "Português (Brasil)", locale: "pt_BR.UTF-8" },
        { name: "Português", locale: "pt_PT.UTF-8" },
        { name: "Română", locale: "ro_RO.UTF-8" },
        { name: "Русский", locale: "ru_RU.UTF-8" },
        { name: "Svenska", locale: "sv_SE.UTF-8" },
        { name: "Türkçe", locale: "tr_TR.UTF-8" },
        { name: "Українська", locale: "uk_UA.UTF-8" },
        { name: "Tiếng Việt", locale: "vi_VN.UTF-8" }
    ]

    /// 选中的是**哪个 locale**，不是第几行 —— 列表会被下面的筛选改变行数，
    /// 记下标就会错位（筛掉前面的项，选中项会跳到别人身上）。
    property string selectedLocale: "zh_CN.UTF-8"
    readonly property var selected: {
        for (var i = 0; i < languages.length; i++) {
            if (languages[i].locale === selectedLocale)
                return languages[i];
        }
        return null;
    }

    /// 筛选关键词：就地过滤，**不是**让用户手输 locale ——
    /// `locale.gen` 有 500 条，「全部列出」必须配一个能找到的办法。
    property string query: ""

    /// 语言名与 locale 代码都参与匹配，大小写无关；空查询 = 全部
    readonly property var filteredLanguages: {
        var q = query.trim().toLowerCase();
        if (q === "")
            return languages;
        var out = [];
        for (var i = 0; i < languages.length; i++) {
            if (languages[i].name.toLowerCase().indexOf(q) >= 0
                    || languages[i].locale.toLowerCase().indexOf(q) >= 0)
                out.push(languages[i]);
        }
        return out;
    }

    /// 行高与行距沿用网络页那两个数（44 是可点面积下限，8 是呼吸位），
    /// 这样两页的「选中一块」手感是同一个。
    readonly property int rowHeight: 44
    readonly property int rowSpacing: Tokens.s1

    /// 网格行数（两列，行优先）—— 按**过滤后**的结果算
    readonly property int gridRows: Math.ceil(filteredLanguages.length / 2)

    /// 列表视口高度：**由可用高度倒推，并吸附到整行**。
    ///
    /// 不写死「显示几行」：写死了，小屏就得多滚一整页（图标、卡片标题都被
    /// 推走），而这里要的是**组件滚、页面不滚**。所以先减去卡片外那一圈固定内容：
    ///   固定部分 = 图标 52 + 图标与卡片间距 24 + 卡片上下内边距 48 + 卡片标题 27
    ///            + 标题与内容间距 8 + 筛选框 44 + 筛选框与列表间距 16 = 219（量出来的）
    /// 预留写 224（比实测多 5px 余量，字体度量换机器会差一两像素）。
    /// 再 `floor` 到整行：**不留半行**——半行看着像画坏了，不如少显示一行。
    /// 两行是下限，窗口再小也不至于把列表挤没。
    readonly property int fixedChrome: 224
    readonly property int visibleRows:
        Math.max(2, Math.floor((page.contentAvailableHeight - page.fixedChrome
                                + page.rowSpacing) / (page.rowHeight + page.rowSpacing)))
    readonly property real listHeight:
        visibleRows * page.rowHeight + (visibleRows - 1) * page.rowSpacing

    primaryText: "继续"

    signal chosen(string locale)
    signal backRequested()

    /// 换了筛选词就回到列表顶部：否则内容变短后滚动位置会留在半空
    onQueryChanged: langFlick.contentY = 0

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        // 顶部大图标：这一页唯一的图形，与网络页同一个位置、同一个尺寸
        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "earth"
            size: 52
            color: Tokens.accentDecor
        }

        // ── 主卡片 ─────────────────────────────────────────────────────
        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）——
            // 曾经这几页为了多塞一行压到 12，导致卡片内容左缘比别人少 12px，已统一
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s1
            title: "系统语言"

            Column {
                width: parent.width
                spacing: Tokens.s2

                // ── 筛选框 ─────────────────────────────────────────
                // 500 条里找一种，靠滚是折磨。就地过滤，输入「日本」「ja」「ru」都能命中
                // （名字与 locale 代码一起匹配）。**这不是「让用户手输 locale」** ——
                // 用户不需要知道 `ja_JP.UTF-8` 怎么写，只要会打字就行。
                Field {
                    fieldWidth: parent.width
                    fieldHeight: 44
                    label: ""
                    placeholder: "筛选语言（名字或 locale 代码）"
                    text: page.query
                    onEdited: page.query = text
                }

                // ── 语言列表：**卡片内自己滚** ─────────────────────
                // 为什么是组件滚而不是整页滚：整页滚会把图标、卡片标题
                // 一起推走，用户滚到一半就不知道自己在选什么了；这里只让列表动。
                // 右边留 12px 给滚动条，条子不压在文字上（行内的值都在 s2 里面）。
                Item {
                    id: listPanel
                    width: parent.width
                    height: page.listHeight

                    Flickable {
                        id: langFlick
                        width: parent.width - 12
                        height: parent.height
                        contentWidth: width
                        // 自己按行数算，不读 Grid 的 implicitHeight ——
                        // implicit 尺寸在抛光阶段才定，读它可能停在上一次的值
                        contentHeight: page.gridRows * page.rowHeight
                                       + Math.max(0, page.gridRows - 1) * page.rowSpacing
                        boundsBehavior: Flickable.StopAtBounds
                        interactive: contentHeight > height
                        // 只在能滚时裁：不能滚时留原样，免得把行外的描边切掉
                        clip: interactive
                        pixelAligned: false

                        Grid {
                            id: langGrid
                            width: parent.width
                            columns: 2
                            spacing: page.rowSpacing

                            Repeater {
                                model: page.filteredLanguages
                                delegate: Rectangle {
                                    id: langCell
                                    required property int index
                                    required property var modelData

                                    readonly property bool chosen:
                                        langCell.modelData.locale === page.selectedLocale

                                    // 宽度只有一个来源（langGrid.width），不回头读父项的
                                    // implicitWidth —— 那个写法实测会进 polish 死循环
                                    width: (langGrid.width - langGrid.spacing) / 2
                                    height: page.rowHeight
                                    radius: Tokens.rControl
                                    color: langCell.chosen ? Tokens.accentTint : "transparent"

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: page.selectedLocale = langCell.modelData.locale
                                    }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: Tokens.s2
                                        anchors.rightMargin: Tokens.s2
                                        spacing: Tokens.s2

                                        // 单选圈：与网络页、磁盘页同一个画法
                                        Rectangle {
                                            Layout.alignment: Qt.AlignVCenter
                                            width: 16
                                            height: 16
                                            radius: 8
                                            color: "transparent"
                                            border.width: langCell.chosen ? 5 : 2
                                            border.color: langCell.chosen
                                                          ? Tokens.accentAction
                                                          : Tokens.borderField
                                        }

                                        Text {
                                            text: langCell.modelData.name
                                            font: Tokens.body
                                            color: Tokens.text
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }

                                        // 真正会写进目标系统的那个值：界面上说「日本語」，
                                        // 落到系统里是 ja_JP.UTF-8，两者摆在一行上对得上
                                        Text {
                                            text: langCell.modelData.locale
                                            font: Tokens.technicalSmall
                                            color: Tokens.textFaint
                                            Layout.alignment: Qt.AlignVCenter
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // 过滤后一条都没有：说一句，而不是留一块空白让人以为坏了
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Tokens.s2
                        anchors.top: parent.top
                        anchors.topMargin: Tokens.s2
                        visible: page.filteredLanguages.length === 0
                        text: "没有匹配的语言 —— 换个词，或清空筛选看全部。"
                        font: Tokens.small
                        color: Tokens.textMuted
                    }

                    // 与 PageShell 用的是同一个组件：细条样式只有一份
                    ScrollBar {
                        flickable: langFlick
                        x: listPanel.width - width
                        y: 0
                        height: listPanel.height
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: page.chosen(page.selectedLocale)
    onBackClicked: page.backRequested()
}
