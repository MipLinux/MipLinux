"""后端事实 → 界面记录：**纯函数，不依赖 Qt**，所以能直接单测。

`DiskPage.qml` 的文件头把这条写成了铁律：**界面上每个字都必须能指出出处。**
这一层因此只做两件事：

* **翻译** —— 字节数变成「40.0 GiB」，`fs_type` 变成那句摘要里的一段；
* **取舍** —— 哪些盘可选、挂哪个颜色的胶囊。

它**不推断**。没有「像是启动盘」，没有「这是 Windows 盘」——
`ntfs` 只说 ntfs。后端担保不了的话，这里一个字都不写。

放在 bridge 而不是 backend，是因为输出的字段名与胶囊配色（`danger` / `warning`）
是**界面词汇**：后端不该知道界面上有「胶囊」这种东西。
"""

from __future__ import annotations

from pathlib import Path

from mipl_installer import disk, network, options, util

#: 未分配空间小于整盘的这一比例时，摘要里就不提它 —— 那是分区表对齐留的零头
#: （1 MiB），说成「未分配 1 MiB」只会占地方、让人以为还有什么没分完。
FREESPACE_NOISE = 0.005

#: 语言页的显示名。**这是纯装饰**，所以放在界面这一侧；认不出的就用 locale
#: 自己当名字（`fr_FR.UTF-8` 显示成 `fr_FR.UTF-8`），不编一个假名字。
LOCALE_NAMES = {
    "zh_CN.UTF-8": "简体中文",
    "zh_TW.UTF-8": "繁體中文（台灣）",
    "zh_HK.UTF-8": "繁體中文（香港）",
    "en_US.UTF-8": "English (US)",
    "en_GB.UTF-8": "English (UK)",
    "ja_JP.UTF-8": "日本語",
    "ko_KR.UTF-8": "한국어",
    "de_DE.UTF-8": "Deutsch",
    "fr_FR.UTF-8": "Français",
    "es_ES.UTF-8": "Español",
    "ru_RU.UTF-8": "Русский",
}


# ── 磁盘 ──────────────────────────────────────────────────────────────
def partition_label(partition: disk.Partition) -> str:
    """一段分区在摘要里叫什么。**按能确证的东西排优先级**：

    ESP 的 GPT 类型 GUID > 文件系统类型 > 「分区 N」（连文件系统都读不到）。
    """
    if partition.esp:
        return "EFI"
    if partition.fs_type:
        return partition.fs_type.upper()
    return f"分区 {partition.number}"


def summary_of(candidate: disk.Candidate) -> str:
    """盘上有什么，一句话。**只平铺事实**，不替谁下结论。"""
    if not candidate.partitions:
        return "整块未使用"

    parts = [
        f"{partition_label(p)} {util.human_size(p.size)}" for p in candidate.partitions
    ]
    used = sum(p.size for p in candidate.partitions)
    free = candidate.size - used
    if candidate.size and free / candidate.size > FREESPACE_NOISE:
        parts.append(f"未分配 {util.human_size(free)}")
    return " · ".join(parts)


def segments_of(candidate: disk.Candidate) -> list[dict]:
    """按容量比例画的条：`[{kind, share}]`。

    分区之间与盘尾的空白也要画出来，否则一条有分区的盘会被画成「满的」——
    那正是「还剩多少能装」的答案。
    """
    total = candidate.size
    if not total or not candidate.partitions:
        return [{"kind": "free", "share": 1.0}]

    segments: list[dict] = []
    cursor = 0

    def add(kind: str, size: int) -> None:
        share = size / total
        # 与摘要用**同一个**阈值：1 MiB 的对齐零头不该在条上留一根看不见的
        # 细丝，也不该在文字里占一句「未分配 1 MiB」。两处同源，所以两处一致。
        if share <= 0 or (kind == "free" and share < FREESPACE_NOISE):
            return
        segments.append({"kind": kind, "share": share})

    for partition in candidate.partitions:
        add("free", partition.start - cursor)
        add("efi" if partition.esp else "os", partition.size)
        cursor = max(cursor, partition.start + partition.size)
    add("free", total - cursor)
    return segments or [{"kind": "free", "share": 1.0}]


def badges_of(candidate: disk.Candidate) -> list[dict]:
    """状态胶囊。**优先级就是危险程度**：禁用的原因排在最前。

    `danger` = 不能选（正在使用 / 太小），`warning` = 能选但要当心
    （可移动设备 / 已有分区表）。颜色只是加强，文字才是事实（tech/07 §2.1）。
    """
    badges: list[dict] = []
    if candidate.in_use:
        badges.append({"t": "正在使用", "v": "danger"})
    if candidate.too_small:
        badges.append({"t": "太小", "v": "danger"})
    if candidate.removable:
        badges.append({"t": "可移动设备", "v": "warning"})
    if candidate.table_type:
        badges.append({"t": "已有分区表", "v": "warning"})
    return badges


def disk_record(candidate: disk.Candidate) -> dict:
    """一块候选盘 → `DiskPage.qml` 的候选记录（字段名就是那边的契约）。"""
    return {
        "path": candidate.path,
        "model": candidate.model or "（型号未报告）",
        "size": util.human_size(candidate.size),
        "summary": summary_of(candidate),
        "segments": segments_of(candidate),
        "selectable": candidate.usable,
        "badges": badges_of(candidate),
    }


def disk_records(candidates: list[disk.Candidate]) -> list[dict]:
    """候选表。**不再排序**：sysfs 出来的顺序（vda / sda / nvme…）就是稳定的，
    按容量或型号排只会让人找不到刚才看见的那块。"""
    return [disk_record(candidate) for candidate in candidates]


# ── 计划中的分区（选完盘之后那一页）──────────────────────────────────────
def planned_partitions(layout: disk.Layout) -> list[dict]:
    """`plan_layout` 算出来的布局 → `PartitionPage.qml` 的两条记录。

    `share` 是按容量的比例（只用来画条），`size` 才是给人看的字 ——
    两者都从**同一份 layout** 来，界面不自己算。
    """
    total = layout.total or 1
    return [
        {
            "kind": "system",
            "name": "系统分区",
            "size": util.human_size(layout.esp_size),
            "fs": "vfat",
            "share": layout.esp_size / total,
        },
        {
            "kind": "data",
            "name": "数据分区",
            "size": util.human_size(layout.root_size),
            "fs": "ext4",
            "share": layout.root_size / total,
        },
    ]


def layout_summary(layout: disk.Layout) -> str:
    """一行说清将要建什么（安装详情页的「分区」那一行）。"""
    return (
        f"系统分区 {util.human_size(layout.esp_size)} (vfat) + "
        f"数据分区 {util.human_size(layout.root_size)} (ext4)"
    )


# ── 网络 ──────────────────────────────────────────────────────────────
def network_record(state: dict) -> dict:
    """`network.state()` → NetworkPage 要的那几个属性。

    有线与无线分开说：有线给接口名与 IPv4，无线给 SSID。**通了才有内容**，
    没通就是空字符串 —— 界面那边「有线整块不出现」正是靠这个。
    """
    wired = state.get("wired", False)
    return {
        "online": state.get("online", False),
        "wiredConnected": wired,
        "wiredName": state.get("wired_interface", "") if wired else "",
        "wiredIPv4": state.get("wired_ipv4", "") if wired else "",
        "connectedSsid": state.get("wifi_ssid", ""),
    }


def wifi_records(networks: list[dict]) -> list[dict]:
    """无线网络记录 → `{ssid, signal, secured}`。

    **`signal` 是百分比**（nmcli 的 SIGNAL，0–100），不是 dBm —— 见 `network.py`
    的说明。界面按它挑图标与文案，不换算成另一套量纲。
    """
    return [
        {
            "ssid": item["ssid"],
            "signal": item["signal"],
            "secured": item["secured"],
        }
        for item in networks
    ]


# ── 就绪检查（加载页与欢迎页）──────────────────────────────────────────
def readiness(items: dict) -> list[dict]:
    """三行自检：网络 / 目标盘 / EFI 固件。

    形状与 `GalleryPage.qml` 里那份样张一致（`{label, state, value, fix?}`），
    因为 `ReadyCheck.qml` 就是按它写的。`fix` **只在没通过时出现** ——
    通过了还挂一条「怎么办」是噪音。
    """
    out: list[dict] = []

    network_ok = bool(items.get("network", {}).get("online"))
    wired = items.get("network", {}).get("wired")
    ssid = items.get("network", {}).get("wifi_ssid", "")
    out.append(
        {
            "label": "网络",
            "state": "ok" if network_ok else "fail",
            "value": ("已连接（有线）" if wired else f"已连接（{ssid}）") if network_ok else "未连接",
            **({} if network_ok else {"fix": "插上网线，或在网络页连一个无线网络 —— 装包阶段必须有网。"}),
        }
    )

    usable = items.get("usable_disks", 0)
    out.append(
        {
            "label": "目标盘",
            "state": "ok" if usable else "fail",
            "value": f"认到 {usable} 块",
            **({} if usable else {"fix": "接一块至少能装下系统的盘；被排除的盘在磁盘页里会写原因。"}),
        }
    )

    efi = bool(items.get("efi"))
    out.append(
        {
            "label": "EFI 固件",
            "state": "ok" if efi else "fail",
            "value": "已检测到" if efi else "未检测到",
            **(
                {}
                if efi
                else {"fix": "这台机器是 BIOS 引导。v0.1 只支持 UEFI —— 请在固件设置里改回 UEFI 模式。"}
            ),
        }
    )
    return out


def efi_booted() -> bool:
    """是不是 UEFI 引导起来的。判据是内核挂上来的 efivarfs。

    v0.1 只支持 UEFI（`boot.py` 写的是 systemd-boot），所以这一条要**在装之前**
    说清楚：装到一半才说「你其实是 BIOS」，盘已经擦了。
    """
    return Path("/sys/firmware/efi").is_dir()


# ── 高级安装的四份名单 ─────────────────────────────────────────────────
def zone_records(zones: list[str], root: str = options.ZONEINFO) -> list[dict]:
    """时区 → `{id, offset}`。`offset` 是**当前**偏移，见 `options.zone_offset`。"""
    return [{"id": zone, "offset": options.zone_offset(zone, root) or ""} for zone in zones]


def locale_records(locales: list[str]) -> list[dict]:
    """语言 → `{name, locale}`。认不出显示名的就用 locale 自己当名字。"""
    return [{"name": LOCALE_NAMES.get(locale, locale), "locale": locale} for locale in locales]


def keymap_records(keymaps: list[str]) -> list[str]:
    """键盘映射就是名字本身（`KeyboardPage` 的 model 是字符串列表）。"""
    return list(keymaps)
