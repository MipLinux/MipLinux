pragma Singleton
import QtQuick

// 界面层缩放（§3.10 的两层缩放里的「界面层」）。
// 纪律：MiplType / MiplShape / MiplSpace 的基准尺寸在各自单例内部乘一次 factor；
// 组件侧绝不再乘，也绝不碰 devicePixelRatio / Screen.devicePixelRatio（双重缩放）。
// 版式断点只由屏幕逻辑宽决定，不受 factor 影响。
QtObject {
    // 用户在界面里调的倍数；实时生效、不写盘。默认 1.0。
    property real factor: 1.0

    // 四档：小 / 默认 / 大 / 更大
    readonly property var steps: [0.85, 1.0, 1.15, 1.3]
    // 菜单项必须带百分比，否则「大」到底多大没人知道。
    readonly property var labels: ["小 85%", "默认 100%", "大 115%", "更大 130%"]
}
