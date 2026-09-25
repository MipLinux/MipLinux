// 阶段进度：分段的横条 + 段落标签。
//
// **不做百分比。** 后端事件只到阶段（events.PHASES），装包阶段的细粒度进度没有 ——
// 编一个假百分比到 99% 卡住，比诚实的分段更伤信任（tech/07 §P4）。
// 「还活着」的凭据由「已用时」与滚动日志承担，不在这里假装。

import QtQuick
import "../theme"

Item {
    id: progress

    //: 段名（显示用）与当前下标。
    //: **默认值就是后端 `events.PHASES` 六个阶段的中文标签**，顺序即执行顺序 ——
    //: 旧的「磁盘 / 账户 / 安装」三段是旧流程的产物，与后端事件对不上（`start`、
    //: `configure`、`boot` 落在哪一段没人说得清），已改掉（2026-09-25）。
    //: 调用方（InstallPage）会显式传自己那份；这里留同样的默认值，只是让
    //: 「忘了传」的页面也不会画出对不上后端的东西。改后端 PHASES 要同步这两处。
    property var segments: ["准备", "磁盘", "装包", "配置", "引导", "完成"]
    property int current: 0
    /// 全部完成（完成页用）
    property bool finished: false
    /// 当前段失败：该段转红，但仍显示在哪一段失败的
    property bool failed: false

    /// 段与段标签之间的行距（对外接口；转发给内部 Column）
    property alias spacing: column.spacing
    readonly property int _active: finished ? -1 : Math.max(0, Math.min(current, segments.length - 1))

    //: 给一个**不依赖父宽**的 implicitWidth：它的宽度按父宽算，若再让父容器
    //: 用 implicitWidth 定宽，两边就接成一个布局循环（实测报 polish loop）。
    //: 固定值即可断开。
    implicitWidth: 600
    implicitHeight: column.implicitHeight

    Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Tokens.s2

        Row {
            width: parent.width
            spacing: Tokens.s1

            Repeater {
                model: progress.segments
                delegate: Column {
                    id: segment
                    required property int index
                    required property string modelData

                    width: (progress.width - Tokens.s1 * (progress.segments.length - 1))
                           / progress.segments.length
                    spacing: Tokens.s1

                    Rectangle {
                        id: segBar
                        width: parent.width
                        height: 6
                        radius: 3
                        color: {
                            if (progress.failed && segment.index === progress._active)
                                return Tokens.danger;
                            if (segment.index < progress._active || progress.finished)
                                return Tokens.accentAction;   // 已完成
                            if (segment.index === progress._active)
                                return Tokens.accentDecor;    // 进行中
                            return Tokens.accentTint;         // 未开始
                        }

                        // **不确定态的「还在等」**：当前段里一条来回走的浅色带。
                        // 它不表示任何百分比 —— 后端事件只到阶段，编一个假进度爬到
                        // 99% 卡住，比诚实的分段更伤信任（tech/07 §P4）。
                        // 只有当前段有它，所以一眼能同时看出「停在哪一段」与「还在动」。
                        Rectangle {
                            id: pulse
                            visible: segment.index === progress._active
                                     && !progress.finished && !progress.failed
                            width: Math.min(28, segBar.width / 3)
                            height: segBar.height
                            radius: segBar.radius
                            color: Tokens.accentTint
                            opacity: 0.85
                            x: 0

                            SequentialAnimation on x {
                                running: pulse.visible
                                loops: Animation.Infinite
                                NumberAnimation {
                                    from: 0
                                    to: Math.max(0, segBar.width - pulse.width)
                                    duration: 1200
                                    easing.type: Easing.InOutQuad
                                }
                                NumberAnimation {
                                    from: Math.max(0, segBar.width - pulse.width)
                                    to: 0
                                    duration: 1200
                                    easing.type: Easing.InOutQuad
                                }
                            }
                        }
                    }

                    Text {
                        width: parent.width
                        text: segment.modelData
                        font: segment.index === progress._active ? Tokens.bodyStrong : Tokens.small
                        color: {
                            if (segment.index === progress._active)
                                return progress.failed ? Tokens.danger : Tokens.text;
                            if (segment.index < progress._active || progress.finished)
                                return Tokens.textMuted;
                            return Tokens.textFaint;
                        }
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
