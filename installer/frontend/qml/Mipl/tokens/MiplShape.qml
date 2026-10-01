pragma Singleton
import QtQuick

// MD3 7 档形状（§3.3），单位 px。基准值在单例内部乘一次 MiplScale.factor。
// none 缩放后恒为 0；full 是哨兵（组件要真胶囊 / 正圆时写 height / 2），不是可用的物理尺寸。
QtObject {
    readonly property real none: 0 * MiplScale.factor
    readonly property real extraSmall: 4 * MiplScale.factor
    readonly property real small: 8 * MiplScale.factor
    readonly property real medium: 12 * MiplScale.factor
    readonly property real large: 16 * MiplScale.factor
    readonly property real extraLarge: 28 * MiplScale.factor
    readonly property real full: 9999 * MiplScale.factor
}
