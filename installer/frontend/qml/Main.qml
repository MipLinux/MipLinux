// MipLinux 安装器 —— 流程壳。**整个程序只有这一个 Window。**
//
// 为什么只有一个窗口：cage 是单窗口 kiosk 合成器（一次只认一个顶层窗口），
// 「翻页」不能靠开关窗口。页面都是 `Loader` 换进换出的 Item ——
// `components/PageShell.qml` 的根从 Window 改成 Item 就是为了这件事。
//
// ── 这一版**不接后端**（G3 口径，2026-09-25 评审确认）────────────────────
// 安装页的阶段 / 当前动作 / 日志由下面那段**假脚本**演出来，不驱动真安装。
// 真接线（后端 events 事件流 + InstallerError）见 `bridge/README.md`，到那时：
//   · `phase` / `currentAction` / `logLines` 由 `QtReporter` 喂（不是 demoTick）；
//   · 「立即重启」调 `systemctl reboot`（不是 `Qt.quit()`）；
//   · 语言 / 键盘 / 时区 / 主机名 / 账户 / 目标盘走 cli.py 的参数交给后端。
//
// ── 流程（2026-09-25 评审定的顺序）──────────────────────────────────────
//   加载 → 欢迎 → 网络 → 系统磁盘 → 磁盘分区 → 确认擦除 → 账户 → 安装详情
//        → 安装 → 结束
//   分支：欢迎页的「高级安装」→ 高级安装（语言 / 键盘 / 时区 / 主机名）
//
// 语言 / 键盘 / 时区 / 主机名**不在主流程里**：四项都有能用的默认值
// （zh_CN.UTF-8 / us / Asia/Shanghai / mipl），要改的人从「高级安装」进去。
// 一屏一决策，主流程越短越好（tech/07 §3）。
//
// 网络页**无论通不通都出现**（评审口径：直接跳过会留下不安），
// 所以它不是一个「条件插入」的步骤，而是固定一屏。

import QtQuick
import QtQuick.Window
import "theme"

Window {
    id: root

    width: 1280
    height: 800
    visible: true
    color: Tokens.pageBg
    title: "MipLinux 安装器"

    // ── 流程状态：页面之间只通过这里传值 ───────────────────────────────
    property string localeName: "zh_CN.UTF-8"
    property string keymap: "us"
    property string timezone: "Asia/Shanghai"
    property string hostName: "mipl"

    property string targetDisk: ""
    property string diskModel: ""
    property string diskSize: ""

    property string userName: ""
    property string userPassword: ""
    property bool setRootPassword: false

    //: 网络状态：**默认在线**（演示）。网络页永远展示，只是按钮文案跟着变。
    property bool networkOnline: true

    //: 高级安装里「改过的项」打蓝点用的默认值
    readonly property string defaultLocale: "zh_CN.UTF-8"
    readonly property string defaultKeymap: "us"
    readonly property string defaultTimezone: "Asia/Shanghai"
    readonly property string defaultHostname: "mipl"

    // ── 路由 ──────────────────────────────────────────────────────────
    //: 当前页（`--set page=…` 可以把取图工具直接送到某一屏）
    property string page: "loading"
    //: 返回栈。`go()` 会压栈，`replace()` 不会（加载页、装完跳结束页用后者）
    property var history: []

    readonly property var pageFiles: ({
        "loading": "pages/LoadingPage.qml",
        "welcome": "pages/WelcomePage.qml",
        "network": "pages/NetworkPage.qml",
        "disk": "pages/DiskPage.qml",
        "partition": "pages/PartitionPage.qml",
        "erase-confirm": "pages/EraseConfirmPage.qml",
        "account": "pages/AccountPage.qml",
        "install-details": "pages/InstallDetailsPage.qml",
        "install": "pages/InstallPage.qml",
        "done": "pages/DonePage.qml",
        "advanced": "pages/AdvancedPage.qml",
        "language": "pages/LanguagePage.qml",
        "keyboard": "pages/KeyboardPage.qml",
        "timezone": "pages/TimezonePage.qml",
        "hostname": "pages/HostnamePage.qml"
    })

    function go(name) {
        history = history.concat([page]);
        page = name;
    }

    function replace(name) {
        page = name;
    }

    function back() {
        if (history.length === 0)
            return;
        page = history[history.length - 1];
        history = history.slice(0, history.length - 1);
    }

    /// 高级安装的四行：显示当前值，改过的打蓝点
    function advancedRows() {
        return [
            {
                page: "language",
                label: "语言",
                value: root.localeName,
                changed: root.localeName !== root.defaultLocale
            },
            {
                page: "keyboard",
                label: "键盘",
                value: root.keymap,
                changed: root.keymap !== root.defaultKeymap
            },
            {
                page: "timezone",
                label: "时区",
                value: root.timezone,
                changed: root.timezone !== root.defaultTimezone
            },
            {
                page: "hostname",
                label: "主机名",
                value: root.hostName,
                changed: root.hostName !== root.defaultHostname
            }
        ];
    }

    /// 从选盘页的候选里把型号与容量记下来（详情页要用，前端不自己编）
    function rememberDisk(candidates, device) {
        for (var i = 0; i < candidates.length; i++) {
            if (candidates[i].path === device) {
                root.diskModel = candidates[i].model;
                root.diskSize = candidates[i].size;
                return;
            }
        }
    }

    // ── 加载页停一下就进欢迎页（真接线时等的是后端的就绪检查）─────────────
    Timer {
        interval: 1400
        running: root.page === "loading"
        onTriggered: root.replace("welcome")
    }

    // ── 页面 ──────────────────────────────────────────────────────────
    Loader {
        id: pageLoader
        anchors.fill: parent
        source: root.pageFiles[root.page] !== undefined ? root.pageFiles[root.page] : ""
        onLoaded: root.wire(root.page, item)
    }

    /// 当前页面的 item。给取图与烟测用（`tools/flow-check.py` 靠它发信号），
    /// 业务代码不要拿它绕开 `wire()` 去直接操作页面。
    readonly property alias currentPage: pageLoader.item

    /// 每一页的接线：注入它要的初始值 + 把它的信号接回流程。
    /// 一个页面一个分支，全都摆在这里 —— 别把翻页逻辑散进各页。
    function wire(name, item) {
        if (!item)
            return;

        if (name === "welcome") {
            item.installRequested.connect(function() {
                root.go("network");
            });
            item.customizeRequested.connect(function() {
                root.go("advanced");
            });

        } else if (name === "network") {
            // 演示：网络状态由流程给，点「连接」就当接通了
            item.wiredConnected = root.networkOnline;
            item.connectRequested.connect(function(ssid, password) {
                root.networkOnline = true;
                item.connectedSsid = ssid;
                item.wiredConnected = true;
            });
            item.continueRequested.connect(function() {
                root.go("disk");
            });
            item.backRequested.connect(root.back);

        } else if (name === "disk") {
            item.chosen.connect(function(device) {
                root.targetDisk = device;
                root.rememberDisk(item.candidates, device);
                root.go("partition");
            });
            item.backRequested.connect(root.back);

        } else if (name === "partition") {
            item.device = root.targetDisk;
            item.diskModel = root.diskModel;
            item.diskSize = root.diskSize;
            item.continueRequested.connect(function() {
                root.go("erase-confirm");
            });
            item.backRequested.connect(root.back);

        } else if (name === "erase-confirm") {
            item.device = root.targetDisk;
            item.confirmedRequested.connect(function(device) {
                root.go("account");
            });
            item.backRequested.connect(root.back);

        } else if (name === "account") {
            item.userName = root.userName;
            item.hostName = root.hostName;
            item.setRootPassword = root.setRootPassword;
            item.accountChosen.connect(function(user, host, password, setRoot) {
                root.userName = user;
                root.userPassword = password;
                root.setRootPassword = setRoot;
                root.go("install-details");
            });
            item.backRequested.connect(root.back);

        } else if (name === "install-details") {
            item.targetDisk = root.targetDisk;
            item.diskSummary = root.diskModel + " · " + root.diskSize;
            item.userName = root.userName;
            item.rootHasPassword = root.setRootPassword;
            item.localeName = root.localeName;
            item.keymap = root.keymap;
            item.timezone = root.timezone;
            item.hostName = root.hostName;
            item.installRequested.connect(function() {
                root.go("install");
            });
            item.backRequested.connect(root.back);

        } else if (name === "install") {
            item.logLines = [];
            root.startDemo();
            item.cancelRequested.connect(function() {
                demoTimer.stop();
                root.back();
            });
            item.retryRequested.connect(function() {
                root.startDemo();
            });

        } else if (name === "done") {
            item.rebootRequested.connect(function() {
                // ⚠️ 演示流程不真重启 —— 真接线时这里换成后端的 `systemctl reboot`。
                // 在开发机上点「立即重启」会把开发机重启，那是不可接受的。
                Qt.quit();
            });

        } else if (name === "advanced") {
            item.rows = root.advancedRows();
            item.rowChosen.connect(function(target) {
                root.go(target);
            });
            item.backRequested.connect(root.back);

        } else if (name === "language") {
            item.selectedLocale = root.localeName;
            item.chosen.connect(function(locale) {
                root.localeName = locale;
                root.back();
            });
            item.backRequested.connect(root.back);

        } else if (name === "keyboard") {
            item.selectedKeymap = root.keymap;
            item.chosen.connect(function(km) {
                root.keymap = km;
                root.back();
            });
            item.backRequested.connect(root.back);

        } else if (name === "timezone") {
            item.selectedZone = root.timezone;
            item.chosen.connect(function(zone) {
                root.timezone = zone;
                root.back();
            });
            item.backRequested.connect(root.back);

        } else if (name === "hostname") {
            item.hostname = root.hostName;
            item.hostnameChosen.connect(function(h) {
                root.hostName = h;
                root.back();
            });
            item.backRequested.connect(root.back);
        }
    }

    // ── 假安装：把「装包」这一段演出来（G3 不接后端）────────────────────
    //
    // 形状照抄后端真实会报的东西：阶段名取自 `events.PHASES`，
    // 命令行是 `Reporter.command()` 那一类，旁白是 `note()`。
    // **它不是进度条**：阶段之间的步长是编的，真接线后由事件流决定。
    readonly property var demoSteps: [
        {
            phase: "start",
            action: "正在准备安装环境",
            lines: [
                "    目标盘 " + root.targetDisk + "（" + root.diskModel + " · " + root.diskSize + "）",
                "    将要创建：系统分区 512 MiB (vfat) + 数据分区（剩余，ext4）"
            ]
        },
        {
            phase: "disk",
            action: "正在重新分区并创建文件系统",
            lines: [
                "$ wipefs -a " + root.targetDisk,
                "$ parted -s " + root.targetDisk + " mklabel gpt mkpart ESP fat32 1MiB 513MiB",
                "$ mkfs.vfat -F 32 -n MIPLINUX " + root.targetDisk + "1",
                "$ mkfs.ext4 -F -L MIPLINUX " + root.targetDisk + "2",
                "$ mount " + root.targetDisk + "2 /mnt"
            ]
        },
        {
            phase: "packages",
            action: "正在从镜像源下载并安装软件包",
            lines: [
                "$ pacman-key --gpgdir /mnt/etc/pacman.d/gnupg --init",
                "    目标包清单：…/data/target-packages.x86_64（8 个包）",
                "$ pacstrap -C /etc/pacman.conf -G -M /mnt base linux linux-firmware"
            ]
        },
        {
            phase: "packages",
            action: "正在从镜像源下载并安装软件包",
            lines: [
                "    ==> 正在从镜像源下载…",
                "    base-2026.09.20-1-any.pkg.tar.zst            100%   312 KiB",
                "    linux-6.16.7.arch1-1-x86_64.pkg.tar.zst      100%   148 MiB"
            ]
        },
        {
            phase: "packages",
            action: "正在从镜像源下载并安装软件包",
            lines: [
                "    (8/8) 正在安装 linux-firmware",
                "    ==> 正在生成 initramfs…"
            ]
        },
        {
            phase: "configure",
            action: "正在写入系统配置与账户",
            lines: [
                "$ genfstab -U /mnt >> /mnt/etc/fstab",
                "$ arch-chroot /mnt ln -sf /usr/share/zoneinfo/" + root.timezone + " /etc/localtime",
                "    已创建用户 " + root.userName + "（wheel 组，可 sudo）",
                root.setRootPassword ? "    root 已设密码" : "    root 保持锁定"
            ]
        },
        {
            phase: "boot",
            action: "正在安装引导",
            lines: [
                "$ bootctl --path=/mnt/boot install",
                "$ arch-chroot /mnt mkinitcpio -P"
            ]
        },
        {
            phase: "done",
            action: "安装完成",
            lines: [
                "    安装完成：" + root.targetDisk + " → " + root.userName
            ]
        }
    ]

    property int demoIndex: 0

    function startDemo() {
        var it = pageLoader.item;
        if (!it)
            return;
        root.demoIndex = 0;
        it.failed = false;
        it.elapsed = 0;
        it.phase = root.demoSteps[0].phase;
        it.currentAction = root.demoSteps[0].action;
        it.logLines = root.demoSteps[0].lines.slice();
        demoTimer.restart();
    }

    function demoTick() {
        var it = pageLoader.item;
        if (!it || root.page !== "install")
            return;
        if (root.demoIndex >= root.demoSteps.length - 1) {
            demoTimer.stop();
            finishTimer.restart();
            return;
        }
        root.demoIndex += 1;
        var step = root.demoSteps[root.demoIndex];
        it.phase = step.phase;
        it.currentAction = step.action;
        it.logLines = it.logLines.concat(step.lines);
        if (root.demoIndex >= root.demoSteps.length - 1) {
            demoTimer.stop();
            finishTimer.restart();
        }
    }

    Timer {
        id: demoTimer
        interval: 1300
        repeat: true
        onTriggered: root.demoTick()
    }

    //: 最后一条日志停一拍再进结束页 —— 让人看清「装完了」
    Timer {
        id: finishTimer
        interval: 900
        onTriggered: if (root.page === "install")
                         root.replace("done")
    }
}
