// 主机名页 —— 从账户页搬出来的单独一页（2026-09-25 评审）。
//
// 版式与语言 / 键盘 / 时区各页**同一套**：大图标 + 一张主卡片，不要页头。
//
//                          [ 网络图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 主机名                                        │
//        │ 这台机器在网络与终端提示符里的名字。            │
//        │ [ mipl ]                                      │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// ── 为什么单独一页 ────────────────────────────────────────────────────
// 账户页改成单列之后，四个字段竖排是 594px，而那一页只有 584px（逐项量过，见
// AccountPage.qml 文件头）。主机名是账户页上唯一**不是决策**的字段（默认 `mipl`），
// 所以给它一页，账户页只管「谁来用这台机器」。搬出来的另一个好处是这一页能把
// 「这台机器叫什么」说清楚 —— 挤在账户页里时那句话是被删掉的（当时是噪音）。
//
// ── 校验 ──────────────────────────────────────────────────────────────
// ⚠️ 后端今天**不校验**主机名：`configure.py` 只把 `cfg.hostname` 原样写进
// `/etc/hostname`。下面这条 RFC 1123 正则是前端临时立的规矩，等后端补上校验后
// 改为调用它 —— 与用户名那条口径一致（`validate_user`，见账户页文件头第 1 条）。
//
// 主按钮不置灰（与网络页、账户页同一条）：空着点「继续」就当场说清缺什么，
// 并把光标送进去。

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

    // 一列短表单：宽度按内容定，不是全站一个数
    contentWidth: 660

    // 这一页现在是**高级安装的分支**（语言 / 键盘 / 时区 / 主机名 四项之一），
    // 不是主流程里的下一步 —— 所以是「完成」，不是「继续」（2026-09-25 评审）。
    primaryText: "完成"

    signal hostnameChosen(string hostname)
    signal backRequested()

    //: 与后端 `TargetConfig.hostname` 的默认值一致
    property string hostname: "mipl"

    /// 点过一次「继续」之后，空的字段也要报错
    property bool submitted: false

    readonly property bool hostValid:
        /^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(page.hostname)

    readonly property string hostError: {
        if (page.hostname === "")
            return page.submitted ? "还没填主机名。" : "";
        if (page.hostname.length > 63)
            return "太长了，最多 63 个字符。";
        if (!page.hostValid)
            return "只能含字母、数字与连字符，- 不能在头尾";
        return "";
    }

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "network"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s2
            title: "主机名"

            Column {
                width: parent.width
                spacing: Tokens.s2

                Text {
                    width: parent.width
                    text: "这台机器在网络与终端提示符里的名字。"
                    font: Tokens.small
                    color: Tokens.textMuted
                    wrapMode: Text.WordWrap
                }

                Field {
                    id: hostField
                    fieldWidth: parent.width
                    // 44 与账户页、确认擦除页一致
                    fieldHeight: 44
                    // 不写 label：卡片标题已经是「主机名」，再来一行只是把同一句话说两遍
                    label: ""
                    text: page.hostname
                    placeholder: "例如 mipl"
                    error: page.hostError
                    onEdited: page.hostname = text
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: {
        if (!page.hostValid) {
            page.submitted = true;
            hostField.inputItem.forceActiveFocus();
            return;
        }
        page.hostnameChosen(page.hostname);
    }

    onBackClicked: page.backRequested()
}
