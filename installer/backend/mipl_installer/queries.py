"""只读出口：把后端事实翻成 JSON，供界面（`--print-*`）与测试消费。

**为什么单独一个模块。** 界面需要的每一份数据都来自 `disk` / `network` / `options` /
`keymap_view`，但那些模块的返回值是 Python 对象（`Candidate`、`Path`、`dataclass`），
不是 JSON。翻译放在 `cli.py` 会让「参数翻译」和「数据翻译」混在一处；
放在各个功能模块里，等于让 `disk.py` 去操心「界面要什么字段名」。
所以收在这里一处：**这里是后端与界面之间唯一的字段名来源**。

## 两条纪律

1. **只吐事实。** 字节数就是字节数（顺带给一个 `size_label`，用的是 `util.human_size`，
   保住「人读的大小」只有一份实现），不吐「推荐」「危险」「胶囊」这类**界面词汇** ——
   它们要翻译成中英两套，属于渲染层。界面的翻译层是
   `installer/frontend/app/renderer/js/backend.js`。
2. **校验结果给码，不给句子。** 失败时返回 `reason`（`format` / `notInList` / `notFound`），
   界面拿它查自己的文案表；`message` 是给人与日志的中文，**界面不许直接显示它** ——
   英文模式会露馅。

## 出口的形态

每个函数返回一个可直接 `json.dumps` 的 dict，由 `cli.py` 的 `--print-*` 打印。
`--connect-wifi` 是唯一有副作用的（它真的会连网），其余全是只读、不需要 root。
"""

from __future__ import annotations

from . import disk, keymap_view, network, options, util
from .util import EXIT_USAGE, InstallerError, Runner


# ── 磁盘 ──────────────────────────────────────────────────────────────
def candidate_dict(candidate: disk.Candidate) -> dict:
    """一块候选盘。

    `model` 可能是空串（virtio-blk 的 sysfs 里没有 model，`disk.model_of()` 拒绝
    把 PCI 厂商号 `0x1af4` 当型号读出来）。空就是空 —— 界面显示「（型号未报告）」，
    那是**界面**的措辞，不是后端的。
    """
    return {
        "path": candidate.path,
        "model": candidate.model,
        "size": candidate.size,
        "size_label": util.human_size(candidate.size),
        "removable": candidate.removable,
        "in_use": candidate.in_use,
        "table_type": candidate.table_type,
        "too_small": candidate.too_small,
        "usable": candidate.usable,
        "partitions": [
            {
                "number": part.number,
                "start": part.start,
                "size": part.size,
                "fs_type": part.fs_type,
                "label": part.label,
                "esp": part.esp,
            }
            for part in candidate.partitions
        ],
    }


def disks(runner: Runner | None = None) -> dict:
    """候选盘。`runner` 给了才补文件系统信息（`blkid`，要 root）—— 不给就是纯 sysfs。"""
    return {"disks": [candidate_dict(item) for item in disk.list_candidates(runner=runner)]}


# ── 网络 ──────────────────────────────────────────────────────────────
def network_state(runner: Runner) -> dict:
    return network.state(runner)


def wifi(runner: Runner, *, rescan: bool = False) -> dict:
    return {"wifi": network.wifi_networks(runner, rescan=rescan)}


def connect_wifi(runner: Runner, ssid: str, password: str = "") -> dict:
    """连无线网。**这是唯一有副作用的出口**，失败也返回 200 形状的 dict：

    连接失败是**预期内**的结果（密码打错是最常见的一种），不是「安装器坏了」。
    用退出码表达它就等于让界面去分辨「哪个非零码是密码错」—— 所以这里一律
    `ok: false` + `reason`，退出码留给「参数根本不对」那种失败。
    """
    try:
        network.connect(runner, ssid, password)
    except InstallerError as exc:
        return {"ok": False, "reason": exc.reason or "other", "message": str(exc)}
    return {"ok": True, "reason": None, "message": ""}


# ── 高级安装的四份名单 ────────────────────────────────────────────────
def timezones() -> dict:
    """时区 + **当前**偏移。

    偏移逐条算，见 `options.zone_offset` 的说明（夏令时会变）。
    这里把它的 `UTC+08:00` 削成 `+08:00`：界面那句 `timezone.display` 已经是
    `%1（UTC%2）`，前缀由**文案**提供。留着前缀会渲染成「中国标准时间（UTCUTC+08:00）」
    —— 而那正是「同一件事有两个来源」的典型症状。削前缀发生在这里，不在界面里：
    界面对偏移做字符串手术，就等于它也开始理解偏移的格式了。
    """
    return {
        "timezones": [
            {"id": zone, "offset": (options.zone_offset(zone) or "").removeprefix("UTC")}
            for zone in options.timezones()
        ]
    }


def locales() -> dict:
    return {"locales": options.locales()}


def keymaps() -> dict:
    return {"keymaps": options.keymaps()}


def keymap(name: str) -> dict:
    """一份键位映射解析完的样子（Issue #65）。

    `lines` 是**原文逐字**，所以 `--print-keymap de` 的输出能直接跟
    `zcat /usr/share/kbd/keymaps/i386/qwertz/de.map.gz` 逐行对上 ——
    「解析没吃掉东西」这件事因此是可自证的，不用信实现。
    """
    return keymap_view.parse(name).as_dict()


# ── 校验（只回答合不合规，不改任何东西）────────────────────────────────
def _verdict(check, value: str) -> dict:
    try:
        check(value)
    except InstallerError as exc:
        return {"ok": False, "reason": exc.reason or "other", "message": str(exc)}
    return {"ok": True, "reason": None, "message": ""}


def check_hostname(hostname: str) -> dict:
    return _verdict(options.validate_hostname, hostname)


def check_locale(locale: str) -> dict:
    return _verdict(options.validate_locale, locale)


def check_keymap(keymap_name: str) -> dict:
    return _verdict(options.validate_keymap, keymap_name)


def check_timezone(zone: str) -> dict:
    return _verdict(options.validate_timezone, zone)


# ── 计划摘要（摘要页的「装成什么样」）─────────────────────────────────
def plan_summary(runner: Runner | None = None) -> dict:
    """摘要页要的两行「事实」：文件系统与引导器。

    包数与下载量**不在这里** —— 那要读包清单、真的去问仓库，属于 M4 的事；
    现在编一个数字摆上去，就是界面在描述它没做过的事（tech/09 的口径）。
    """
    return {
        "filesystem": "ext4",
        "boot": "systemd-boot",
        "esp": util.human_size(disk.ESP_SIZE),
        "pacman_conf": "/etc/pacman.conf",
    }


#: 出口名 → 实现。`cli.py` 的 `--print-*` 与测试都按这张表走，两处不会漂。
EXITS = {
    "disks": disks,
    "network": network_state,
    "wifi": wifi,
    "timezones": timezones,
    "locales": locales,
    "keymaps": keymaps,
    "plan": plan_summary,
}


def require_disk_argv(disk_path: str | None) -> str:
    """安装模式下 `--disk` 是必填的。

    `--disk` 在 argparse 里已经不是 `required=True` 了（只读出口不该逼人先指一块盘），
    所以这条判断挪到了这里 —— 报错时机与文案跟原来的 argparse 一致。
    """
    if not disk_path:
        raise InstallerError(
            "要装系统就得指出目标盘",
            EXIT_USAGE,
            hint="例如 --disk /dev/vda；只想看名单用 --print-disks 之类的只读出口",
        )
    return disk_path
