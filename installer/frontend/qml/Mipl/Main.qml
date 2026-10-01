// Main.qml —— 阶段 0 的最小根页面（Issue #79 的启动器接线）。
//
// 目的只有一个：把「启动器首帧之前注入的主题 / 设备层缩放」与「界面层 MiplScale」
// 串起来，让 cage 里能起出第一屏、让宿主机 `mipl-installer --self-test` 能断言注入值。
// **不是最终版式**：08 §4.2 的排除项（bottom sheet / navigation rail / FAB / …）一律不做。
//
// 根页面不自己算任何策略：主题来自 `MiplTheme`（读 `MiplLaunch.theme`），
// 设备层缩放来自启动器写好的 `QT_SCALE_FACTOR`，界面层缩放由 `MiplScale.factor` 承担。
// 纪律：不碰 devicePixelRatio / Screen.devicePixelRatio（双重缩放，08 §3.10 的禁止项）。
import QtQuick
import QtQuick.Controls.Basic
import Mipl 1.0

ApplicationWindow {
    id: root

    visible: true
    width: 1280
    height: 800
    title: qsTr("MipLinux 安装器")
    color: MiplColor.surface

    MiplTopAppBar {
        id: appBar

        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        title: qsTr("MipLinux 安装器")
        showBack: false

        // 主题切换（08 §3.9）：亮 ↔ 暗，点一下就在本次会话内锁定。
        // 图标文字表示「点下去会切到哪套」；当前状态看 tooltip（规格要求 tooltip 显示状态）。
        MiplIconButton {
            id: themeButton

            iconText: MiplTheme.dark ? qsTr("亮") : qsTr("暗")
            tip: MiplTheme.locked
                 ? (MiplTheme.manualDark ? qsTr("已手动锁定为暗色") : qsTr("已手动锁定为亮色"))
                 : qsTr("跟随时间")

            onClicked: {
                MiplTheme.locked = true
                MiplTheme.manualDark = !MiplTheme.dark
            }
        }

        // 界面层缩放（08 §3.10）：「Aa」→ 四档菜单，实时生效、不写盘。
        MiplIconButton {
            id: scaleButton

            iconText: "Aa"
            tip: qsTr("界面缩放（当前 %1%）").arg(Math.round(MiplScale.factor * 100))
            onClicked: scaleMenu.open()
        }
    }

    // 缩放菜单挂根上：Popup 的 x/y 相对窗口内容区，右对齐 app bar 的右缘。
    MiplMenu {
        id: scaleMenu

        x: appBar.width - width
        y: appBar.height

        // checked 用命令式维护、**不**直接绑定：QQC 的 MenuItem 点击时会自己 toggle
        // `checked`，绑定被那次写入打断后这个档位就再也不更新了。
        function syncChecks() {
            const factor = MiplScale.factor
            const steps = MiplScale.steps
            itemSmall.checked = Math.abs(factor - steps[0]) < 0.001
            itemDefault.checked = Math.abs(factor - steps[1]) < 0.001
            itemLarge.checked = Math.abs(factor - steps[2]) < 0.001
            itemLarger.checked = Math.abs(factor - steps[3]) < 0.001
        }

        onAboutToShow: syncChecks()

        MiplMenuItem {
            id: itemSmall
            checkable: true
            text: MiplScale.labels[0]
            onTriggered: {
                MiplScale.factor = MiplScale.steps[0]
                scaleMenu.syncChecks()
            }
        }

        MiplMenuItem {
            id: itemDefault
            checkable: true
            text: MiplScale.labels[1]
            onTriggered: {
                MiplScale.factor = MiplScale.steps[1]
                scaleMenu.syncChecks()
            }
        }

        MiplMenuItem {
            id: itemLarge
            checkable: true
            text: MiplScale.labels[2]
            onTriggered: {
                MiplScale.factor = MiplScale.steps[2]
                scaleMenu.syncChecks()
            }
        }

        MiplMenuItem {
            id: itemLarger
            checkable: true
            text: MiplScale.labels[3]
            onTriggered: {
                MiplScale.factor = MiplScale.steps[3]
                scaleMenu.syncChecks()
            }
        }
    }

    Column {
        id: body

        anchors.top: appBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: MiplSpace.page
        spacing: MiplSpace.m

        Text {
            width: parent.width
            text: qsTr("阶段 0 的最小根页面：只用来验证主题与两层缩放是否接通，不是最终版式。")
            color: MiplColor.onSurface
            font.family: MiplType.family
            font.pixelSize: MiplType.headlineSmall.size
            font.weight: MiplType.headlineSmall.weight
            font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                        : MiplType.headlineSmall.tracking
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        Text {
            width: parent.width
            text: qsTr("设备层缩放（启动器写入 QT_SCALE_FACTOR）：%1x").arg(MiplLaunch.deviceScale)
            color: MiplColor.onSurfaceVariant
            font.family: MiplType.family
            font.pixelSize: MiplType.bodyMedium.size
            font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                        : MiplType.bodyMedium.tracking
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        Text {
            width: parent.width
            text: qsTr("界面层缩放（MiplScale.factor）：%1%").arg(Math.round(MiplScale.factor * 100))
            color: MiplColor.onSurfaceVariant
            font.family: MiplType.family
            font.pixelSize: MiplType.bodyMedium.size
            font.letterSpacing: /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? MiplType.cjkTracking
                                                                        : MiplType.bodyMedium.tracking
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        Text {
            width: parent.width
            text: qsTr("主题：%1（themeSource=%2）")
                      .arg(MiplTheme.dark ? qsTr("暗色") : qsTr("亮色"))
                      .arg(MiplTheme.source)
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
