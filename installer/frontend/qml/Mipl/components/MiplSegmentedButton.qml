// MiplSegmentedButton —— 08 §4.1「Segmented button」的自建件（2–3 项互斥切换）。
// 底座：AbstractButton × N + ButtonGroup 语义由本组件自己表达（不用 checkable，避免与外部绑定抢 checked）。
// 键盘：每个分段都是 Tab 可达的按钮，Enter / Space 触发（08 §3.8）。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

Item {
    id: control

    // 字符串数组，如 ["简体中文", "English"]
    property var model: []
    property int currentIndex: 0
    signal activated(int index)

    readonly property int segmentCount: repeater.count
    // MD3 分段按钮高 40 = xxl + s
    readonly property real segmentHeight: MiplSpace.xxl + MiplSpace.s
    readonly property real segmentRadius: segmentHeight / 2

    implicitHeight: segmentHeight
    implicitWidth: segmentsRow.implicitWidth

    Accessible.role: Accessible.Grouping
    Accessible.name: qsTr("分段选择")

    // 外框：1px outline-variant 层级（08 §3.5）
    Rectangle {
        anchors.fill: parent
        radius: control.segmentRadius
        color: "transparent"
        border.width: 1
        border.color: MiplColor.outline
    }

    Row {
        id: segmentsRow
        anchors.fill: parent

        Repeater {
            id: repeater
            model: control.model

            delegate: AbstractButton {
                id: segment

                required property int index
                required property var modelData

                readonly property bool selected: control.currentIndex === index
                readonly property bool isFirst: index === 0
                readonly property bool isLast: index === control.segmentCount - 1

                implicitHeight: control.segmentHeight
                implicitWidth: Math.max(MiplSpace.page + MiplSpace.xl,
                                        segmentLabel.implicitWidth + MiplSpace.xl * 2)
                width: Math.max(implicitWidth, control.width / Math.max(1, control.segmentCount))
                height: control.segmentHeight

                onClicked: {
                    control.currentIndex = index
                    control.activated(index)
                }

                // 08 §3.8：Enter 与 Space 同义（QQC Basic 只处理 Space）
                Keys.onReturnPressed: segment.clicked()
                Keys.onEnterPressed: segment.clicked()

                Accessible.role: Accessible.RadioButton
                Accessible.name: String(segment.modelData)
                Accessible.checked: segment.selected

                contentItem: Item {
                    implicitWidth: segmentLabel.implicitWidth
                    implicitHeight: segmentLabel.implicitHeight

                    Text {
                        id: segmentLabel
                        anchors.centerIn: parent
                        text: String(segment.modelData)
                        color: !segment.enabled ? MiplColor.onSurfaceVariant
                             : segment.selected ? MiplColor.onSecondaryContainer
                             : MiplColor.onSurface
                        font.family: MiplType.family
                        font.pixelSize: MiplType.labelLarge.size
                        font.weight: MiplType.labelLarge.weight
                        font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                                    : MiplType.labelLarge.tracking
                        textFormat: Text.PlainText
                    }
                }

                background: Rectangle {
                    // 每角圆角：整组是胶囊（Qt 6.7+ 的 Rectangle 四角独立半径）
                    topLeftRadius: segment.isFirst ? control.segmentRadius : 0
                    bottomLeftRadius: segment.isFirst ? control.segmentRadius : 0
                    topRightRadius: segment.isLast ? control.segmentRadius : 0
                    bottomRightRadius: segment.isLast ? control.segmentRadius : 0
                    color: segment.selected ? MiplColor.secondaryContainer : "transparent"
                    border.width: 0

                    Rectangle {
                        anchors.fill: parent
                        topLeftRadius: parent.topLeftRadius
                        bottomLeftRadius: parent.bottomLeftRadius
                        topRightRadius: parent.topRightRadius
                        bottomRightRadius: parent.bottomRightRadius
                        color: segment.selected ? MiplColor.onSecondaryContainer : MiplColor.onSurface
                        opacity: !segment.enabled ? 0
                               : segment.down ? 0.12
                               : segment.hovered ? 0.08
                               : segment.activeFocus ? 0.12 : 0
                        Behavior on opacity {
                            NumberAnimation {
                                duration: MiplMotion.short2
                                easing.type: Easing.Bezier
                                easing.bezierCurve: MiplMotion.easingStandard
                            }
                        }
                    }

                    // 焦点环：2px primary，贴着分段内缘（08 §3.8）
                    Rectangle {
                        anchors.fill: parent
                        topLeftRadius: parent.topLeftRadius
                        bottomLeftRadius: parent.bottomLeftRadius
                        topRightRadius: parent.topRightRadius
                        bottomRightRadius: parent.bottomRightRadius
                        color: "transparent"
                        visible: segment.activeFocus
                        border.width: 2
                        border.color: MiplColor.primary
                    }
                }
            }
        }
    }
}
