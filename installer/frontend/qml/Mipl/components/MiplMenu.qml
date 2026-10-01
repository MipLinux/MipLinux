// MiplMenu —— 08 §4.1「Menu」的覆写件：下拉选择 / 缩放档位菜单。
// 底座：Qt Quick Controls Basic 的 Menu（Menu 的 items 由使用方用 MenuItem 声明，沿用 QQC 习惯）。
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

    // 菜单项统一换皮：尺寸 / 状态层 / 选中勾都按 MD3 走
    delegate: MenuItem {
        id: menuItem

        implicitWidth: MiplSpace.page * 4
        implicitHeight: Math.max(MiplSpace.page, menuLabel.implicitHeight + MiplSpace.m)
        leftPadding: MiplSpace.l
        rightPadding: MiplSpace.l
        topPadding: MiplSpace.m
        bottomPadding: MiplSpace.m

        Accessible.role: Accessible.MenuItem
        Accessible.name: menuItem.text
        Accessible.checked: menuItem.checked
        Accessible.checkable: menuItem.checkable

        // 默认的勾图标走 palette，深色底上会看不见；换成自己画的
        indicator: Item {
            implicitWidth: 0
            implicitHeight: 0
        }

        contentItem: Item {
            implicitWidth: menuRow.implicitWidth
            implicitHeight: menuRow.implicitHeight

            Row {
                id: menuRow
                anchors.verticalCenter: parent.verticalCenter
                spacing: MiplSpace.m

                // 选中勾：18 设计格的两根短杆
                Item {
                    visible: menuItem.checkable
                    width: MiplSpace.l + 2
                    height: MiplSpace.l + 2
                    anchors.verticalCenter: parent.verticalCenter
                    readonly property real u: width / 18

                    Rectangle {
                        visible: menuItem.checked
                        width: 2 * parent.u
                        height: 4.3 * parent.u
                        radius: width / 2
                        x: 6 * parent.u - width / 2
                        y: 11 * parent.u - height / 2
                        rotation: -45
                        color: MiplColor.onSurface
                    }
                    Rectangle {
                        visible: menuItem.checked
                        width: 2 * parent.u
                        height: 8.9 * parent.u
                        radius: width / 2
                        x: 10.5 * parent.u - width / 2
                        y: 9.25 * parent.u - height / 2
                        rotation: 45
                        color: MiplColor.onSurface
                    }
                }

                Text {
                    id: menuLabel
                    anchors.verticalCenter: parent.verticalCenter
                    text: menuItem.text
                    color: menuItem.enabled ? MiplColor.onSurface : MiplColor.onSurfaceVariant
                    font.family: MiplType.family
                    font.pixelSize: MiplType.labelLarge.size
                    font.weight: MiplType.labelLarge.weight
                    font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                                : MiplType.labelLarge.tracking
                    textFormat: Text.PlainText
                }
            }
        }

        background: Rectangle {
            radius: MiplShape.extraSmall
            color: menuItem.highlighted ? MiplColor.surfaceContainerHighest : "transparent"

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: MiplColor.onSurface
                opacity: !menuItem.enabled ? 0
                       : menuItem.down ? 0.12
                       : menuItem.hovered ? 0.08
                       : menuItem.activeFocus ? 0.12 : 0
                Behavior on opacity {
                    NumberAnimation {
                        duration: MiplMotion.short2 * MiplMotion.motionScale
                        easing.type: Easing.Bezier
                        easing.bezierCurve: MiplMotion.easingStandard
                    }
                }
            }

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: "transparent"
                visible: menuItem.activeFocus
                border.width: 2
                border.color: MiplColor.primary
            }
        }
    }

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
