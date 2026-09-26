pragma Singleton

/* MipLinux 安装器 · 设计令牌 —— 全项目唯一的视觉真相。
 *
 * 「深色仪器盘」被否掉、改成浅色大圆角之后，这份文件就是设计语言的落点：
 * 颜色、圆角、间距、字体、动效全在这里，界面代码里**不许再出现字面量色值**。
 *
 * 三条从 LOGO 推出来的硬约束（详见 docs/work/tech/07-M2界面设计.md）：
 *
 * 1. **亮蓝只能装饰。** LOGO 主色 #2A78EC 压白只有 4.20:1，达不到 AA 正文。
 *    所以它单独叫 `accentDecor`，绝不放在文字或填充按钮底下；
 *    能承载文字的是 `accentAction`（5.85:1）与 `accentPress`（8.56:1）。
 *    命名上分开，是为了让「顺手用错」在 review 里一眼可见。
 * 2. **底不用纯白。** kiosk 全屏纯白发亮、层次全靠描边；浅灰底 + 纯白卡
 *    既把「层」讲清楚，又省掉重阴影 —— QEMU 下是 pixman 软件渲染，重投影很贵。
 * 3. **正文不下于 16px。** 大字、少层级，是「减少认知负担」在排版上的具体做法。
 *
 * 改动这份文件等于改设计语言：先改 docs/work/tech/07-M2界面设计.md 的对应表格，
 * 再改这里。两处不一致时以本文档为准。
 */

import QtQuick

QtObject {
    id: tokens

    // ── 品牌色（取自 LOGO 蓝色渐变）────────────────────────────────────
    //
    // 实测值来自 `convert MipLinuxLogo.png -colors 24 histogram:info:`：
    //   #2A78EC（主）· #1957CB（深）· #3389F7（浅）· #B7D1F8 / #D9E6FA（最浅）

    /// LOGO 主色。**只做装饰**：图标、进度条填充、星光、选中描边。
    /// 对白 4.20:1 —— 不许放正文，不许做填充按钮底。
    readonly property color accentDecor: "#2A78EC"

    /// 可承载文字与填充按钮的强调色（白字压它 5.85:1，它压白也 5.85:1）。
    readonly property color accentAction: "#1A5FD0"

    /// 按下态 / 深底（白字压它 8.56:1）。
    readonly property color accentPress: "#12489F"

    /// 选中项底、进度轨道、浅色标签底。装饰，不承担信息。
    readonly property color accentTint: "#EAF2FE"

    /// 选中态描边。仅装饰（对白 1.52:1，不传达任何含义）。
    readonly property color accentBorder: "#BBD3F8"

    // ── 中性面 ────────────────────────────────────────────────────────

    /// 页面底。故意不用纯白 —— 理由见文件头第 2 条。
    readonly property color pageBg: "#F5F7FB"

    /// 卡片 / 抬升面。
    readonly property color cardBg: "#FFFFFF"

    /// 悬停、分组底、表头这类「比卡片再低一层」的填充。
    readonly property color subtleBg: "#F0F3F9"

    /// 分隔线与卡片描边。装饰用。
    readonly property color border: "#E3E8F0"

    /// 输入框描边：比 border 深一档，让「这里能打字」看得出来。
    readonly property color borderField: "#CBD4E2"

    // ── 文字（对比度全部实测，不是估算）────────────────────────────────

    /// 主文字。对底 16.07:1。
    readonly property color text: "#171B24"

    /// 次要文字。对白 6.77:1。
    readonly property color textMuted: "#525C6B"

    /// 提示文字。对白 4.55:1 ✅ —— **只允许放在卡片上**：
    /// 它对页面底（#F5F7FB）是 4.24:1，达不到正文的 4.5:1。
    readonly property color textFaint: "#6B7787"

    /// 主按钮上的文字。
    readonly property color textOnAccent: "#FFFFFF"

    // ── 语义色 ────────────────────────────────────────────────────────

    /// 危险文字（对白 4.95:1）。
    readonly property color danger: "#D32F3D"

    /// 危险填充底（白字压它 5.62:1）。
    readonly property color dangerFill: "#C62828"

    /// 危险浅底（警告块、行内错误背景）。
    readonly property color dangerTint: "#FDECEE"

    /// 危险描边。
    readonly property color dangerBorder: "#F5C2C7"

    /// 成功文字（对白 5.04:1）。
    readonly property color success: "#1B7F45"

    /// 成功浅底。
    readonly property color successTint: "#E9F6EE"

    /// 警告文字（对白 5.00:1）。
    readonly property color warning: "#9A6400"

    /// 警告浅底。
    readonly property color warningTint: "#FDF4E3"

    /// 警告描边。
    readonly property color warningBorder: "#F0D9A8"

    /// 焦点环。也是键盘可达性的唯一可见凭据（对白 4.20:1，UI 元件达标）。
    readonly property color focusRing: "#2A78EC"

    /// 禁用态填充与文字（禁用文字对白 2.8:1 —— 禁用内容豁免 AA，
    /// 但**不许**把有用信息做成禁用的样子）。
    readonly property color disabledBg: "#EDF1F7"
    readonly property color disabledText: "#A3ADBD"

    // ── 圆角：「大圆角」的具体值 ────────────────────────────────────────

    readonly property int rControl: 12   // 输入框、下拉、小控件
    readonly property int rPill: 999     // 按钮（胶囊）
    readonly property int rCard: 20      // 卡片
    readonly property int rPanel: 24     // 大面板、欢迎页主视觉容器

    // ── 间距：8px 基准 ────────────────────────────────────────────────

    readonly property int s1: 8
    readonly property int s2: 16
    readonly property int s3: 24
    readonly property int s4: 32
    readonly property int s5: 48
    readonly property int s6: 64

    /// 页面左右内边距。
    readonly property int pagePadding: 48

    /// 卡片内边距。
    readonly property int cardPadding: 24

    /// 内容最大宽度。「中文正文行宽 ≤ 32 全角字」在 16px 下约合 560px，
    /// 加两侧内边距与卡片留白就是它。
    readonly property int contentMaxWidth: 880

    // ── 字号（px）─────────────────────────────────────────────────────
    //
    // 层级刻意少：大字 + 少层级 = 好读。行高在 FontSpec 里按倍数给。

    readonly property int fsTitle: 30    // 每页一句主标
    readonly property int fsHeading: 20  // 卡片标题
    readonly property int fsBody: 16     // 正文（下限，不再小）
    readonly property int fsSmall: 14    // 辅助说明、行内错误
    readonly property int fsMicro: 12    // 脚注、徽标

    // ── 字体 ──────────────────────────────────────────────────────────
    //
    // 只用 Live 环境里确实存在、且实测 fc-match 解析得到的这两族：
    //   Noto Sans CJK SC  ← noto-fonts-cjk
    //   Maple Mono NF CN  ← ttf-maplemono-nf-cn-unhinted
    // **显式指定字体族**，不依赖 fontconfig 的 fallback —— 实测宿主的
    // `sans-serif:lang=zh-cn` 会落到 wqy-zenhei，与 Live 不是同一个结果。

    readonly property string fontSans: "Noto Sans CJK SC"
    readonly property string fontMono: "Maple Mono NF CN"

    // ── 动效 ──────────────────────────────────────────────────────────

    /// 状态变化：悬停、按下、勾选。
    readonly property int motionFast: 140

    /// 翻页、面板展开、主视觉淡入。
    readonly property int motionNormal: 240

    // ── 阴影：极轻 ────────────────────────────────────────────────────
    //
    // 层次主要靠描边（QEMU 是软件渲染，重投影很贵）。这两个是「加分项」，
    // 拿不到硬件合成时不要指望它们撑起层次。

    readonly property real cardRadius: 6
    readonly property color cardShadow: Qt.rgba(23 / 255, 27 / 255, 36 / 255, 0.06)
    readonly property real raisedRadius: 18
    readonly property color raisedShadow: Qt.rgba(23 / 255, 27 / 255, 36 / 255, 0.10)

    // ── 速查：字体构造器 ──────────────────────────────────────────────
    //
    // QML 的 font 属性不能从字符串拼，所以这里给几个现成的 FontSpec。
    // 用法：`font: Tokens.body` / `font: Tokens.technical`

    readonly property var display: ({ family: tokens.fontSans, pixelSize: tokens.fsTitle,
                                      weight: Font.DemiBold })
    readonly property var heading: ({ family: tokens.fontSans, pixelSize: tokens.fsHeading,
                                      weight: Font.DemiBold })
    readonly property var body: ({ family: tokens.fontSans, pixelSize: tokens.fsBody,
                                   weight: Font.Normal })
    readonly property var bodyStrong: ({ family: tokens.fontSans, pixelSize: tokens.fsBody,
                                         weight: Font.DemiBold })
    readonly property var small: ({ family: tokens.fontSans, pixelSize: tokens.fsSmall,
                                    weight: Font.Normal })
    readonly property var micro: ({ family: tokens.fontSans, pixelSize: tokens.fsMicro,
                                    weight: Font.Normal })
    readonly property var technical: ({ family: tokens.fontMono, pixelSize: tokens.fsSmall,
                                        weight: Font.Normal })
    readonly property var technicalSmall: ({ family: tokens.fontMono, pixelSize: tokens.fsMicro,
                                             weight: Font.Normal })
}
