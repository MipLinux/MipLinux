// 组件总览 —— 步骤 2 的评审用页面。
//
// 把每个控件在**它会出现的那几种状态**下同屏摆出来（默认 / 悬停 / 禁用 / 出错 /
// 危险），这样评审时不用去点每一页找边界情况。
//
//     python3 installer/frontend/tools/shots.py --page gallery --out /tmp/shots

import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "components"
import "theme"

Window {
    id: gallery
    width: 1280
    height: 1500
    visible: true
    color: Tokens.pageBg
    title: "MipLinux 安装器 · 组件总览"

    readonly property var logSample: [
        "$ pacman-key --gpgdir /mnt/etc/pacman.d/gnupg --init",
        "    目标包清单：…/data/target-packages.x86_64（8 个包）",
        "$ pacman-key --gpgdir /mnt/etc/pacman.d/gnupg --populate archlinux",
        "    ==> 正在更新信任数据库…",
        "$ pacstrap -C /etc/pacman.conf -G -M /mnt base linux linux-firmware",
        "    ==> 正在从镜像源下载…",
        "    ( 1/8) base",
        "    ( 2/8) linux",
        "    ( 3/8) linux-firmware",
        "$ arch-chroot /mnt useradd -m -G wheel -s /bin/bash mipl",
        "    写入 /mnt/etc/sudoers.d/10-wheel（mode 0440）",
        "    root 未设密码（账号保持锁定）：只能用 mipl + sudo 提权"
    ]

    readonly property var diskRows: [
        { path: "/dev/vda", model: "QEMU HARDDISK", size: "40.0 GiB",
          badges: [{ t: "将安装到这里", v: "info" }], selectable: true },
        { path: "/dev/nvme0n1", model: "Samsung SSD 990 PRO 2TB", size: "1.8 TiB",
          badges: [{ t: "正在使用", v: "danger" }, { t: "已有分区表", v: "warning" }],
          selectable: false },
        { path: "/dev/sdb", model: "SanDisk Cruzer Blade", size: "14.3 GiB",
          badges: [{ t: "太小", v: "danger" }, { t: "可移动设备", v: "warning" }],
          selectable: false }
    ]

    readonly property var checkItems: [
        { label: "网络", state: "ok", value: "已连接（有线）" },
        { label: "目标盘", state: "ok", value: "认到 1 块" },
        { label: "EFI 固件", state: "fail", value: "未检测到",
          fix: "这台机器是 BIOS 引导。v0.1 只支持 UEFI —— 请在固件设置里改回 UEFI 模式。" }
    ]

    Column {
        id: root
        x: Tokens.pagePadding
        y: Tokens.s5
        width: gallery.width - Tokens.pagePadding * 2
        spacing: Tokens.s5

        Column {
            spacing: Tokens.s1
            Text { text: "组件总览"; font: Tokens.display; color: Tokens.text }
            Text {
                text: "每个控件在它会出现的状态下同屏 —— 评审时不用去点每一页找边界情况。"
                font: Tokens.body
                color: Tokens.textMuted
            }
        }

        // ── 按钮 ────────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "按钮"; font: Tokens.heading; color: Tokens.text }

            Card {
                width: root.width
                Column {
                    width: parent.width
                    spacing: Tokens.s3

                    RowLayout {
                        spacing: Tokens.s2
                        Button { text: "开始安装" }
                        Button { text: "开始安装"; suffix: "· 3 块" }
                        Button { text: "开始安装"; enabled: false }
                    }
                    RowLayout {
                        spacing: Tokens.s2
                        Button { text: "我可以等"; variant: "secondary" }
                        Button { text: "上一步"; variant: "ghost" }
                        Button { text: "擦除并安装"; variant: "danger" }
                        Button { text: "擦除并安装"; variant: "danger"; enabled: false }
                    }
                    Text {
                        text: "一页只允许一个 primary —— 「一页一个主按钮」是减少认知负担的一部分。"
                        font: Tokens.small
                        color: Tokens.textFaint
                    }
                }
            }
        }

        // ── 表单字段 ────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "表单字段"; font: Tokens.heading; color: Tokens.text }

            Card {
                width: root.width
                RowLayout {
                    width: parent.width
                    spacing: Tokens.s4

                    Field {
                        fieldWidth: (parent.width - Tokens.s4) / 2
                        label: "用户名"
                        text: "mipl"
                        help: "小写字母开头，可含数字、下划线、连字符"
                    }
                    Field {
                        fieldWidth: (parent.width - Tokens.s4) / 2
                        label: "用户名"
                        text: "Mip Linux"
                        error: "只能用小写字母开头，且不能有空格。例如 mipl"
                    }
                }
                Field {
                    width: parent.width
                    label: "密码"
                    text: "hunter2"
                    secret: true
                }
                Field {
                    width: parent.width
                    label: "时区"
                    text: "Asia/Shanghai"
                    readOnly: true
                    help: "v0.1 默认值，装后可改"
                }
            }
        }

        // ── 提示块 ──────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "提示块"; font: Tokens.heading; color: Tokens.text }

            Alert {
                width: root.width
                variant: "danger"
                title: "盘上现有数据将全部丢失，且无法恢复。"
                message: "包括其它操作系统、个人文件与恢复分区。这一步之后无法撤销。"
            }
            Alert {
                width: root.width
                variant: "warning"
                title: "这是一块可移动设备"
                message: "如果它是你的安装 U 盘，装完就只能重做了 —— 请确认换一块盘。"
            }
            Alert {
                width: root.width
                variant: "info"
                message: "Live 介质可以拔掉，重启进入新系统。"
            }
            Alert {
                width: root.width
                variant: "success"
                message: "已装好，可以重启了。"
            }
        }

        // ── 状态胶囊 ────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "状态胶囊"; font: Tokens.heading; color: Tokens.text }

            Card {
                width: root.width
                Flow {
                    width: parent.width
                    spacing: Tokens.s2
                    Badge { variant: "neutral"; text: "已有分区表" }
                    Badge { variant: "info"; text: "将安装到这里" }
                    Badge { variant: "warning"; text: "可移动设备" }
                    Badge { variant: "danger"; text: "正在使用" }
                    Badge { variant: "danger"; text: "太小" }
                    Badge { variant: "success"; text: "已装好" }
                }
            }
        }

        // ── 磁盘行（P2 的核心控件）──────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "磁盘行"; font: Tokens.heading; color: Tokens.text }

            Column {
                width: root.width
                spacing: Tokens.s1

                Repeater {
                    model: gallery.diskRows
                    delegate: Rectangle {
                        id: diskRow
                        required property int index
                        required property var modelData
                        readonly property bool selected: diskRow.index === 0 && diskRow.modelData.selectable
                        width: root.width
                        height: 72
                        radius: Tokens.rCard
                        color: diskRow.selected ? Tokens.accentTint : Tokens.cardBg
                        border.width: diskRow.selected ? 2 : 1
                        border.color: diskRow.selected ? Tokens.accentAction
                                                       : (diskRow.modelData.selectable ? Tokens.border
                                                                                       : Tokens.disabledBg)
                        opacity: diskRow.modelData.selectable ? 1.0 : 0.72

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Tokens.s3
                            anchors.rightMargin: Tokens.s3
                            spacing: Tokens.s3

                            Rectangle {
                                width: 22
                                height: 22
                                radius: 11
                                color: "transparent"
                                border.width: diskRow.selected ? 6 : 2
                                border.color: diskRow.selected
                                              ? Tokens.accentAction
                                              : (diskRow.modelData.selectable ? Tokens.borderField
                                                                              : Tokens.disabledText)
                            }

                            Column {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: diskRow.modelData.path
                                    font: Tokens.bodyStrong
                                    color: diskRow.modelData.selectable ? Tokens.text : Tokens.textMuted
                                }
                                Text {
                                    text: diskRow.modelData.model
                                    font: Tokens.technical
                                    color: Tokens.textFaint
                                }
                            }

                            Text {
                                text: diskRow.modelData.size
                                font: Tokens.technical
                                color: Tokens.textMuted
                            }

                            RowLayout {
                                spacing: Tokens.s1
                                Repeater {
                                    model: diskRow.modelData.badges
                                    delegate: Badge {
                                        required property var modelData
                                        variant: modelData.v
                                        text: modelData.t
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── 阶段进度 ────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "阶段进度"; font: Tokens.heading; color: Tokens.text }

            Card {
                width: root.width
                Column {
                    width: parent.width
                    spacing: Tokens.s3
                    ProgressPhase { width: parent.width; current: 1 }
                    ProgressPhase { width: parent.width; current: 2; failed: true }
                    ProgressPhase { width: parent.width; finished: true }
                    Text {
                        text: "不做百分比 —— 后端事件只到阶段，装包阶段没有细粒度进度。"
                        font: Tokens.small
                        color: Tokens.textFaint
                    }
                }
            }
        }

        // ── 就绪检查 ────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "就绪检查"; font: Tokens.heading; color: Tokens.text }

            Card {
                width: root.width
                ReadyCheck { width: parent.width; items: gallery.checkItems }
            }
        }

        // ── 日志视图 ────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "日志视图"; font: Tokens.heading; color: Tokens.text }

            LogView {
                width: root.width
                height: 300
                lines: gallery.logSample
            }
        }

        // ── 分段切换 ────────────────────────────────────────────────
        Column {
            width: parent.width
            spacing: Tokens.s2
            Text { text: "分段切换"; font: Tokens.heading; color: Tokens.text }

            Card {
                width: root.width
                SegmentedToggle { options: ["中文", "English"]; currentIndex: 0 }
            }
        }
    }
}
