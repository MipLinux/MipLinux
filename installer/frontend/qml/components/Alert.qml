// 提示块：info / warning / danger / success。
//
// 原则「高危信息不靠颜色传达」在控件层的落点：每种变体都带一个符号，
// 颜色只是加强。色盲用户、以及灰度打印出来的截图上，符号还在。

import QtQuick
import "../theme"

Rectangle {
    id: alert

    //: info / warning / danger / success
    property string variant: "info"
    property string title: ""
    property string message: ""
    default property alias content: extra.data

    readonly property var _palette: {
        if (variant === "danger")
            return { fill: Tokens.dangerTint, line: Tokens.dangerBorder, fg: Tokens.danger, mark: "x" };
        if (variant === "warning")
            return { fill: Tokens.warningTint, line: Tokens.warningBorder, fg: Tokens.warning, mark: "circle" };
        if (variant === "success")
            return { fill: Tokens.successTint, line: Tokens.successTint, fg: Tokens.success, mark: "check" };
        return { fill: Tokens.accentTint, line: Tokens.accentBorder, fg: Tokens.accentAction, mark: "circle" };
    }

    implicitWidth: Tokens.contentMaxWidth
    // 高度按内部 Column 算，但**不留多余的一行**：文本行高由字体决定，
    // 这里只负责内边距。早期版本在这里多估了一行，导致每张 Alert 白高 ~20px，
    // 页面就顶到行动区了（实测 AccountPage 差 43px）。
    implicitHeight: column.implicitHeight + Tokens.s3 * 2
    radius: Tokens.rControl
    color: _palette.fill
    border.width: 1
    border.color: _palette.line

    // 符号一律矢量（components/Icon.qml）：颜色之外还有一层形状信息，
    // 色盲用户与灰度截图里都还在。
    Icon {
        id: mark
        x: Tokens.s2
        y: Tokens.s3
        width: 20
        height: 20
        name: alert._palette.mark
        size: 16
        color: alert._palette.fg
    }

    Column {
        id: column
        x: Tokens.s2 + 20 + Tokens.s2
        y: Tokens.s3
        width: parent.width - x - Tokens.s2
        spacing: Tokens.s1

        Text {
            visible: alert.title !== ""
            width: parent.width
            text: alert.title
            font: Tokens.bodyStrong
            color: Tokens.text
            wrapMode: Text.WordWrap
        }
        Text {
            visible: alert.message !== ""
            width: parent.width
            text: alert.message
            font: Tokens.body
            color: Tokens.text
            wrapMode: Text.WordWrap
        }
        Column {
            id: extra
            width: parent.width
            spacing: Tokens.s1
        }
    }
}
