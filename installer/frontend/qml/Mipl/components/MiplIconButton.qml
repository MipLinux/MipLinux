// MiplIconButton —— 08 §4.1「Icon button（standard / filled）」的覆写件。
// 底座：Qt Quick Controls Basic 的 AbstractButton。
// 图标：08 §3.7 定的是 SVG 资源；本阶段资产未落地，所以提供三种互斥的给图方式：
//   iconSource（SVG/位图，将来） > iconName（内置绘制，不依赖字体） > iconText（任意文字，如「Aa」）。
//   内置绘制不用 字体字形：Live 的 noto-fonts 覆盖不到 ✓ / ← 这类符号，回退会出豆腐块。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

AbstractButton {
    id: control

    enum Variant { Standard, Filled }

    property int variant: MiplIconButton.Standard
    property url iconSource: ""
    property string iconText: ""
    // "back"（左尖括号）| ""（不绘制）
    property string iconName: ""
    // tooltip 文案：08 §3.7 要求图标按钮必须有标签或 tooltip
    property string tip: ""
    // 图标档位：08 §3.7 的 24 档（图标按钮限 24）
    property real iconSize: MiplSpace.xl

    // 08 §3.8：Enter 触发主动作（QQC Basic 只认 Space）
    function _activateKey() {
        if (control.enabled)
            control.clicked()
    }
    Keys.onReturnPressed: control._activateKey()
    Keys.onEnterPressed: control._activateKey()

    implicitWidth: MiplSpace.xxl + MiplSpace.s
    implicitHeight: implicitWidth
    padding: (implicitWidth - iconSize) / 2

    readonly property color iconColor: !enabled
                                       ? Qt.rgba(MiplColor.onSurface.r, MiplColor.onSurface.g, MiplColor.onSurface.b, 0.38)
                                       : variant === MiplIconButton.Filled ? MiplColor.onPrimary
                                       : MiplColor.onSurfaceVariant

    Accessible.role: Accessible.Button
    Accessible.name: tip.length > 0 ? tip : iconText
    Accessible.description: tip

    contentItem: Item {
        implicitWidth: control.iconSize
        implicitHeight: control.iconSize

        Image {
            anchors.fill: parent
            visible: control.iconSource != ""
            source: control.iconSource
            sourceSize.width: control.iconSize
            sourceSize.height: control.iconSize
            fillMode: Image.PreserveAspectFit
        }

        Text {
            anchors.centerIn: parent
            visible: control.iconSource == "" && control.iconName == "" && control.iconText.length > 0
            text: control.iconText
            color: control.iconColor
            font.family: MiplType.family
            font.pixelSize: control.iconSize * 0.75
            font.weight: MiplType.labelLarge.weight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        // 内置「返回」左尖括号：两根圆头短杆拼出来（u = 24px 设计格的比例，不是 scale 倍数）
        Item {
            anchors.centerIn: parent
            visible: control.iconSource == "" && control.iconName === "back"
            width: control.iconSize
            height: control.iconSize
            readonly property real u: width / 24

            Rectangle {
                width: 2 * parent.u
                height: 9 * parent.u
                radius: width / 2
                x: 11 * parent.u - width / 2
                y: 9 * parent.u - height / 2
                rotation: 45
                color: control.iconColor
            }
            Rectangle {
                width: 2 * parent.u
                height: 9 * parent.u
                radius: width / 2
                x: 11 * parent.u - width / 2
                y: 15 * parent.u - height / 2
                rotation: -45
                color: control.iconColor
            }
        }
    }

    background: Rectangle {
        radius: control.height / 2
        color: control.variant === MiplIconButton.Filled && control.enabled ? MiplColor.primary : "transparent"
        border.width: 0

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.variant === MiplIconButton.Filled ? MiplColor.onPrimary : MiplColor.onSurfaceVariant
            opacity: !control.enabled ? 0
                   : control.down ? 0.12
                   : control.hovered ? 0.08
                   : control.activeFocus ? 0.12 : 0
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
            anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            visible: control.activeFocus
            border.width: 2
            border.color: MiplColor.primary
        }
    }

    // tooltip 挂在自己身上：悬停或键盘聚焦时显示（08 §3.7）
    // 不绑定 parent（Popup 一旦被重设父项就会和自己的坐标绑定打架）：默认父项就是这个按钮，
    // 坐标相对按钮算；Popup 本身由窗口的 overlay 层渲染，不会被父项裁剪。
    MiplTooltip {
        id: tipPopup
        text: control.tip
        visible: control.tip.length > 0 && (control.hovered || control.activeFocus)
        x: Math.round((control.width - width) / 2)
        y: Math.round(control.height + MiplSpace.s)
    }
}
