pragma Singleton
import QtQuick

// MD3 15 档字形（§3.2）。size / lineHeight 的基准值在单例内部乘一次 MiplScale.factor；
// tracking（字距）与 weight 不缩放。
// CJK 追加规则：渲染中文串时把字距换成常量 cjkTracking（0）——中文没有词间空格，
// 官方那套拉丁字距直接套会偏散。行高沿用官方值。
// 家族映射（Live 里没有 Roboto）：拉丁 Noto Sans / 中文 Noto Sans CJK SC / 等宽 Noto Sans Mono。
QtObject {
    readonly property string family: "Noto Sans"
    readonly property string familyCjk: "Noto Sans CJK SC"
    readonly property string familyMono: "Noto Sans Mono"

    // 渲染中文串时的字距常量
    readonly property real cjkTracking: 0

    readonly property MiplTypeScale displayLarge: MiplTypeScale {
        size: 57 * MiplScale.factor
        lineHeight: 64 * MiplScale.factor
        tracking: -0.25
        weight: 400
    }
    readonly property MiplTypeScale displayMedium: MiplTypeScale {
        size: 45 * MiplScale.factor
        lineHeight: 52 * MiplScale.factor
        tracking: 0
        weight: 400
    }
    readonly property MiplTypeScale displaySmall: MiplTypeScale {
        size: 36 * MiplScale.factor
        lineHeight: 44 * MiplScale.factor
        tracking: 0
        weight: 400
    }
    readonly property MiplTypeScale headlineLarge: MiplTypeScale {
        size: 32 * MiplScale.factor
        lineHeight: 40 * MiplScale.factor
        tracking: 0
        weight: 400
    }
    readonly property MiplTypeScale headlineMedium: MiplTypeScale {
        size: 28 * MiplScale.factor
        lineHeight: 36 * MiplScale.factor
        tracking: 0
        weight: 400
    }
    readonly property MiplTypeScale headlineSmall: MiplTypeScale {
        size: 24 * MiplScale.factor
        lineHeight: 32 * MiplScale.factor
        tracking: 0
        weight: 400
    }
    readonly property MiplTypeScale titleLarge: MiplTypeScale {
        size: 22 * MiplScale.factor
        lineHeight: 28 * MiplScale.factor
        tracking: 0
        weight: 400
    }
    readonly property MiplTypeScale titleMedium: MiplTypeScale {
        size: 16 * MiplScale.factor
        lineHeight: 24 * MiplScale.factor
        tracking: 0.15
        weight: 500
    }
    readonly property MiplTypeScale titleSmall: MiplTypeScale {
        size: 14 * MiplScale.factor
        lineHeight: 20 * MiplScale.factor
        tracking: 0.10
        weight: 500
    }
    readonly property MiplTypeScale bodyLarge: MiplTypeScale {
        size: 16 * MiplScale.factor
        lineHeight: 24 * MiplScale.factor
        tracking: 0.50
        weight: 400
    }
    readonly property MiplTypeScale bodyMedium: MiplTypeScale {
        size: 14 * MiplScale.factor
        lineHeight: 20 * MiplScale.factor
        tracking: 0.25
        weight: 400
    }
    readonly property MiplTypeScale bodySmall: MiplTypeScale {
        size: 12 * MiplScale.factor
        lineHeight: 16 * MiplScale.factor
        tracking: 0.40
        weight: 400
    }
    readonly property MiplTypeScale labelLarge: MiplTypeScale {
        size: 14 * MiplScale.factor
        lineHeight: 20 * MiplScale.factor
        tracking: 0.10
        weight: 500
    }
    readonly property MiplTypeScale labelMedium: MiplTypeScale {
        size: 12 * MiplScale.factor
        lineHeight: 16 * MiplScale.factor
        tracking: 0.50
        weight: 500
    }
    readonly property MiplTypeScale labelSmall: MiplTypeScale {
        size: 11 * MiplScale.factor
        lineHeight: 16 * MiplScale.factor
        tracking: 0.50
        weight: 500
    }
}
