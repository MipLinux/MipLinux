// ExamplePage —— 08 §4.1 的 17 项组件各一例，供离屏运行与截图目检（阶段 0 的 V5 目检素材）。
//
// 离屏跑法（验收命令）：
//   QT_QPA_PLATFORM=offscreen qml6 -I installer/frontend/qml installer/frontend/qml/Mipl/components/ExamplePage.qml
// 页面到 snapshotDelay 毫秒时把窗口内容存成 PNG（snapshotPath）然后退出 —— 否则 qml6 会一直挂着。
// 窗口 1100×2800 是为了让 17 项一屏截完（离屏没有屏幕尺寸限制）；真人看时把 height 调小，内容是 ScrollView 会滚动。
// 本页只做展示，不接真实后端（阶段 0 边界）。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

ApplicationWindow {
    id: page

    property string snapshotPath: "/tmp/mipl-example-page.png"
    property int snapshotDelay: 1500

    width: 1100
    height: 2800
    visible: true
    color: MiplColor.surface
    title: qsTr("Mipl 组件示例 · 阶段 0")

    // 整页内容包一层普通 Item：Window.contentItem 没有 QML engine，grabToImage 用不了。
    // 用 Rectangle 而不是裸 Item —— 截图要带不透明的页面底色，否则背景透明、存成 PNG 会变黑。
    Rectangle {
        id: contentRoot
        anchors.fill: parent
        color: MiplColor.surface

        Timer {
            interval: page.snapshotDelay
            running: true
            onTriggered: {
                contentRoot.grabToImage(function (result) {
                    result.saveToFile(page.snapshotPath)
                })
                // 兜底退出：就算截图没成，也不能让 qml6 一直挂着
                quitTimer.start()
            }
        }

        Timer {
            id: quitTimer
            interval: 500
            repeat: false
            onTriggered: Qt.quit()
        }

        // 每个小节：一行标题 + 直接用默认属性塞进来的示例
        component DemoSection: Column {
            property string heading: ""

            width: parent ? parent.width : 0
            spacing: MiplSpace.m

            Text {
                width: parent.width
                text: parent.heading
                color: MiplColor.onSurface
                font.family: MiplType.family
                font.pixelSize: MiplType.titleMedium.size
                font.weight: MiplType.titleMedium.weight
                font.letterSpacing: MiplType.cjkTracking
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
        }

        // ── 10 · Top app bar：窗口顶栏就是这一项 ────────────────────────────────
        MiplTopAppBar {
            id: appBar

            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            title: qsTr("组件总览 · %1").arg(MiplTheme.dark ? qsTr("暗色") : qsTr("亮色"))
            onBackClicked: snackbar.show(qsTr("返回（示例）"))

            // 14 · Tooltip 挂在这里：图标按钮必须有 tooltip（08 §3.7）
            MiplIconButton {
                iconText: MiplTheme.dark ? qsTr("暗") : qsTr("亮")
                tip: MiplTheme.locked ? qsTr("已手动锁定为暗色") : qsTr("跟随时间")
                onClicked: {
                    MiplTheme.locked = true
                    MiplTheme.manualDark = !MiplTheme.dark
                }
            }

            MiplIconButton {
                id: scaleButton
                iconText: "Aa"
                tip: qsTr("界面缩放")
                onClicked: {
                    scaleMenu.x = Math.round(scaleButton.mapToItem(null, 0, scaleButton.height).x)
                    scaleMenu.y = Math.round(scaleButton.mapToItem(null, 0, scaleButton.height).y)
                    scaleMenu.open()
                }
            }
        }

        // 15 · Menu：界面层缩放四档（08 §3.10），当前档打勾
        MiplMenu {
            id: scaleMenu

            Repeater {
                model: MiplScale.steps

                MenuItem {
                    required property int index
                    required property var modelData

                    text: MiplScale.labels[index] + " · " + Math.round(modelData * 100) + "%"
                    checkable: true
                    checked: Math.abs(MiplScale.factor - modelData) < 0.001
                    onTriggered: {
                        MiplScale.factor = modelData
                        checked = true
                    }
                }
            }
        }

        // 15 · Menu：普通下拉（有分组分隔线的用法）
        MiplMenu {
            id: moreMenu

            MenuItem {
                text: qsTr("重新扫描磁盘")
                onTriggered: snackbar.show(qsTr("重新扫描磁盘（示例）"))
            }
            MenuItem {
                text: qsTr("查看安装日志")
                onTriggered: snackbar.show(qsTr("查看安装日志（示例）"))
            }
            MenuSeparator {}
            MenuItem {
                text: qsTr("清除本次选择")
                enabled: false
            }
        }

        // 3 · Dialog：不可逆操作确认（P3）
        MiplDialog {
            id: confirmDialog

            title: qsTr("确认清除磁盘")
            message: qsTr("目标磁盘上的全部分区与数据都会被清除，此操作不可撤销。")
            acceptText: qsTr("清除并安装")
            dismissText: qsTr("取消")
            onAccepted: snackbar.show(qsTr("已确认（示例，不会真的动盘）"))
            onRejected: snackbar.show(qsTr("已取消"))
        }

        // 13 · Snackbar：非阻塞提示
        MiplSnackbar {
            id: snackbar
            actionText: qsTr("知道了")
        }

        ScrollView {
            id: scroll

            anchors.top: appBar.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            contentWidth: availableWidth
            clip: true

            Column {
                id: body

                width: scroll.availableWidth
                padding: MiplSpace.page
                spacing: MiplSpace.xxl

                // 1 · Button ───────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("1 · Button（filled / tonal / outlined / text）")

                    Row {
                        spacing: MiplSpace.m

                        MiplButton { text: qsTr("开始安装"); variant: MiplButton.Filled }
                        MiplButton { text: qsTr("次要动作"); variant: MiplButton.Tonal }
                        MiplButton { text: qsTr("返回"); variant: MiplButton.Outlined }
                        MiplButton { text: qsTr("跳过"); variant: MiplButton.Text }
                        MiplButton { text: qsTr("不可用"); enabled: false }
                    }

                    MiplButton {
                        width: MiplSpace.page * 6
                        text: qsTr("长文案换行：确认目标磁盘上的现有分区会被全部清除，然后开始安装")
                        variant: MiplButton.Outlined
                    }
                }

                // 2 · Icon button ──────────────────────────────────────────
                DemoSection {
                    heading: qsTr("2 · Icon button（standard / filled）")

                    Row {
                        spacing: MiplSpace.l

                        MiplIconButton { iconName: "back"; tip: qsTr("返回上一步") }
                        MiplIconButton { iconText: "Aa"; tip: qsTr("界面缩放"); variant: MiplIconButton.Filled }
                        MiplIconButton { iconText: qsTr("帮助"); tip: qsTr("打开帮助") }
                    }
                }

                // 3 · Dialog ───────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("3 · Dialog（basic，不可逆操作确认）")

                    MiplButton {
                        text: qsTr("打开确认对话框")
                        variant: MiplButton.Outlined
                        onClicked: confirmDialog.open()
                    }
                }

                // 4 · Linear progress ──────────────────────────────────────
                DemoSection {
                    heading: qsTr("4 · Linear progress（determinate / indeterminate）+ 步骤文字")

                    MiplLinearProgress {
                        width: MiplSpace.page * 8
                        value: 0.35
                        showStepLabel: true
                        step: 2
                        stepCount: 4
                    }

                    MiplLinearProgress {
                        width: MiplSpace.page * 8
                        indeterminate: true
                        showStepLabel: true
                        step: 2
                        stepCount: 4
                    }
                }

                // 5 · Text field ───────────────────────────────────────────
                DemoSection {
                    heading: qsTr("5 · Text field（filled / outlined）")

                    MiplTextField {
                        width: MiplSpace.page * 6
                        label: qsTr("主机名")
                        text: "mipl-pc"
                        supportingText: qsTr("只能用小写字母、数字和连字符")
                    }

                    MiplTextField {
                        width: MiplSpace.page * 6
                        variant: MiplTextField.Outlined
                        label: qsTr("密码")
                        echoMode: TextInput.Password
                        supportingText: qsTr("至少 8 位")
                    }

                    MiplTextField {
                        width: MiplSpace.page * 6
                        variant: MiplTextField.Outlined
                        label: qsTr("用户名")
                        text: "root"
                        error: true
                        supportingText: qsTr("该用户名已被占用")
                    }
                }

                // 6 · Switch ───────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("6 · Switch")

                    MiplSwitch { text: qsTr("自动连接网络"); checked: true }
                    MiplSwitch { text: qsTr("安装 NVIDIA 驱动") }
                }

                // 7 · Checkbox / Radio ─────────────────────────────────────
                DemoSection {
                    heading: qsTr("7 · Checkbox / Radio")

                    Row {
                        spacing: MiplSpace.xl

                        MiplCheckbox { text: qsTr("记住本次选择"); checked: true }
                        MiplCheckbox { text: qsTr("启用遥测（默认关闭）") }
                    }

                    ButtonGroup { id: langGroup }

                    Column {
                        spacing: MiplSpace.s

                        MiplRadio { text: qsTr("简体中文"); checked: true; ButtonGroup.group: langGroup }
                        MiplRadio { text: qsTr("English"); ButtonGroup.group: langGroup }
                        MiplRadio { text: qsTr("日本語"); ButtonGroup.group: langGroup }
                    }
                }

                // 8 · List item（装进卡片，顺带展示 9 与 16）───────────────
                DemoSection {
                    heading: qsTr("8 · List item（1–3 行）+ 9 · Card + 16 · Divider")

                    MiplCard {
                        width: MiplSpace.page * 8
                        title: qsTr("目标磁盘")
                        subtitle: qsTr("outlined 卡片 · 列表项容器")

                        MiplListItem {
                            width: parent.width
                            text: qsTr("/dev/vda · 64 GiB")
                            secondaryText: qsTr("UEFI 引导 · 全盘安装")
                            trailingText: qsTr("推荐")
                            onClicked: snackbar.show(qsTr("已选择 /dev/vda（示例）"))
                        }

                        MiplDivider { width: parent.width }

                        MiplListItem {
                            width: parent.width
                            text: qsTr("/dev/sda · 1 TiB")
                            secondaryText: qsTr("已有 3 个分区")
                            tertiaryText: qsTr("安装将清除这块盘上的全部数据")
                            onClicked: snackbar.show(qsTr("已选择 /dev/sda（示例）"))
                        }

                        MiplDivider { width: parent.width; inset: true }

                        MiplListItem {
                            width: parent.width
                            text: qsTr("手动分区")
                            trailingText: qsTr("高级")
                            onClicked: snackbar.show(qsTr("手动分区（示例）"))
                        }
                    }

                    MiplCard {
                        width: MiplSpace.page * 8
                        variant: MiplCard.Filled
                        title: qsTr("filled 卡片")
                        subtitle: qsTr("surface-container-highest · 无描边")

                        MiplButton {
                            text: qsTr("卡片里的动作")
                            variant: MiplButton.Text
                            onClicked: snackbar.show(qsTr("卡片动作（示例）"))
                        }
                    }
                }

                // 10 · Top app bar ─────────────────────────────────────────
                DemoSection {
                    heading: qsTr("10 · Top app bar（small）—— 窗口顶栏就是这个组件")

                    Text {
                        width: parent.width
                        text: qsTr("标题在左、返回在左端、动作位在右端；右侧现在挂着主题切换与「Aa」缩放菜单。")
                        color: MiplColor.onSurfaceVariant
                        font.family: MiplType.family
                        font.pixelSize: MiplType.bodyMedium.size
                        font.letterSpacing: MiplType.cjkTracking
                        wrapMode: Text.WordWrap
                    }
                }

                // 11 · Segmented button ────────────────────────────────────
                DemoSection {
                    heading: qsTr("11 · Segmented button（2–3 项互斥）")

                    MiplSegmentedButton {
                        width: MiplSpace.page * 7
                        model: [qsTr("简体中文"), qsTr("English"), qsTr("日本語")]
                        onActivated: snackbar.show(qsTr("已选语言：%1").arg(model[index]))
                    }
                }

                // 12 · Chip ────────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("12 · Chip（filter，可多选）")

                    Row {
                        spacing: MiplSpace.s

                        MiplChip { text: qsTr("中文"); checked: true }
                        MiplChip { text: qsTr("NVIDIA"); checked: true }
                        MiplChip { text: qsTr("无网安装") }
                    }
                }

                // 13 · Snackbar ────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("13 · Snackbar（非阻塞提示）")

                    MiplButton {
                        text: qsTr("显示 Snackbar")
                        variant: MiplButton.Tonal
                        onClicked: snackbar.show(qsTr("网络未连接：安装仍可继续，但不会下载更新"))
                    }
                }

                // 14 · Tooltip ─────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("14 · Tooltip（plain）—— 悬停或键盘聚焦图标按钮即可看到")

                    Row {
                        spacing: MiplSpace.l

                        MiplIconButton { iconText: qsTr("主题"); tip: MiplTheme.locked ? qsTr("已手动锁定为暗色") : qsTr("跟随时间") }
                        MiplIconButton { iconText: qsTr("网络"); tip: qsTr("当前网络未连接") }
                    }
                }

                // 15 · Menu ────────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("15 · Menu（下拉选择；顶栏「Aa」也是它）")

                    MiplButton {
                        id: moreButton

                        text: qsTr("更多操作")
                        variant: MiplButton.Outlined
                        onClicked: {
                            moreMenu.x = Math.round(moreButton.mapToItem(null, 0, moreButton.height).x)
                            moreMenu.y = Math.round(moreButton.mapToItem(null, 0, moreButton.height).y)
                            moreMenu.open()
                        }
                    }
                }

                // 16 · Divider ─────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("16 · Divider（full-width / inset / 竖线）")

                    Column {
                        width: MiplSpace.page * 8
                        spacing: MiplSpace.s

                        Text {
                            text: qsTr("全宽")
                            color: MiplColor.onSurfaceVariant
                            font.family: MiplType.family
                            font.pixelSize: MiplType.bodySmall.size
                            font.letterSpacing: MiplType.cjkTracking
                        }
                        MiplDivider { width: parent.width }

                        Text {
                            text: qsTr("inset（左侧 l 档缩进）")
                            color: MiplColor.onSurfaceVariant
                            font.family: MiplType.family
                            font.pixelSize: MiplType.bodySmall.size
                            font.letterSpacing: MiplType.cjkTracking
                        }
                        MiplDivider { width: parent.width; inset: true }

                        Row {
                            height: MiplSpace.xl
                            spacing: MiplSpace.m

                            Text {
                                text: qsTr("左")
                                color: MiplColor.onSurfaceVariant
                                font.family: MiplType.family
                                font.pixelSize: MiplType.bodySmall.size
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            MiplDivider { vertical: true; height: parent.height }
                            Text {
                                text: qsTr("右")
                                color: MiplColor.onSurfaceVariant
                                font.family: MiplType.family
                                font.pixelSize: MiplType.bodySmall.size
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }

                // 17 · Badge ───────────────────────────────────────────────
                DemoSection {
                    heading: qsTr("17 · Badge（small）")

                    Row {
                        spacing: MiplSpace.xxl

                        MiplBadge { text: "12" }
                        MiplBadge { dot: true }

                        Item {
                            width: MiplSpace.xxl + MiplSpace.s
                            height: width

                            MiplIconButton {
                                anchors.fill: parent
                                iconText: qsTr("通知")
                                tip: qsTr("有 3 条未读提示")
                            }
                            MiplBadge {
                                text: "3"
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: -MiplSpace.s
                                anchors.topMargin: -MiplSpace.xs
                            }
                        }
                    }
                }
            }
        }
    }
}
