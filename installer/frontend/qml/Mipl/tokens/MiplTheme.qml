pragma Singleton
import QtQuick
// 这一行不能删：MiplLaunch 是启动器在 engine.load() 之前用 qmlRegisterSingletonInstance
// 注册进 Mipl 1.0 的（不在 qmldir 里），模块内文件只有显式 import 自己才能解析它；
// 少了这行，下面的 typeof 恒为 "undefined"，自动主题永远走回落分支（本机实测过这个差异）。
import Mipl 1.0

// 主题状态（§3.9）。dark 是只读派生量，写入面只有 locked / manualDark 两个。
QtObject {
    // 顶部 app bar 的主题按钮写：locked = true; manualDark = !dark
    property bool locked: false
    property bool manualDark: false

    // 自动模式下跟随启动器首帧之前解析好的主题；manual 锁定后不再理会 MiplLaunch.theme。
    // MiplLaunch 未注册时（只加载 token 单例的探针 / 单测）回落暗色：这是本层唯一的兜底口径。
    readonly property bool dark: locked
        ? manualDark
        : (typeof MiplLaunch === "undefined" ? true : MiplLaunch.theme === "dark")

    // 与 MiplLaunch.themeSource 同一口径：手动锁定后为 "manual"。
    readonly property string source: locked ? "manual" : "auto"
}
