// MiplMenu —— 08 §4.1「Menu」的覆写件：下拉选择 / 缩放档位菜单。
// 底座：Qt Quick Controls Basic 的 Menu。
//
// 用法：菜单项**必须**用 MiplMenuItem 声明（`MiplMenu { MiplMenuItem { ... } }`）。
// 本组件**不设** `delegate` —— QQC 的 `Menu.delegate` 对声明式菜单项不生效（F8），
// 写了就是一层看着生效、实际走不到的换皮代码；原因与实测见 MiplMenuItem.qml 头部。
//
// 分隔线：菜单里的分隔请用 MiplDivider（实测能作为菜单行正常排布：宽=菜单内宽、高 1px，
// 后面的项紧接其后）；不要用 QQC 的 MenuSeparator —— 它走默认皮肤，本阶段没有 token 化入口。
//
// 层级：08 §3.5 唯一的例外 —— 只有菜单用阴影，且只到 level2。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import Mipl 1.0

Menu {
    id: control

    padding: MiplSpace.s
    margins: 0
    overlap: 1

    background: Rectangle {
        implicitWidth: MiplSpace.page * 4
        implicitHeight: MiplSpace.page
        color: MiplColor.surfaceContainer
        radius: MiplShape.extraSmall
        border.width: 1
        border.color: MiplColor.outlineVariant

        // 08 §3.5：只有菜单用阴影，且只到 level2（web elevation 3）
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowBlur: 0.5
            shadowVerticalOffset: 3
            shadowOpacity: 0.4
            shadowColor: MiplColor.shadow
        }
    }
}
