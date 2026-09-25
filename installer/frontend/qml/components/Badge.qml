// 状态胶囊：磁盘列表上那四个状态，以及页面里其它需要一眼分辨的短标记。
//
// 变体的**语义优先级**（不是配色偏好）见 tech/07 §P2：
//   正在使用 / 太小 → 危险，且该行禁用
//   可移动设备 / 已有分区表 → 警告，行仍可选
//
// 每个变体都带符号，理由同 Alert.qml。

import QtQuick
import "../theme"

Rectangle {
    id: badge

    //: neutral / info / warning / danger / success
    property string variant: "neutral"
    property string text: ""

    readonly property var _palette: {
        if (variant === "danger")
            return { fill: Tokens.dangerTint, bd: Tokens.dangerBorder, fg: Tokens.danger, mark: "x" };
        if (variant === "warning")
            return { fill: Tokens.warningTint, bd: Tokens.warningBorder, fg: Tokens.warning, mark: "circle" };
        if (variant === "success")
            return { fill: Tokens.successTint, bd: Tokens.successTint, fg: Tokens.success, mark: "check" };
        if (variant === "info")
            return { fill: Tokens.accentTint, bd: Tokens.accentBorder, fg: Tokens.accentAction, mark: "" };
        return { fill: Tokens.subtleBg, bd: Tokens.border, fg: Tokens.textMuted, mark: "" };
    }

    implicitWidth: row.implicitWidth + Tokens.s2
    implicitHeight: 28
    radius: Tokens.rPill
    color: _palette.fill
    border.width: 1
    border.color: _palette.bd

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 4

        Icon {
            visible: badge._palette.mark !== ""
            anchors.verticalCenter: parent.verticalCenter
            name: badge._palette.mark
            size: 11
            color: badge._palette.fg
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: badge.text
            font: Tokens.small
            color: badge._palette.fg
        }
    }
}
