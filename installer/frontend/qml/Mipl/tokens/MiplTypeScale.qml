import QtQuick

// MiplType 每档字形的值类型：15 档各实例化一次，所以**不是**单例。
// size / lineHeight 由 MiplType 内部乘好 MiplScale.factor；tracking / weight 不缩放。
QtObject {
    property real size: 0
    property real lineHeight: 0
    property real tracking: 0
    property int weight: 400
}
