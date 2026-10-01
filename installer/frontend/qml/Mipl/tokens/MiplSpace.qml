pragma Singleton
import QtQuick

// MD3 间距（§3.4）：4px 网格上的 6 档 + 页面级 1 档，单位 px。
// 基准值在单例内部乘一次 MiplScale.factor；组件侧绝不再乘。
QtObject {
    readonly property real xs: 4 * MiplScale.factor
    readonly property real s: 8 * MiplScale.factor
    readonly property real m: 12 * MiplScale.factor
    readonly property real l: 16 * MiplScale.factor
    readonly property real xl: 24 * MiplScale.factor
    readonly property real xxl: 32 * MiplScale.factor
    readonly property real page: 48 * MiplScale.factor
}
