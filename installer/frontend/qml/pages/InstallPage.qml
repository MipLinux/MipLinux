// P4 · 安装进度与日志（重写 2026-09-25，与其余各页统一到 PageShell 那一套）。
//
//                          [ 下载图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 正在安装                                      │
//        │ ▮▮▮▮▮ ▮▮▮▮▮ ▮▮▮▮▮ ▮▮▮▮▮ ▮▮▮▮▮ ▮▮▮▮▮          │  ← 六段＝后端六个阶段
//        │ 03:24 已过去        第 3 / 6 步 · 装包         │
//        │ 正在从镜像源下载并安装软件包      隐藏日志      │
//        │ ┌──────────────────────────────────────────┐ │
//        │ │ $ pacstrap -C /etc/pacman.conf …          │ │  ← 卡片内滚（细滚动条）
//        │ │     ==> 正在从镜像源下载…                  │ │
//        │ └──────────────────────────────────────────┘ │
//        └──────────────────────────────────────────────┘
//                                          [取消安装]
//
// ── 这一页的核心决定：**不显示百分比** ─────────────────────────────────
// 后端事件只到阶段（`events.PHASES` = start / disk / packages / configure / boot / done），
// 装包阶段的细粒度进度根本没有。编一个假进度条爬到 99% 卡住，比诚实的分段更伤信任
// ——「没有实测证据不得声称已验证」那条口径在界面上就是这个意思（tech/07 §P4）。
// 「还活着」由两样**真实**的东西承担：**已用时**（每秒在走）与**滚动日志**
// （后端每条命令都经 `Reporter.command()` 报出来）。
//
// 当前段里那条来回走的浅色带（`ProgressPhase` 里）是唯一的不确定态动画：
// 它表示「在等」，**不表示走到了多少**。
//
// ── 阶段条为什么是六个，不是原来的「磁盘 · 账户 · 安装」三段 ──────────────
// 那三段是旧流程（认盘 / 账户 / 安装）的产物，与后端事件对不上：`start`、
// `configure`、`boot` 三段落在哪里没人说得清。这一页现在**直接照 `events.PHASES`
// 画六段**，下标就是事件里的 `phase` —— 界面上每一段的含义都能指回后端的一行代码
// （同一条口径见 DiskPage 文件头：「界面上每个字都必须是后端能确证的事实」）。
// 段标签（准备 / 磁盘 / 装包 / 配置 / 引导 / 完成）是我们写的中文，**id 是后端的**；
// 改后端 `PHASES` 的名字等于改接口，得先和后端对齐（见 events.py 文件头）。
//
// ── 版面 ─────────────────────────────────────────────────────────────
// · 装到一半**没有「返回」**：要么装完，要么取消（取消走行动区那颗次要按钮）。
// · 日志区的**高度是算出来的**（可用高 − 固定开销），所以页面本身永不滚动；
//   日志比框长时由 `LogView` 内部滚，滚动条就是全项目那一份 4px 细条。
// · 日志**默认展开**：它是这一页唯一的「还活着」证据，折叠起来等于把证据藏了。
//   「渐进披露」针对的是首屏的认知负担，不是这一屏 —— 这一屏本来就只剩「等」。
//   想收起时点右边的「隐藏日志」。
// · 失败时日志强制展开、不再给折叠开关：日志就摊在失败面板下面、可以滚到底，
//   再放一颗「查看完整日志」是在做已经做完的事（「不显示不能用的开关」）。
//
// ⚠️ 失败时**不自动重启安装器**：崩了不该在残骸上接着装（M0 验收口径，05-测试方法 §5）。

import QtQuick
import QtQuick.Layouts
import "../components"
import "../theme"

PageShell {
    id: page

    // 标题交给卡片；装到一半没有「返回」
    title: ""
    subtitle: ""
    backText: ""

    // ── 后端事件（真身由 bridge 层喂进来，见 bridge/README.md）──────────
    /// 后端的 `Event.phase`，取值就是 events.PHASES 里那几个
    property string phase: "packages"
    /// 后端 `Event.message` 原文 —— 界面上这一行不自己编词
    property string currentAction: "正在从镜像源下载并安装软件包"
    /// 后端 `Event.detail` 与经 `Reporter.command()` 报出的命令
    property var logLines: [
        "$ wipefs -a /dev/vda",
        "$ parted /dev/vda … 建立 GPT 与两个分区",
        "$ mkfs.vfat -F 32 -n MIPLINUX /dev/vda1",
        "$ mkfs.ext4 -F -L MIPLINUX /dev/vda2",
        "$ mount /dev/vda2 /mnt",
        "$ pacman-key --gpgdir /mnt/etc/pacman.d/gnupg --init",
        "    目标包清单：…/data/target-packages.x86_64（8 个包）",
        "$ pacstrap -C /etc/pacman.conf -G -M /mnt base linux linux-firmware",
        "    ==> 正在从镜像源下载…"
    ]

    // ── 失败态 ────────────────────────────────────────────────────────
    property bool failed: false
    /// `InstallerError.render()` 的两行：错在哪 + 接下来敲什么
    property string failureMessage: ""
    property string failureHint: ""

    property bool showLog: true

    /// 已用时（秒）。默认不是 0：这一屏在演示/取图时要看起来像真的在装，
    /// 而且安装本来就不可能在第 1 秒被看到。
    property int elapsed: 204

    // ── 后端阶段 → 段 ─────────────────────────────────────────────────
    readonly property var phaseIds: ["start", "disk", "packages", "configure", "boot", "done"]
    readonly property var phaseLabels: ["准备", "磁盘", "装包", "配置", "引导", "完成"]
    readonly property int phaseIndex: Math.max(0, page.phaseIds.indexOf(page.phase))
    readonly property string phaseLabel: page.phaseLabels[page.phaseIndex]

    readonly property string elapsedText: {
        var m = Math.floor(page.elapsed / 60);
        var s = page.elapsed % 60;
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
    }

    Timer {
        interval: 1000
        repeat: true
        running: !page.failed
        onTriggered: page.elapsed += 1
    }

    // ── 行动区 ────────────────────────────────────────────────────────
    /// 跑的时候只有「取消安装」（次要、描边）—— 没有任何「往前一步」的动作，
    /// 所以 PageShell 那颗主按钮整颗不画（`primaryText` 空即隐藏）。
    /// 失败时主按钮是「重试」：重来一次是这一屏唯一的前进方式。
    primaryText: page.failed ? "重试" : ""
    secondaryText: "取消安装"
    secondaryVisible: !page.failed

    signal cancelRequested()
    signal retryRequested()

    // ── 高度预算：日志吃剩下的所有高度 ────────────────────────────────
    //
    // 固定开销（与语言 / 键盘 / 时区三页同一笔账，数值是量出来的，不是估的）：
    //   图标 52 + 图标间距 24 = 76
    //   卡片上下内边距 48 + 标题 29 + 标题间距 16 = 93
    //   阶段条 35 + 间距 16 + 用时行 24 + 间距 16 + 动作行 24 + 间距 16 = 131
    //   小计 300 —— 实测还差 8（行高取整），所以写 308。
    // 失败时多一块错误面板（Alert 自带 48 内边距 + 两行字，量得 128）+ 16 间距 = 144。
    readonly property int fixedChrome: 308
    readonly property int failureChrome: 144
    readonly property real logHeight:
        Math.max(96, page.contentAvailableHeight - page.fixedChrome
                     - (page.failed ? page.failureChrome : 0))

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: page.failed ? "triangle-alert" : "download"
            size: 52
            color: page.failed ? Tokens.danger : Tokens.accentDecor
        }

        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s2
            title: page.failed ? "安装没有完成" : "正在安装"

            Column {
                width: parent.width
                spacing: Tokens.s2

                ProgressPhase {
                    width: parent.width
                    segments: page.phaseLabels
                    current: page.phaseIndex
                    failed: page.failed
                }

                // ── 已用时 + 停在哪一段 ────────────────────────────
                RowLayout {
                    width: parent.width
                    spacing: Tokens.s2

                    Text {
                        text: page.failed ? page.elapsedText + " 后停止"
                                          : page.elapsedText + " 已过去"
                        font: Tokens.technical
                        color: page.failed ? Tokens.danger : Tokens.textMuted
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: (page.failed ? "失败于「" : "第 ")
                              + (page.failed ? page.phaseLabel + "」"
                                             : (page.phaseIndex + 1) + " / "
                                               + page.phaseIds.length + " 步 · " + page.phaseLabel)
                        font: Tokens.small
                        color: page.failed ? Tokens.danger : Tokens.textMuted
                        Layout.alignment: Qt.AlignVCenter
                    }
                }

                // ── 失败面板：错在哪 + 接下来怎么办 ─────────────────
                // 文案**不自造**：两行都来自后端的 InstallerError.render()
                Alert {
                    width: parent.width
                    visible: page.failed
                    variant: "danger"
                    title: page.failureMessage
                    message: page.failureHint
                }

                // ── 当前动作 + 日志开关 ────────────────────────────
                RowLayout {
                    width: parent.width
                    spacing: Tokens.s2

                    Text {
                        text: page.currentAction
                        font: Tokens.bodyStrong
                        color: page.failed ? Tokens.textMuted : Tokens.text
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                    }

                    // 失败时日志强制展开：不再给这个开关（见文件头）
                    RowLayout {
                        visible: !page.failed
                        spacing: Tokens.s1
                        Layout.alignment: Qt.AlignVCenter

                        Icon {
                            name: page.showLog ? "chevron-down" : "chevron-right"
                            size: 11
                            color: Tokens.accentAction
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Text {
                            text: page.showLog ? "隐藏日志" : "查看日志"
                            font: Tokens.small
                            color: Tokens.accentAction
                            Layout.alignment: Qt.AlignVCenter
                        }
                        MouseArea {
                            implicitWidth: Tokens.s2 * 4
                            implicitHeight: Tokens.s2 * 2
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.showLog = !page.showLog
                        }
                    }
                }

                // ── 日志：高度算出来的，滚在它自己里面 ──────────────
                Item {
                    width: parent.width
                    height: page.showLog ? page.logHeight : 0
                    visible: page.showLog

                    LogView {
                        anchors.fill: parent
                        lines: page.logLines
                        autoScroll: true
                        emptyText: "尚无输出"
                    }
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: {
        if (page.failed)
            page.retryRequested();
    }

    onSecondaryClicked: {
        if (!page.failed)
            page.cancelRequested();
    }
}
