// MiplCard —— 08 §4.1「Card（outlined / filled）」的组合件。
// 底座：Rectangle + Column（组合，不是覆写）。层级靠 surface-container-* + 1px outline-variant（08 §3.5），不用阴影。
// 用法：标题 / 副标题走属性，正文塞进默认属性（会落进 body）。
// 纪律：只取 Mipl* token；不乘 MiplScale.factor、不碰 devicePixelRatio。
import QtQuick
import Mipl 1.0

Rectangle {
    id: control

    enum Variant { Outlined, Filled }

    property int variant: MiplCard.Outlined
    property string title: ""
    property string subtitle: ""
    property string leadingText: ""
    property real padding: MiplSpace.l
    default property alias contentData: body.data

    readonly property bool cjkTitle: /[\u3400-\u9fff\uf900-\ufaff]/.test(title)

    implicitWidth: column.implicitWidth + padding * 2
    implicitHeight: column.implicitHeight + padding * 2

    color: variant === MiplCard.Filled ? MiplColor.surfaceContainerHighest : MiplColor.surfaceContainer
    radius: MiplShape.medium
    border.width: variant === MiplCard.Outlined ? 1 : 0
    border.color: MiplColor.outlineVariant

    Column {
        id: column

        x: control.padding
        y: control.padding
        width: control.width - control.padding * 2
        spacing: MiplSpace.m

        Row {
            id: headerRow
            width: parent.width
            spacing: MiplSpace.l
            visible: control.leadingText.length > 0 || control.title.length > 0 || control.subtitle.length > 0

            Text {
                id: leadingIcon
                visible: control.leadingText.length > 0
                text: control.leadingText
                color: MiplColor.onSurfaceVariant
                font.family: MiplType.family
                font.pixelSize: MiplSpace.xl
                anchors.verticalCenter: parent.verticalCenter
            }

            Column {
                width: parent.width - (leadingIcon.visible ? leadingIcon.width + parent.spacing : 0)
                spacing: 0

                Text {
                    width: parent.width
                    visible: control.title.length > 0
                    text: control.title
                    color: MiplColor.onSurface
                    font.family: MiplType.family
                    font.pixelSize: MiplType.titleMedium.size
                    font.weight: MiplType.titleMedium.weight
                    font.letterSpacing: control.cjkTitle ? MiplType.cjkTracking : MiplType.titleMedium.tracking
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }

                Text {
                    width: parent.width
                    visible: control.subtitle.length > 0
                    text: control.subtitle
                    color: MiplColor.onSurfaceVariant
                    font.family: MiplType.family
                    font.pixelSize: MiplType.bodyMedium.size
                    font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                                : MiplType.bodyMedium.tracking
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
            }
        }

        // 正文容器：由使用方塞内容（默认属性）。必须是 Column ——
        // 裸 Item 里的子项都会落在 (0,0)，多行内容会叠在一起。
        Column {
            id: body
            width: parent.width
            spacing: MiplSpace.m
        }
    }
}
