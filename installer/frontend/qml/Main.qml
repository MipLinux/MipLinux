// MipLinux 安装器 —— 流程壳。**整个程序只有这一个 Window。**
//
// 为什么只有一个窗口：cage 是单窗口 kiosk 合成器（一次只认一个顶层窗口），
// 「翻页」不能靠开关窗口。页面都是 `Loader` 换进换出的 Item ——
// `components/PageShell.qml` 的根从 Window 改成 Item 就是为了这件事。
//
// ── 真接线（2026-09-26）：界面只订阅事件，数据全部来自后端 ────────────────
// 两个 QML 侧的对象由 `mipl-installer` 挂进来（见该文件与 bridge/）：
//   · `Backend` —— 候选盘 / 分区预告 / 就绪检查 / 网络 / 四份名单 / 校验；
//   · `Install` —— 安装控制器（工作线程 + 事件信号）。
// 界面**不解析 nmcli、不读 sysfs、不拼 parted 命令、不自己写校验正则** ——
// 那是桥接层的事（frontend/README 的「唯一来源」，tech/07 §6 的四条缺口）。
//
// 取图与流程烟测（`tools/`）默认**不挂**这两个对象：那时页面用各自的默认值渲染
// （评审要的是可复现的图，不是「这台机器正好有几块盘」）。`tools/flow-check.py
// --backend` 会挂上，走的就与 Live 是同一条路。下面那段 `rehearsalSteps` 假安装
// 同理：只在**没有** `Install` 时用，真身永远轮不到它。
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
    // **必须全屏**（2026-09-26 实机反馈）：窗口只要是普通 toplevel，Qt 的 Wayland
    // 插件就会给它画一套客户端装饰（标题栏 + 关闭按钮）—— 而 cage 不是窗口管理器、
    // 没有服务端装饰可谈。于是安装器带着标题栏出现、还能被关掉，一关就掉回 tty。
    // 全屏窗口没有装饰，这才是 kiosk 该有的形态（M0 占位窗口当年也是 showFullScreen）。
    // 取图工具会把它掰回窗口模式再定尺寸，见 tools/shots.py。
    visibility: Window.FullScreen
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

    // ── 后端接线 ──────────────────────────────────────────────────────
    //: 有 `Backend` / `Install` 才是真身（Live 里永远有，见文件头）
    readonly property bool hasBackend: typeof Backend !== "undefined"
    readonly property bool hasInstall: typeof Install !== "undefined"

    //: 就绪检查的三行（网络 / 目标盘 / EFI）。空数组 = 还没探过。
    property var readyItems: []
    property bool probed: false
    property bool minShown: false
    //: 加载页那句话：探测发现有问题时，把问题说在这一屏上
    property string loadingMessage: "正在准备安装环境…"
    //: 选完盘之后算出来的分区预告（安装详情页要用同一份）
    property string partitionSummary: ""
    //: root 密码：界面上没有单独的字段，「勾了就与账户同密码」（tech/07 §4 P3）
    property string rootPassword: ""
    property bool installRunning: false

    /// 排练模式：让安装控制器只打印命令序列、一个字节都不动。
    ///
    /// **只有 `tools/wiring-check.py` 会挂 `MipRehearsal` 这个上下文属性**，
    /// Live 的入口（`mipl-installer`）不挂它 —— 所以真身永远是 `false`。
    /// 这是一个「只有测试能打开」的开关，不是界面上的一条路径：签名里那个
    /// 布尔位如果由界面决定，就等于把「假装装完了」做成了一个可点选项。
    readonly property bool rehearsalMode: typeof MipRehearsal !== "undefined" && MipRehearsal === true

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

    // ── 加载页：等**真的**探测结果，不是等一个固定秒数 ───────────────────
    //
    // 两件事同时满足才放行：
    //   · `probeTimer` 后台探完就绪检查 —— interval 0 让第一帧先画出去，
    //     所以 tech/07 §9.3 那条「先出 LOGO、后出字」的口径不变；
    //   · `minTimer` 保证 LOGO 至少露一下（一次淡入 480ms，别闪一下就没）。
    // 没有后端（取图 / 烟测）时探测立刻完成，所以那两条路的等待行为没变。
    Timer {
        id: probeTimer

        interval: 0
        running: root.page === "loading"
        onTriggered: root.probeReadiness()
    }

    Timer {
        id: minTimer

        interval: 700
        running: root.page === "loading"
        onTriggered: {
            root.minShown = true;
            root.leaveLoadingWhenReady();
        }
    }

    /// 就绪检查里没通过的那几项，一句话说完；全通过就是空串。
    function troubleSummary() {
        var bad = [];
        for (var i = 0; i < root.readyItems.length; i++) {
            var row = root.readyItems[i];
            if (row.state !== "ok")
                bad.push(row.label + "：" + row.value);
        }
        return bad.join(" · ");
    }

    /// 探一遍就绪检查。**问题说在加载页上** —— 那是用户看到的第一屏，
    /// 比等到磁盘页才发现「一块盘都没有」要早得多。
    function probeReadiness() {
        if (root.hasBackend)
            root.readyItems = Backend.readiness();
        root.probed = true;
        var trouble = root.troubleSummary();
        if (trouble !== "")
            root.loadingMessage = trouble;
        root.leaveLoadingWhenReady();
    }

    function leaveLoadingWhenReady() {
        if (root.page === "loading" && root.probed && root.minShown)
            root.replace("welcome");
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

        if (name === "loading") {
            // 加载页那句话跟着探测结果走（探测完成后再改 `loadingMessage`）
            item.message = Qt.binding(function() {
                return root.loadingMessage;
            });

        } else if (name === "welcome") {
            item.installRequested.connect(function() {
                root.go("network");
            });
            item.customizeRequested.connect(function() {
                root.go("advanced");
            });

        } else if (name === "network") {
            // 有后端就读真的；没有（取图 / 烟测）沿用流程里那个默认值
            if (root.hasBackend) {
                var net = Backend.network();
                root.networkOnline = net.online;
                item.wiredConnected = net.wiredConnected;
                item.wiredName = net.wiredName;
                item.wiredIPv4 = net.wiredIPv4;
                item.connectedSsid = net.connectedSsid;
                item.networks = Backend.wifiNetworks(false);
            } else {
                item.wiredConnected = root.networkOnline;
            }

            /// 刷新与「其它网络」都走这里：让 NetworkManager 重新扫一遍
            /// （要几秒，所以只在用户点的时候做，进页面那次读的是缓存）
            item.refreshRequested.connect(function() {
                if (!root.hasBackend)
                    return;
                item.networks = Backend.wifiNetworks(true);
                root.syncNetworkInto(item);
            });
            item.manualEntryRequested.connect(function() {
                if (!root.hasBackend)
                    return;
                item.networks = Backend.wifiNetworks(true);
                root.syncNetworkInto(item);
            });
            item.connectRequested.connect(function(ssid, password) {
                if (!root.hasBackend) {
                    root.networkOnline = true;
                    item.connectedSsid = ssid;
                    item.wiredConnected = true;
                    return;
                }
                var result = Backend.connectWifi(ssid, password);
                if (result.ok) {
                    item.connectError = "";
                    root.syncNetworkInto(item);
                } else {
                    // 失败说人话：后端的原文 + 它给的下一步（不复用「缺密码」那句）
                    item.connectError = result.hint === "" ? result.message
                                                           : result.message + " → " + result.hint;
                }
            });
            item.continueRequested.connect(function() {
                root.go("disk");
            });
            item.backRequested.connect(root.back);

        } else if (name === "disk") {
            // 候选盘**全部**来自后端（sysfs + blkid），前端不编也不推导
            if (root.hasBackend)
                item.candidates = Backend.candidates();
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
            if (root.hasBackend) {
                // 布局用后端 `disk.plan_layout` 算 —— 与真正动手时同一个函数
                var plan = Backend.partitionPlan(root.targetDisk);
                if (plan.partitions !== undefined)
                    item.partitions = plan.partitions;
                root.partitionSummary = plan.summary !== undefined ? plan.summary : "";
            }
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
                // 「设 root 密码」在界面上就是「与账户同密码」（tech/07 §4 P3）：
                // 没有第二个输入框，也就不该编出第二个密码
                root.rootPassword = setRoot ? password : "";
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
            // 分区预告是分区页算出来的那一份，这里只是把同一份显示第二遍
            if (root.partitionSummary !== "")
                item.partitionSummary = root.partitionSummary;
            item.installRequested.connect(function() {
                root.go("install");
            });
            item.backRequested.connect(root.back);

        } else if (name === "install") {
            // 信号在 Component.onCompleted 里只接一次（见那段注释）；这里只负责
            // 把这一页摆回初始态，然后**真开跑**或者（没有控制器时）演一遍。
            item.logLines = [];
            item.failed = false;
            item.failureMessage = "";
            item.failureHint = "";
            item.elapsed = 0;
            if (root.hasInstall) {
                root.startInstall();
            } else {
                root.startRehearsal();
            }
            item.cancelRequested.connect(function() {
                if (root.hasInstall) {
                    // 真身的取消**不跳页**：要等后端那一步收尾（卸载目标），
                    // 然后由 `failed` 信号把现场显示出来
                    Install.cancel();
                    return;
                }
                rehearsalTimer.stop();
                root.back();
            });
            item.retryRequested.connect(function() {
                if (root.hasInstall)
                    root.startInstall();
                else
                    root.startRehearsal();
            });

        } else if (name === "done") {
            item.rebootRequested.connect(function() {
                // 真重启（实机反馈：原来只 Qt.quit()，等于把安装器杀掉掉回 tty）。
                // QML 不自己动手 —— 交给 `Backend`（最终落到 bridge/actions.py）。
                if (typeof Backend !== "undefined")
                    Backend.reboot();
            });

        } else if (name === "advanced") {
            item.rows = root.advancedRows();
            item.rowChosen.connect(function(target) {
                root.go(target);
            });
            item.backRequested.connect(root.back);

        } else if (name === "language") {
            // 名单来自运行系统的 `/usr/share/i18n/SUPPORTED`（502 条），
            // 前端不写死一份 —— 那是 Issue #63 的翻版
            if (root.hasBackend)
                item.languages = Backend.locales();
            item.selectedLocale = root.localeName;
            item.chosen.connect(function(locale) {
                root.localeName = locale;
                root.back();
            });
            item.backRequested.connect(root.back);

        } else if (name === "keyboard") {
            // 名单来自 `/usr/share/kbd/keymaps/**/*.map.gz`（252 条）
            if (root.hasBackend)
                item.keymaps = Backend.keymaps();
            item.selectedKeymap = root.keymap;
            item.chosen.connect(function(km) {
                root.keymap = km;
                root.back();
            });
            item.backRequested.connect(root.back);

        } else if (name === "timezone") {
            // 名单来自 `zone1970.tab`，偏移是**当前**偏移（后端算的，夏令时会变）
            if (root.hasBackend)
                item.zones = Backend.timezones();
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

    // ── 排练：只在**没有** `Install` 时用（取图与流程烟测）────────────────
    //
    // Live 里 `mipl-installer` 一定挂了 `Install`，所以这一段永远轮不到 —— 它
    // 不是「备用实现」，是给 `tools/shots.py` / `tools/flow-check.py` 用的离线
    // 素材（评审要的图必须可复现，不能取决于这台机器装到第几步）。
    //
    // 形状照抄后端真实会报的东西：阶段名取自 `events.PHASES`，命令行是
    // `Reporter.command()` 那一类，旁白是 `note()` —— 免得看图上像、真跑起来不像。
    readonly property var rehearsalSteps: [
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

    property int rehearsalIndex: 0

    function startRehearsal() {
        var it = pageLoader.item;
        if (!it)
            return;
        root.rehearsalIndex = 0;
        it.failed = false;
        it.elapsed = 0;
        it.phase = root.rehearsalSteps[0].phase;
        it.currentAction = root.rehearsalSteps[0].action;
        it.logLines = root.rehearsalSteps[0].lines.slice();
        rehearsalTimer.restart();
    }

    function rehearsalTick() {
        var it = pageLoader.item;
        if (!it || root.page !== "install")
            return;
        if (root.rehearsalIndex >= root.rehearsalSteps.length - 1) {
            rehearsalTimer.stop();
            finishTimer.restart();
            return;
        }
        root.rehearsalIndex += 1;
        var step = root.rehearsalSteps[root.rehearsalIndex];
        it.phase = step.phase;
        it.currentAction = step.action;
        it.logLines = it.logLines.concat(step.lines);
        if (root.rehearsalIndex >= root.rehearsalSteps.length - 1) {
            rehearsalTimer.stop();
            finishTimer.restart();
        }
    }

    Timer {
        id: rehearsalTimer

        interval: 1300
        repeat: true
        onTriggered: root.rehearsalTick()
    }

    //: 最后一条日志停一拍再进结束页 —— 让人看清「装完了」
    Timer {
        id: finishTimer

        interval: 900
        onTriggered: if (root.page === "install")
                         root.replace("done")
    }

    // ── 安装控制器：信号**只接一次** ──────────────────────────────────────
    //
    // 不能写在 `wire("install")` 里：用户来回翻页会重复接上同一个信号，
    // 于是日志一行变两行、三行 —— 而且看起来像后端报了重复事件，极难查。
    // `Install` 是长生命周期的对象，界面只是它的一个订阅者。
    Component.onCompleted: {
        if (!root.hasInstall)
            return;
        Install.phaseChanged.connect(root.onInstallPhase);
        Install.logged.connect(root.onInstallLog);
        Install.failed.connect(root.onInstallFailed);
        Install.succeeded.connect(root.onInstallSucceeded);
        Install.runningChanged.connect(root.onInstallRunning);
    }

    /// 安装页当前的 item；不在安装页就返回 null（事件可能在任何时刻到达）
    function installPage() {
        return root.page === "install" ? pageLoader.item : null;
    }

    function onInstallPhase(phase, action) {
        var it = root.installPage();
        if (it) {
            it.phase = phase;
            it.currentAction = action;
        }
    }

    function onInstallLog(line) {
        var it = root.installPage();
        if (it)
            it.logLines = it.logLines.concat([line]);
    }

    function onInstallFailed(message, hint) {
        var it = root.installPage();
        if (it) {
            it.failed = true;
            it.failureMessage = message;
            it.failureHint = hint;
        }
    }

    function onInstallSucceeded() {
        if (root.page === "install")
            root.replace("done");
    }

    function onInstallRunning(running) {
        root.installRunning = running;
    }

    /// 把流程的状态交给后端。**这里是唯一拼 `request` 的地方** —— 之前是 CLI 拼
    /// argv，现在两边都从同一份「意图」走（`pipeline.Plan`）。
    function startInstall() {
        var it = pageLoader.item;
        if (it) {
            it.logLines = [];
            it.failed = false;
            it.failureMessage = "";
            it.failureHint = "";
            it.elapsed = 0;
            it.phase = "start";
            it.currentAction = "正在准备安装环境";
        }
        Install.start({
            "disk": root.targetDisk,
            "hostname": root.hostName,
            "user": root.userName,
            "locale": root.localeName,
            "timezone": root.timezone,
            "keymap": root.keymap,
            "password": root.userPassword,
            "rootPassword": root.rootPassword,
            "confirmedDevice": root.targetDisk
        }, root.rehearsalMode);
    }

    /// 把后端当前的网络状况同步进网络页（连接成功、刷新之后都要做一遍）
    function syncNetworkInto(item) {
        if (!root.hasBackend || !item)
            return;
        var now = Backend.network();
        root.networkOnline = now.online;
        item.wiredConnected = now.wiredConnected;
        item.wiredName = now.wiredName;
        item.wiredIPv4 = now.wiredIPv4;
        item.connectedSsid = now.connectedSsid;
    }
}
