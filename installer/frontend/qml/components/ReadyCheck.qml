// 就绪检查：三行自检。
//
// 做成**三列表格**而不是自由流动的文字：
//   [符号] [项目] [结果]
// 结果那一列必须左对齐成一列 —— 否则「已连接（有线）」「未检测到」「UEFI」
// 各自跟着标签跑，读起来是三句话而不是一张表。
//
// 这里只报**状态**。出问题时「怎么办」不写在这（会在别处重复），
// 由页面自己选一处讲清楚。

import QtQuick
import QtQuick.Layouts
import "../theme"

Column {
    id: check

    //: [{ label: "网络", state: "ok"|"fail"|"checking", value: "已连接（有线）" }]
    property var items: []

    //: 「结果」列的起点。调用方按同一页里其它表格的标签宽度给值，
    //: 让检查表和「将要安装」那张表对齐成同一套栅格。
    property int labelWidth: 72

    spacing: Tokens.s2

    Repeater {
        model: check.items
        delegate: RowLayout {
            id: row
            required property var modelData
            /// 取一次到局部，子项引用 row.xxx —— 不用 parent.parent 这种脆链
            readonly property string state: modelData.state || "checking"

            width: check.width
            spacing: Tokens.s2

            // 符号不只是装饰：颜色之外必须还有一层信息（色盲 / 灰度截图）。
            // 一律矢量（components/Icon.qml），不用 ✓ ✗ 这类字符。
            Icon {
                // 名字都来自 Lucide（见 icons/lucide/）
                name: row.state === "ok" ? "check"
                                         : (row.state === "fail" ? "x" : "circle")
                size: 14
                color: row.state === "ok" ? Tokens.success
                                          : (row.state === "fail" ? Tokens.danger : Tokens.textFaint)
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 16
            }

            Text {
                text: row.modelData.label || ""
                font: Tokens.body
                color: Tokens.text
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: check.labelWidth - 16 - Tokens.s2
            }

            Text {
                text: row.modelData.value || ""
                font: Tokens.technical
                color: row.state === "fail" ? Tokens.danger : Tokens.textMuted
                Layout.alignment: Qt.AlignVCenter
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }
    }
}
