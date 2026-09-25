// 按钮：胶囊形，四种变体。一页只允许一个 primary —— 「一页一个主按钮」是
// 减少认知负担的一部分，视觉上必须能一眼看出该点哪个。
//
// 颜色纪律（见 Tokens.qml 文件头）：填充底用 accentAction，**不用** accentDecor；
// 后者压白只有 4.20:1。

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: button

    // ── 接口 ──────────────────────────────────────────────────────────
    property string text: ""
    /// primary / secondary / ghost / danger
    property string variant: "primary"
    /// 标签右边的小字，用来点数量或快捷键（例如「· 3 块」）
    property string suffix: ""
    signal clicked()

    // ── 尺寸 ──────────────────────────────────────────────────────────
    implicitHeight: 48
    implicitWidth: row.implicitWidth + Tokens.s4
    radius: Tokens.rPill

    // ── 配色 ──────────────────────────────────────────────────────────
    readonly property color _fill: {
        if (!button.enabled)
            return Tokens.disabledBg;
        if (button.variant === "primary")
            return button._pressed ? Tokens.accentPress : Tokens.accentAction;
        if (button.variant === "danger")
            return button._pressed ? "#A81E1E" : Tokens.dangerFill;
        if (button.variant === "secondary")
            return button._hovered ? Tokens.accentTint : Tokens.cardBg;
        return "transparent";  // ghost
    }
    readonly property color _label: {
        if (!button.enabled)
            return Tokens.disabledText;
        if (button.variant === "primary" || button.variant === "danger")
            return Tokens.textOnAccent;
        if (button.variant === "secondary")
            return Tokens.accentAction;
        return Tokens.textMuted;  // ghost
    }
    readonly property bool _filled: variant === "primary" || variant === "danger"

    readonly property bool _hovered: mouseArea.containsMouse && button.enabled
    readonly property bool _pressed: mouseArea.pressed && button.enabled

    color: _fill
    border.width: (variant === "secondary" || (variant === "ghost" && _hovered)) ? 1 : 0
    border.color: button.enabled ? Tokens.borderField : Tokens.border

    // 焦点环：键盘可达性的唯一可见凭据，不能用颜色以外的装饰替掉。
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: button.radius + 3
        color: "transparent"
        border.width: 2
        border.color: Tokens.focusRing
        visible: button.activeFocus && button.enabled
    }

    Behavior on color {
        ColorAnimation { duration: Tokens.motionFast }
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Tokens.s1

        Text {
            text: button.text
            font: Tokens.bodyStrong
            color: button._label
        }
        Text {
            visible: button.suffix !== ""
            text: button.suffix
            font: Tokens.small
            color: button._filled ? Qt.rgba(1, 1, 1, 0.8) : button._label
            opacity: 0.9
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        enabled: button.enabled
        cursorShape: button.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: button.clicked()
    }
}
