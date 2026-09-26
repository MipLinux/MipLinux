// 账户页 —— 与语言 / 键盘 / 时区各页**同一套**：大图标 + 一张主卡片，不要页头。
//
//                          [ 用户图标 ]
//        ┌──────────────────────────────────────────────┐
//        │ 账户                                          │
//        │ 用户名                                        │
//        │ [ 例如 mipl ]                                 │
//        │ 主机名                                        │
//        │ [ mipl ]                                      │
//        │ 密码                                          │
//        │ [ •••••••• ]                                  │
//        │ 再次输入                                      │
//        │ [ •••••••• ]                                  │
//        │ ────────────────────────────────────────────  │
//        │ ☐ 将密码应用于 root                           │
//        └──────────────────────────────────────────────┘
//        返回                                    [继续]
//
// ── 版面：一列到底，所以只能放三个字段（2026-09-25 评审）──────────────
// 评审要求「尽可能使用单列布局」，所以字段一律竖排，不再两两并排。
// 单列表单页因此把内容列收窄到 660（与「确认擦除」「磁盘分区」同宽）：
// 880 上放一列 832 宽的输入框，两端的字会隔着半个屏幕。
//
// **代价是「主机名」必须离开这一页。** 逐项量过（`shots.py --measure`）：
// 大图标 52 + 间距 24 + 卡片（内边距 48 + 标题 29 + 标题间距 16）= 169 是固定开销，
// 每个字段 80（`fieldHeight: 48`）、字段间 16、分隔线 17、root 行 40。
// 四个字段竖排 = **594px**，而 1280×800 上这一页只有 **584px** —— **默认态就装不下**，
// 而且每多一行错误还要再占 29px。
// 主机名是这一页唯一**不是决策**的字段（默认 `mipl`，要改的人会去「高级安装」，
// 那里本来就有这一项），所以走的是它：三个字段 + `fieldHeight: 44` = **486px**，
// 连最坏的三行错误（573px）也放得下。
//
// **这一页没有一句帮助文字**，这是评审核定的结果：字段名 + 占位符已经说清
// 每个框要什么，多一行灰字只是噪音。因此字段的**唯一可变高度就是错误行**，
// 一屏放得下与否只由「同时显示几行错误」决定 —— 三行就是最坏情况，量得出来。
//
// ── 五条口径 ──────────────────────────────────────────────────────────
//
// 1. **校验规则来自后端。** 用户名的判据是 backend/configure.py 的 `validate_user`
//    （`[a-z_][a-z0-9_-]{0,31}`，就是 useradd 的规则）。原型在 QML 里复现一份是为了
//    能取图；真实现必须**调用后端函数**，前端另写一份就是「唯一来源」约定在
//    校验逻辑上的翻版（tech/07 §P3）。
//    ⚠️ 主机名后端**没有**这条校验（只是把 `cfg.hostname` 原样写进 `/etc/hostname`），
//    所以下面那条 RFC 1123 的正则是前端临时立的规矩，属于待后端接管的一项。
//
// 2. **主按钮不置灰。** 字段没填完时点「继续」不会静默：它当场把还缺的字段标出来，
//    并把光标送到第一个（口径与网络页一致 —— 置灰让人猜为什么，点了把问题说清）。
//    这与「确认擦除」页故意保留置灰不矛盾：那一处守的是**不可逆**动作，这里守的
//    只是「还没填完」。
//
// 3. **root 默认保持锁定。** 勾上才是把**上面这个密码**也设给 root；没勾就是保持
//    锁定、只能用 sudo 提权。这一页不再单起一行解释（评审删掉了那行说明），
//    所以「root 会被锁」这件事现在只由复选框的文字承担。
//
// 4. **密码短不拦。** 「偏短」是提醒不是错误：后端能把短密码设成功，拦它就得自己
//    编一条后端没有的规则，所以只把代价说出来（现在也不再单起一行，与第 3 条同理）。
//
// 5. **主机名不在这里改。** 它由「高级安装」面板维护，本页只把它一起交给后端 ——
//    版面理由见上，产品理由是我们不把「不是决策」的字段摆在最后一道工序上。
//    ⚠️ 因此本页**不再校验主机名**。后端今天也不校验（`configure.py` 只把
//    `cfg.hostname` 原样写进 `/etc/hostname`），这条校验该由接管主机名的那个界面
//    / 后端补，不是在这里假装有。
//
// ⚠️ 后端今天能收的仍然有限：`--user` 与密码走 stdin（`cli.py`），root 密码只能靠
// `--root-password-stdin`；GUI 要拿到 TTY 之外的那条路，见 tech/07 §6 第 3 条。

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

    // 「继续」而不是「开始安装」：账户之后还有一屏**装前核对**
    // （`InstallDetailsPage.qml`，所有决定都做完、动盘之前把将要发生的事摊开），
    // 真正那颗「开始安装」在那一页 —— 最后一颗实心按钮属于最后一个确认动作。
    primaryText: "继续"

    signal accountChosen(string user, string host, string password, bool setRootPassword)
    signal backRequested()

    // ── 字段值 ────────────────────────────────────────────────────────
    property string userName: ""
    /// 本页**不编辑**主机名（在「高级安装」里改，见文件头第 5 条），只随账户一起交出去
    property string hostName: "mipl"
    property string password: ""
    property string passwordAgain: ""
    property bool setRootPassword: false

    /// 点过一次「开始安装」之后，**空的**字段也要报错。
    /// 在那之前只在用户真的输错时报 —— 一进页面就红三行是骚扰。
    property bool submitted: false

    // ── 校验 ──────────────────────────────────────────────────────────
    //: 用户名规则**来自后端**（`configure.validate_user`）：这里**调用**它，
    //: 不重写一份正则 —— 重写就是「唯一来源」约定在验证逻辑上的翻版
    //: （frontend/README）。没有后端时（取图 / 流程烟测）这条不拦：宁可在那条
    //: 离线路径上宽松，也不在界面里养第二份迟早会不一致的规则。
    readonly property bool userValid:
        page.userName !== ""
        && (typeof Backend === "undefined" || Backend.validateUser(page.userName) === "")

    readonly property string userError: {
        if (page.userName === "")
            return page.submitted ? "还没填用户名。" : "";
        if (!page.userValid)
            return "只能用小写字母或下划线开头，可含数字、- 与 _";
        return "";
    }

    readonly property bool passwordOk: page.password.length > 0
    readonly property string passwordError:
        page.password === "" && page.submitted ? "还没填密码。" : ""

    readonly property bool passwordMatch: page.passwordAgain === page.password
    //: 「不一致」只在用户开始输第二遍之后才提示 —— 还没输就报错是骚扰。
    readonly property string againError: {
        if (page.passwordAgain === "")
            return page.submitted ? "再把它输一遍。" : "";
        return page.passwordMatch ? "" : "两次输入的密码不一致。";
    }

    readonly property bool formOk:
        page.userValid && page.passwordOk && page.passwordMatch

    // ── 卡片内容区的滚动（评审：照时区 / 语言 / 键盘那三页的写法）─────────
    //
    // **页面本身永不滚动**：1280×800 上内容本来放得下（不出现滚动条），
    // 1024×600 上放不下时，滚的是**卡片里的字段区**，大图标、卡片标题与
    // 底部按钮都待在原地 —— 整页滚会把标题和主按钮一起推走，人滚到一半就不知道
    // 自己在填哪一步，也与那三页的手感不一致。
    //
    // 固定开销与那三页同一笔账：图标 52 + 图标间距 24 + 卡片上下内边距 48
    // + 卡片标题 29 + 标题间距 16 = 169。
    readonly property int fixedChrome: 169
    readonly property real fieldAreaHeight:
        Math.max(160, page.contentAvailableHeight - page.fixedChrome)

    // ── 内容 ──────────────────────────────────────────────────────────
    content: Column {
        width: parent.width
        spacing: Tokens.s3

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: "user-round"
            size: 52
            color: Tokens.accentDecor
        }

        Card {
            width: parent.width
            // 内边距用**全项目统一值**（Tokens.cardPadding = 24）
            padding: Tokens.cardPadding
            titleSpacing: Tokens.s2
            title: "账户"

            // 放得下时高度就是内容高（与不套 Flickable 时逐像素一致），
            // 放不下时收成可用高，由里面的字段区自己滚。
            Item {
                id: fieldPanel
                width: parent.width
                height: Math.min(fieldColumn.implicitHeight, page.fieldAreaHeight)

                Flickable {
                    id: fieldFlick
                    // 让出右侧 12px 给滚动条，免得条子压在输入框的描边上
                    width: parent.width - 12
                    height: parent.height
                    contentWidth: width
                    contentHeight: fieldColumn.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height
                    clip: interactive
                    pixelAligned: false

                    Column {
                        id: fieldColumn
                        width: parent.width
                        spacing: Tokens.s2

                        Field {
                            id: userField
                            fieldWidth: parent.width
                            // 44 是 Field 允许的最紧一档（EraseConfirmPage 也用它）：
                            // 三个字段一共省下 12px，正好把「三行错误」压进一屏。
                            fieldHeight: 44
                            label: "用户名"
                            text: page.userName
                            placeholder: "例如 mipl"
                            error: page.userError
                            onEdited: page.userName = text
                        }

                        Field {
                            id: passwordField
                            fieldWidth: parent.width
                            fieldHeight: 44
                            label: "密码"
                            text: page.password
                            secret: true
                            error: page.passwordError
                            onEdited: page.password = text
                        }

                        Field {
                            id: againField
                            fieldWidth: parent.width
                            fieldHeight: 44
                            label: "再次输入"
                            text: page.passwordAgain
                            secret: true
                            error: page.againError
                            onEdited: page.passwordAgain = text
                        }

                        // root 是另一件事（要不要多一个能登进来的账户），与上面三个字段分开。
                        // 没有分隔线时它紧贴在「再次输入」的输入框下面，会被读成第四个字段。
                        Rectangle {
                            width: parent.width
                            height: 1
                            color: Tokens.border
                        }

                        // root 那一行是「复选框 + 一句话」，不用 Alert：它是一条**状态说明**，
                        // 不是危险或警告 —— Alert 的视觉重量会让它挤掉真正要注意的东西。
                        Item {
                            width: parent.width
                            height: rootRow.height

                            RowLayout {
                                id: rootRow
                                width: parent.width
                                spacing: Tokens.s2

                                Rectangle {
                                    Layout.alignment: Qt.AlignVCenter
                                    width: 22
                                    height: 22
                                    radius: 6
                                    color: page.setRootPassword ? Tokens.accentAction
                                                                : Tokens.cardBg
                                    border.width: page.setRootPassword ? 0 : 1
                                    border.color: Tokens.borderField

                                    Icon {
                                        anchors.centerIn: parent
                                        visible: page.setRootPassword
                                        name: "check"
                                        size: 15
                                        color: Tokens.textOnAccent
                                    }
                                }

                                Text {
                                    Layout.alignment: Qt.AlignVCenter
                                    Layout.fillWidth: true
                                    text: "将密码应用于 root"
                                    font: Tokens.body
                                    color: rootArea.containsMouse ? Tokens.accentAction
                                                                  : Tokens.text

                                    Behavior on color {
                                        ColorAnimation { duration: Tokens.motionFast }
                                    }
                                }
                            }

                            // 整行可点 —— 只让 22×22 的方框可点是常见的「点不中」来源
                            MouseArea {
                                id: rootArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.setRootPassword = !page.setRootPassword
                            }
                        }
                    }
                }

                // 与那三页同一个组件、同一个摆法：贴在**卡片内容**的右缘，
                // 不是页面右缘；放得下时整根不画（ScrollBar 自己管这件事）。
                ScrollBar {
                    flickable: fieldFlick
                    x: fieldPanel.width - width
                    y: 0
                    height: fieldPanel.height
                }
            }
        }
    }

    // ── 动作 ──────────────────────────────────────────────────────────
    onPrimaryClicked: {
        if (!page.formOk) {
            // 一次把还缺的字段标出来，光标送到第一个 —— 不要让人点一次修一个
            page.submitted = true;
            if (!page.userValid)
                userField.inputItem.forceActiveFocus();
            else if (!page.passwordOk)
                passwordField.inputItem.forceActiveFocus();
            else
                againField.inputItem.forceActiveFocus();
            return;
        }
        page.accountChosen(page.userName, page.hostName, page.password,
                           page.setRootPassword);
    }

    onBackClicked: page.backRequested()
}
