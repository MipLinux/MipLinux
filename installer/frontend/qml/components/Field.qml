// 表单字段：标签 / 输入框 / 行内错误 / 帮助文字。
//
// 「错误说人话 + 下一步」在控件层的落点：错误只出现**在字段下面**，
// 不用弹窗、不用页面顶部汇总 —— 用户眼睛不用离开正在填的那一行。
//
// ── 两个布局上的坑（都实测踩过，别改回去）──────────────────────────────
// 1. 根对象是 Item，不是 Column：Column 的 implicitWidth/implicitHeight 是
//    只读的，而 Field 要能放进 RowLayout —— 没有 implicitWidth 就会被压成一条缝。
// 2. 帮助/错误文字的宽度**不参与** implicitWidth 计算。它们会换行，
//    若把 Unwrapped 的整句长度算进去，字段宽度会离谱（实测被撑到 600+，
//    然后又被 Layout 压回去，文字挤成三行）。

import QtQuick
import "../theme"

Item {
    id: field

    // ── 接口 ──────────────────────────────────────────────────────────
    property alias label: labelText.text
    property alias text: input.text
    //: 占位提示。TextInput 没有 placeholderText（那是 TextField 的），
    //: 所以自己存一个值，由下面那个 Text 负责画。
    property string placeholder: ""
    property string help: ""
    property string error: ""
    /// 密码框
    property bool secret: false
    /// 只读展示（例如「即将安装」摘要里的值）
    property bool readOnly: false
    property alias inputItem: input

    signal edited()

    //: 有错误时描边转红 —— 颜色只是加强，错误文字本身才是信息。
    readonly property bool _invalid: error !== ""

    //: 输入框宽度：给了就按它，没给就用 defaultFieldWidth。
    property real fieldWidth: defaultFieldWidth
    readonly property real defaultFieldWidth: 320
    //: 输入框高度。默认 48（手指/鼠标都舒服）；整页最紧的地方可以压到 44，
    //: 再小就会低于可点面积的下限。
    property int fieldHeight: 48

    //: 这行字段至少要多宽才放得下（帮助/错误文字按 320 估两行，不算整句）
    implicitWidth: field.fieldWidth
    implicitHeight: column.implicitHeight

    Column {
        id: column
        x: 0
        y: 0
        width: field.width
        spacing: Tokens.s1

        Text {
            id: labelText
            width: parent.width
            font: Tokens.bodyStrong
            color: Tokens.text
            wrapMode: Text.WordWrap
            visible: text !== ""
        }

        Rectangle {
            width: field.fieldWidth
            height: field.fieldHeight
            radius: Tokens.rControl
            color: field.readOnly ? Tokens.subtleBg : Tokens.cardBg
            border.width: 1
            border.color: field._invalid ? Tokens.danger
                                         : (input.activeFocus ? Tokens.focusRing : Tokens.borderField)

            TextInput {
                id: input
                anchors.fill: parent
                anchors.leftMargin: Tokens.s2
                anchors.rightMargin: Tokens.s2
                verticalAlignment: TextInput.AlignVCenter
                font: Tokens.body
                color: field.readOnly ? Tokens.textMuted : Tokens.text
                echoMode: field.secret ? TextInput.Password : TextInput.Normal
                readOnly: field.readOnly
                selectByMouse: true
                selectionColor: Tokens.accentTint
                selectedTextColor: Tokens.text
                onTextChanged: field.edited()

                Text {
                    anchors.fill: parent
                    verticalAlignment: Text.AlignVCenter
                    text: field.placeholder
                    font: Tokens.body
                    color: Tokens.textFaint
                    visible: input.text === "" && !input.activeFocus
                    elide: Text.ElideRight
                }
            }
        }

        Text {
            width: field.fieldWidth
            visible: field._invalid
            text: field.error
            font: Tokens.small
            color: Tokens.danger
            wrapMode: Text.WordWrap
        }

        Text {
            width: field.fieldWidth
            visible: !field._invalid && field.help !== ""
            text: field.help
            font: Tokens.small
            color: Tokens.textFaint
            wrapMode: Text.WordWrap
        }
    }
}
