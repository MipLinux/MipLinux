pragma Singleton
import QtQuick

// MD3 35 个核心颜色角色。
// 字面值唯一来源：本目录 color.json（快照与断言输入）。运行期不读 JSON、不做任何计算。
// 键名 kebab-case -> 小驼峰；每个角色 = MiplTheme.dark ? 暗色值 : 亮色值。
//
// on-* 那 10 个角色为什么要绕一层嵌套对象 + alias：
// ① QML 把同一对象里**带初值**的 `onXxx` 声明当作「信号 Xxx 的处理器」；同对象只要还有
//    一个首字母小写的 `xxx` 成员，编译就报 “Cannot assign a value to a signal (expecting
//    a script to be run)”，整个类型直接不可用（实测：`readonly property color onPrimary:`
//    与 `readonly property color primary:` 同文件即失败；拆到两个文件就正常）。MD3 的
//    on-primary / on-surface … 恰好各自都有一个 primary / surface … 兄弟，35 个里 10 个全踩。
//    alias 声明不受这条规则约束，所以把 on-* 放进一个**只声明 on-* 的嵌套对象**，再用
//    readonly alias 平铺出来：对消费方仍是 `MiplColor.onPrimary`，仍然 readonly + 响应主题。
// ② 这个嵌套对象用 `property var` 而不是 `property QtObject`：实测「先建 QQmlEngine、
//    再 qmlRegisterSingletonInstance 注册 MiplLaunch」时，`property QtObject x: QtObject {}`
//    会报 “Cannot assign object of type "QtObject" to property of type "QObject*"”；
//    `property var` 两种注册顺序都正常（复合类型属性如 MiplType 的 MiplTypeScale 也不受影响）。
QtObject {
    readonly property color primary: MiplTheme.dark ? "#adc6ff" : "#445e91"
    readonly property color primaryContainer: MiplTheme.dark ? "#2b4678" : "#d8e2ff"
    readonly property color secondary: MiplTheme.dark ? "#bfc6dc" : "#565e71"
    readonly property color secondaryContainer: MiplTheme.dark ? "#3f4759" : "#dbe2f9"
    readonly property color tertiary: MiplTheme.dark ? "#debcdf" : "#715574"
    readonly property color tertiaryContainer: MiplTheme.dark ? "#583e5b" : "#fbd7fc"
    readonly property color error: MiplTheme.dark ? "#ffb4ab" : "#ba1a1a"
    readonly property color errorContainer: MiplTheme.dark ? "#93000a" : "#ffdad6"
    readonly property color surface: MiplTheme.dark ? "#111318" : "#f9f9ff"
    readonly property color surfaceVariant: MiplTheme.dark ? "#44474f" : "#e1e2ec"
    readonly property color surfaceDim: MiplTheme.dark ? "#111318" : "#d9d9e0"
    readonly property color surfaceBright: MiplTheme.dark ? "#37393e" : "#f9f9ff"
    readonly property color surfaceContainerLowest: MiplTheme.dark ? "#0c0e13" : "#ffffff"
    readonly property color surfaceContainerLow: MiplTheme.dark ? "#1a1b20" : "#f3f3fa"
    readonly property color surfaceContainer: MiplTheme.dark ? "#1e1f25" : "#ededf4"
    readonly property color surfaceContainerHigh: MiplTheme.dark ? "#282a2f" : "#e8e7ee"
    readonly property color surfaceContainerHighest: MiplTheme.dark ? "#33353a" : "#e2e2e9"
    readonly property color outline: MiplTheme.dark ? "#8e9099" : "#74777f"
    readonly property color outlineVariant: MiplTheme.dark ? "#44474f" : "#c4c6d0"
    readonly property color scrim: MiplTheme.dark ? "#000000" : "#000000"
    readonly property color shadow: MiplTheme.dark ? "#000000" : "#000000"
    readonly property color surfaceTint: MiplTheme.dark ? "#adc6ff" : "#445e91"
    readonly property color inverseSurface: MiplTheme.dark ? "#e2e2e9" : "#2f3036"
    readonly property color inverseOnSurface: MiplTheme.dark ? "#2f3036" : "#f0f0f7"
    readonly property color inversePrimary: MiplTheme.dark ? "#445e91" : "#adc6ff"

    // on-* 的取值（只为避开上面那条 QML 规则而嵌套；不对外暴露这一层）
    readonly property var _onRoles: QtObject {
        id: onRoles
        readonly property color onPrimary: MiplTheme.dark ? "#102f60" : "#ffffff"
        readonly property color onPrimaryContainer: MiplTheme.dark ? "#d8e2ff" : "#2b4678"
        readonly property color onSecondary: MiplTheme.dark ? "#283041" : "#ffffff"
        readonly property color onSecondaryContainer: MiplTheme.dark ? "#dbe2f9" : "#3f4759"
        readonly property color onTertiary: MiplTheme.dark ? "#402843" : "#ffffff"
        readonly property color onTertiaryContainer: MiplTheme.dark ? "#fbd7fc" : "#583e5b"
        readonly property color onError: MiplTheme.dark ? "#690005" : "#ffffff"
        readonly property color onErrorContainer: MiplTheme.dark ? "#ffdad6" : "#93000a"
        readonly property color onSurface: MiplTheme.dark ? "#e2e2e9" : "#1a1b20"
        readonly property color onSurfaceVariant: MiplTheme.dark ? "#c4c6d0" : "#44474f"
    }

    readonly property alias onPrimary: onRoles.onPrimary
    readonly property alias onPrimaryContainer: onRoles.onPrimaryContainer
    readonly property alias onSecondary: onRoles.onSecondary
    readonly property alias onSecondaryContainer: onRoles.onSecondaryContainer
    readonly property alias onTertiary: onRoles.onTertiary
    readonly property alias onTertiaryContainer: onRoles.onTertiaryContainer
    readonly property alias onError: onRoles.onError
    readonly property alias onErrorContainer: onRoles.onErrorContainer
    readonly property alias onSurface: onRoles.onSurface
    readonly property alias onSurfaceVariant: onRoles.onSurfaceVariant
}
