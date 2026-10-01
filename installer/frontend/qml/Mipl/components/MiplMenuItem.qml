// MiplMenuItem —— 08 §4.1「Menu」的**菜单项**换皮件，与 MiplMenu 配套使用。
//
// 为什么必须有这一件（F8）：QQC `Menu.delegate` 只作用于**从 model 生成**的项。
// 使用方声明式写 `MenuItem {}` 时，走的是 QQC 自己声明的那个项，`delegate` 根本不参与 ——
// 实测：静态声明下对象树里既没有 delegate 的 contentItem（QQuickRow/QQuickText），
// 也没有任何 Behavior，菜单项用的是 QQC 默认皮肤；而 `Menu` 没有 `model`
// （`contentModel` 只读），也没法改成「从 model 生成」。
// 所以换皮只能落在使用方**实际声明的类型**上：菜单项一律用 MiplMenuItem。
//
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

MenuItem {
    id: control

    implicitWidth: MiplSpace.page * 4
    implicitHeight: Math.max(MiplSpace.page, menuLabel.implicitHeight + MiplSpace.m)
    leftPadding: MiplSpace.l
    rightPadding: MiplSpace.l
    topPadding: MiplSpace.m
    bottomPadding: MiplSpace.m

    Accessible.role: Accessible.MenuItem
    Accessible.name: control.text
    Accessible.checked: control.checked
    Accessible.checkable: control.checkable

    // 08 §3.8：Enter 触发主动作（QQC Basic 只认 Space）
    Keys.onReturnPressed: control.clicked()
    Keys.onEnterPressed: control.clicked()

    // QQC 默认的勾图标走 palette，深色底上看不见；这里自己画
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
                visible: control.checkable
                width: MiplSpace.l + 2
                height: MiplSpace.l + 2
                anchors.verticalCenter: parent.verticalCenter
                readonly property real u: width / 18

                Rectangle {
                    visible: control.checked
                    width: 2 * parent.u
                    height: 4.3 * parent.u
                    radius: width / 2
                    x: 6 * parent.u - width / 2
                    y: 11 * parent.u - height / 2
                    rotation: -45
                    color: MiplColor.onSurface
                }
                Rectangle {
                    visible: control.checked
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
                text: control.text
                color: control.enabled ? MiplColor.onSurface : MiplColor.onSurfaceVariant
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
        color: control.highlighted ? MiplColor.surfaceContainerHighest : "transparent"

        // 状态层：hover 0.08 / focus 0.12 / pressed 0.12（08 §3.5）
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: MiplColor.onSurface
            opacity: !control.enabled ? 0
                   : control.down ? 0.12
                   : control.hovered ? 0.08
                   : control.activeFocus ? 0.12 : 0
            Behavior on opacity {
                NumberAnimation {
                    duration: MiplMotion.short2
                    easing.type: Easing.Bezier
                    easing.bezierCurve: MiplMotion.easingStandard
                }
            }
        }

        // 焦点环：2px primary（08 §3.8）
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            visible: control.activeFocus
            border.width: 2
            border.color: MiplColor.primary
        }
    }
}
