// MiplTooltip —— 08 §4.1「Tooltip（plain）」的覆写件。
// 底座：Qt Quick Controls Basic 的 ToolTip（08 §5 路线 B）。
// 纪律：只取 Mipl* token；token 已在单例内部乘过 MiplScale.factor，本文件不乘 scale、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

ToolTip {
    id: control

    // 独立使用：可见性由使用方绑定（悬停 / 聚焦），不在组件内部做定时隐藏。
    // 悬停时长的语义留给使用方，避免 timeout 反向改写使用方的 visible 绑定。
    timeout: -1

    padding: MiplSpace.s
    leftPadding: MiplSpace.m
    rightPadding: MiplSpace.m
    topPadding: MiplSpace.s
    bottomPadding: MiplSpace.s

    font.family: MiplType.family
    font.pixelSize: MiplType.labelMedium.size
    font.weight: MiplType.labelMedium.weight
    font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(control.text) ? MiplType.cjkTracking
                                                                          : MiplType.labelMedium.tracking

    contentItem: Text {
        text: control.text
        font: control.font
        color: MiplColor.inverseOnSurface
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }

    background: Rectangle {
        color: MiplColor.inverseSurface
        radius: MiplShape.extraSmall
        border.width: 1
        border.color: MiplColor.outlineVariant
    }
}
