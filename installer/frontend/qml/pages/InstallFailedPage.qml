// P4 的失败态 —— 只是为了能单独取图/评审而存在的一层薄包装。
//
// 失败长什么样是设计的一部分：「失败模式清单」里每一条都要有对应的兜底
// （installer-roadmap §6），而界面上那一条就得说清楚「哪里停下、接下来怎么办」。
// 与其在 InstallPage 里塞一个 __demo 开关污染真实组件，不如在这里摆好状态。

import QtQuick
import "../components"
import "."          // InstallPage.qml 就在同目录 —— 没有 qmldir，所以按目录导入

InstallPage {
    phase: "packages"
    currentAction: "装包阶段失败（退出码 4）"
    failed: true
    elapsed: 137
    showLog: true

    failureMessage: "命令失败（退出码 1）：pacstrap -C /etc/pacman.conf -G -M /mnt base  …"
    failureHint: "多半是网络断了或镜像源不可达。联网后点「重试」即可 —— "
               + "安装器会从擦盘重新来过，不会在半成品上继续。"

    logLines: [
        "$ wipefs -a /dev/vda",
        "$ mkfs.ext4 -F -L MIPLINUX /dev/vda2",
        "$ pacman-key --gpgdir /mnt/etc/pacman.d/gnupg --init",
        "$ pacstrap -C /etc/pacman.conf -G -M /mnt base linux linux-firmware",
        "    ==> 正在从镜像源下载…",
        "    error: failed retrieving file 'base-2026.09.20-1-any.pkg.tar.zst' from mirror.example.cn : Could not resolve host",
        "    error: failed to commit transaction (unreachable mirror)",
        "$ pacman -Sy 仍可用来单独排查",
        "    失败收尾：卸载目标",
        "    盘上可能留有半成品：重试会从擦盘重新来过"
    ]
}
