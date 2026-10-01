pragma Singleton
import QtQuick

// MD3 动效（§3.6）。
// 时长 = 基准值 × motionScale；**不乘** MiplScale.factor（界面层缩放不改变动画快慢）。
// motionScale = 0 表示关闭动效（无障碍设置 / 低配机）——此时所有时长为 0。
// 缓动是 (x1, y1, x2, y2) 四元组，用法：
//     easing.type: Easing.Bezier; easing.bezierCurve: MiplMotion.easingStandard
// 首帧零动效：首屏不挂动画，进度条循环动效在第一帧之后启动。
QtObject {
    // 全局动效倍数；0 = 关闭动效。
    property real motionScale: 1.0

    readonly property real short1: 50 * motionScale
    readonly property real short2: 100 * motionScale
    readonly property real short3: 150 * motionScale
    readonly property real short4: 200 * motionScale
    readonly property real medium1: 250 * motionScale
    readonly property real medium2: 300 * motionScale
    readonly property real medium3: 350 * motionScale
    readonly property real medium4: 400 * motionScale
    readonly property real long1: 450 * motionScale
    readonly property real long2: 500 * motionScale
    readonly property real long3: 550 * motionScale
    readonly property real long4: 600 * motionScale
    readonly property real extraLong1: 700 * motionScale
    readonly property real extraLong2: 800 * motionScale
    readonly property real extraLong3: 900 * motionScale
    readonly property real extraLong4: 1000 * motionScale

    readonly property var easingStandard: [0.2, 0, 0, 1]
    readonly property var easingEmphasized: [0.2, 0, 0, 1]
    readonly property var easingStandardAccelerate: [0.3, 0, 1, 1]
    readonly property var easingStandardDecelerate: [0, 0, 0, 1]
    readonly property var easingEmphasizedAccelerate: [0.3, 0, 0.8, 0.15]
    readonly property var easingEmphasizedDecelerate: [0.05, 0.7, 0.1, 1]
    readonly property var easingLinear: [0, 0, 1, 1]
}
