"""chroot 配置：fstab / 源 / locale / 时区 / 用户 / keyring / initramfs。

这里的原则是「**能写成文件的就写成文件，必须进 chroot 的才进 chroot**」：
前者单测能逐字断言，后者只有 Live 里能验。所以纯函数都在本模块顶部，
`configure_system()` 只负责按顺序调它们。

几处不显眼但会决定成败的地方：

* **`/etc/sudoers` 里 `%wheel` 默认是注释掉的**（sudo 包自带的那份）。
  不写 `/etc/sudoers.d/10-wheel`，建出来的用户就「在 wheel 组里但没有 sudo」，
  而且现场表现成「密码错了」。
* **fstab 按 UUID 写**：分区号会随盘变，UUID 不会。
* **ESP 挂 `/boot`**（见 disk.py），所以 fstab 里要有第二条。
* **vconsole 不抄 Live 的字体**：Live 用 `ter-132n`，而目标清单里没有
  `terminus-font`，抄过去就是「开机前几行报缺字体」。M1 只写 KEYMAP。
* **默认镜像源来自构建时保存的 profile 基线**，Live 的临时测速结果只服务 Live。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import options
from .events import step_event
from .util import (
    DEFAULT_TARGET,
    EXIT_CONFIGURE,
    InstallerError,
    Runner,
    chroot_argv,
    ensure_dir,
    read_text,
    write_text,
)

#: 构建脚本从 profile 生成，运行中的 Live 换源不会写这里。
PACMAN_BASELINE = Path(__file__).parent / "data/pacman-baseline"

#: `Include = /etc/pacman.d/mirrorlist` —— 只认未注释的整行
INCLUDE_RE = re.compile(r"^\s*Include\s*=\s*(\S+)\s*$")

FSTAB_HEADER = """\
# /etc/fstab: static file system information.
#
# 由 mipl-installer 按 UUID 生成 —— 分区号会随盘而变，UUID 不会。
# 两行的顺序与挂载点（ESP 在 /boot）配合 systemd-boot：内核与 initramfs
# 必须落在 ESP 上，它才找得到。
#
# <file system> <dir>   <type> <options>                          <dump> <pass>
"""

#: ESP 的挂载选项：root 可读写，其他用户不可见（Arch 的默认口径）
ESP_OPTIONS = "rw,relatime,fmask=0137,dmask=0027"
ROOT_OPTIONS = "rw,relatime"


@dataclass(frozen=True)
class TargetConfig:
    """装后系统的一份「要长成什么样」。

    默认值都按中文用户与国内环境给（D10 / D11），命令行可以逐项覆盖。
    """

    target: str = DEFAULT_TARGET
    hostname: str = "mipl"
    user: str = "mipl"
    locale: str = "zh_CN.UTF-8"
    timezone: str = "Asia/Shanghai"
    #: 控制台键盘映射（`/etc/vconsole.conf` 的 `KEYMAP`）。**以前写死 `us`** ——
    #: 界面里那个键盘页因此是个摆设（Issue #64）。现在它是真参数。
    keymap: str = "us"
    #: 默认路径使用随安装器打包的基线；自定义路径按调用者提供的输入读取。
    pacman_conf: str = "/etc/pacman.conf"
    mirrorlist: str = "/etc/pacman.d/mirrorlist"
    #: 中文字体 fallback 的出厂设置（Live 的 /etc/fonts/local.conf）
    fonts_conf: str = "/etc/fonts/local.conf"
    #: 语言生成用（locale.gen 里放开的行）
    locales: tuple[str, ...] = field(default=("zh_CN.UTF-8", "en_US.UTF-8"))


# ── 纯函数：生成内容 ──────────────────────────────────────────────────
def iter_includes(pacman_conf_text: str) -> list[str]:
    """取出 conf 里所有**未注释**的 `Include` 目标。

    Live 的 `airootfs/etc/pacman.conf` 用 `Include = /etc/pacman.d/mirrorlist`
    指向国内源，所以这些文件必须一起进目标系统 —— 少一个，装后系统第一次
    `pacman -Syu` 就找不到仓库（检查点 6）。
    """
    return [m.group(1) for line in pacman_conf_text.splitlines() if (m := INCLUDE_RE.match(line))]


#: 仓库段里「不校验签名」的 SigLevel 行（`Optional` / `TrustAll`）。`\b` 保证
#: 不误伤 `Required DatabaseOptional`（全局那行）与 `LocalFileSigLevel = Optional`
#: （本地包的策略，键名不同，本来就匹配不到）。
OPTIONAL_TRUST_RE = re.compile(r"^\s*SigLevel\s*=\s*.*\b(?:Optional|TrustAll)\b")


def target_pacman_conf(pacman_conf_text: str) -> str:
    """Live conf → 装后系统的 conf：**去掉 Optional Trust**（issue #135）。

    Live 出厂设置里 `[archlinuxcn]` 写 `SigLevel = Optional TrustAll`（不校验签名）——
    内部构建无所谓，装后系统不行（P11 候选 A）：这种行整行去掉，该段就继承
    `[options]` 的全局 `SigLevel = Required DatabaseOptional`，装后系统对
    `[archlinuxcn]` 的每次 pacman 操作都验包签名。验签所需的 key 由
    `run_in_chroot()` 里对 `archlinuxcn` 的 populate 导入目标密钥环。
    """
    lines = [
        line for line in pacman_conf_text.splitlines()
        if not OPTIONAL_TRUST_RE.match(line)
    ]
    return "\n".join(lines) + "\n"


def fstab_lines(root_uuid: str, esp_uuid: str) -> list[str]:
    return [
        FSTAB_HEADER.rstrip("\n"),
        f"UUID={root_uuid}\t/\t\text4\t{ROOT_OPTIONS}\t0 1",
        f"UUID={esp_uuid}\t/boot\t\tvfat\t{ESP_OPTIONS}\t0 2",
    ]


def fstab_text(root_uuid: str, esp_uuid: str) -> str:
    return "\n".join(fstab_lines(root_uuid, esp_uuid)) + "\n"


def locale_conf(locale: str) -> str:
    # 与 Live 出厂（profile/airootfs/etc/locale.conf）保持同一份真相：LANG + LANGUAGE。
    # LANGUAGE 是 gettext 的回退链 —— 程序没有中文翻译时退回英文而不是留空。
    # 只有 zh_CN 才有这条链；其它 locale 不硬塞（一致性指「同一份出厂设置」，不是照抄值）。
    lines = [f"LANG={locale}"]
    if locale.startswith("zh_CN"):
        lines.append("LANGUAGE=zh_CN:zh:en_US:en")
    return "\n".join(lines) + "\n"


def environment_text() -> str:
    # 只写进目标系统：Live 安装器不装输入法；装后系统需要这三个变量，
    # GTK / Qt 程序才会选用已安装的 fcitx5 输入法模块。
    return "GTK_IM_MODULE=fcitx\nQT_IM_MODULE=fcitx\nXMODIFIERS=@im=fcitx\n"


def vconsole_conf(keymap: str = "us") -> str:
    # 只有 KEYMAP：字体留给 M3（要么带 terminus-font，要么换 CJK 字体方案），
    # 现在写一个包里没有的字体名，开机前几行就是报错。
    # KEYMAP 是参数（Issue #64）：以前写死 us，界面上的键盘页选什么都不生效。
    return f"KEYMAP={keymap}\n"


def locales_to_enable(cfg: TargetConfig) -> tuple[str, ...]:
    """要在目标 `locale.gen` 里放开的行：**选中的那个 locale 必须在里面**。

    以前这里只放开 `cfg.locales`（默认恰好是 zh_CN / en_US 两行），于是「语言」页
    选了第三种 locale 时，`LANG` 指向一个从没生成过的 locale —— 装出来的系统
    每个程序都报 `setlocale` 警告（Issue #63）。`en_US.UTF-8` 始终带上：它是
    gettext 的回退链末端，缺了它英文回退也没有。
    """
    wanted = [cfg.locale, *cfg.locales, "en_US.UTF-8"]
    seen: list[str] = []
    for locale in wanted:
        if locale and locale not in seen:
            seen.append(locale)
    return tuple(seen)


def has_locale(locale_gen_text: str, locale: str) -> bool:
    """`locale.gen` 里有没有可放开的那一行（注释或未注释都算）。

    带字符集比较（表里写的是 `zh_CN.UTF-8 UTF-8`），所以按整名匹配 ——
    `zh_CN.UTF-8` 与 `zh_CN.GB18030` 是两行，不能只看前半个名字。
    """
    for line in locale_gen_text.splitlines():
        body = line.strip().lstrip("#").strip()
        if body and body.split()[0] == locale:
            return True
    return False


def enable_locales(locale_gen_text: str, locales: tuple[str, ...]) -> str:
    """把 `/etc/locale.gen` 里指定的行放开（其余原样）。

    locale.gen 里的写法是 `zh_CN.UTF-8 UTF-8`，带字符集，所以直接按整名比。
    """
    wanted = {loc for loc in locales}
    out: list[str] = []
    for line in locale_gen_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            parts = body.split()
            if parts and parts[0] in wanted:
                out.append(body)
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def hosts(hostname: str) -> str:
    return (
        "127.0.0.1\tlocalhost\n"
        "::1\t\tlocalhost\n"
        f"127.0.1.1\t{hostname}.localdomain\t{hostname}\n"
    )


def sudoers_dropin() -> str:
    # sudo 包自带的 /etc/sudoers 里 %wheel 那行是注释掉的 —— 这条 drop-in 才让
    # 「在 wheel 组里」真的等于「能 sudo」。
    return "%wheel ALL=(ALL:ALL) ALL\n"


def validate_user(user: str) -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        raise InstallerError(
            f"用户名不合法：{user!r}",
            EXIT_CONFIGURE,
            hint="小写字母开头，后跟小写字母/数字/下划线/连字符（useradd 的规则）",
        )


# ── 落到目标系统 ──────────────────────────────────────────────────────
def copy_pacman_config(runner: Runner, cfg: TargetConfig) -> None:
    """默认从 ISO 内独立基线写入目标；显式自定义 conf 使用调用者的文件。

    基线缺失时硬失败，不回退到 Live 临时状态。目标配置仍按 #135 收紧验签。
    """
    baseline = PACMAN_BASELINE if cfg.pacman_conf == "/etc/pacman.conf" else None

    def source_path(path: str) -> Path:
        return baseline / path.lstrip("/") if baseline is not None else Path(path)

    conf_path = source_path(cfg.pacman_conf)
    if not conf_path.is_file() and runner.dry_run and baseline is not None:
        runner.reporter.note(f"[dry-run] ISO 构建时将生成 pacman 基线：{baseline}；未验证内容")
        return
    if not conf_path.is_file():
        raise InstallerError(
            f"找不到 pacman 配置：{cfg.pacman_conf}",
            EXIT_CONFIGURE,
            hint=f"配置来源：{conf_path}；默认安装需要 ISO 打包的 pacman 基线",
        )
    text = target_pacman_conf(read_text(str(conf_path)))
    includes = iter_includes(text)

    write_text(runner, f"{cfg.target}/etc/pacman.conf", text)

    if not includes:
        # conf 里没有 Include（构建期那份 profile/pacman.conf 就是这种写法），
        # 那就至少把 mirrorlist 写进去。
        if not source_path(cfg.mirrorlist).is_file():
            raise InstallerError(
                f"找不到 mirrorlist：{cfg.mirrorlist}",
                EXIT_CONFIGURE,
                hint="装后系统要靠它找仓库（检查点 6），不能没有",
            )
        write_text(runner, f"{cfg.target}/etc/pacman.d/mirrorlist", read_text(str(source_path(cfg.mirrorlist))))
        return

    for include in includes:
        source = source_path(include) if Path(include).is_absolute() else conf_path.parent / include
        if not source.is_file():
            raise InstallerError(
                f"pacman.conf 里 Include 的文件不存在：{include}",
                EXIT_CONFIGURE,
                hint=f"配置来源中找不到 {source}，装后系统缺少该文件将无法升级",
            )
        write_text(runner, f"{cfg.target}{include}", read_text(str(source)))


def copy_mirror_switch(runner: Runner, cfg: TargetConfig) -> None:
    """安装受控的网络事件入口；reflector 自带定时任务仍由守卫禁用。"""
    data = Path(__file__).parent / "data/network"
    for name, destination in (
        ("mipl-mirror-switch", "/usr/local/bin/mipl-mirror-switch"),
        ("mipl-mirror-watch", "/usr/local/bin/mipl-mirror-watch"),
        ("mipl-mirror-watch.service", "/etc/systemd/system/mipl-mirror-watch.service"),
        ("90-mipl-mirror-switch", "/etc/NetworkManager/dispatcher.d/90-mipl-mirror-switch"),
    ):
        source = data / name
        if runner.dry_run and not source.is_file():
            runner.reporter.note(f"[dry-run] ISO 构建时将打包网络换源文件：{source}")
            continue
        if not source.is_file():
            raise InstallerError(f"缺少网络换源文件：{source}", EXIT_CONFIGURE)
        write_text(runner, cfg.target + destination, read_text(str(source)),
                   mode=0o644 if destination.endswith(".service") else 0o755)


def copy_fonts_conf(runner: Runner, cfg: TargetConfig) -> None:
    """把运行系统（Live）的字体 fallback 配置复制进目标。

    与 pacman.conf / mirrorlist 同一个哲学：出厂设置在 Live（airootfs），安装器
    不复制第二份字符串 —— 中文 fallback 只该有一份真相。字体包由装后系统清单提供。
    """
    source = Path(cfg.fonts_conf)
    if not source.is_file():
        if runner.dry_run:
            # 宿主排练机上没有这份 Live 出厂设置 —— dry-run 只预览命令序列，
            # 照 write_static_files 对 locale.gen 的同一口径：容忍并说出来。
            runner.reporter.note(
                f"dry-run：找不到字体配置 {cfg.fonts_conf}（Live 的出厂设置）—— 跳过复制预览"
            )
            return
        raise InstallerError(
            f"找不到字体配置：{cfg.fonts_conf}",
            EXIT_CONFIGURE,
            hint="默认读运行系统的 /etc/fonts/local.conf —— 这个安装器要在 Live 里跑",
        )
    ensure_dir(runner, f"{cfg.target}/etc/fonts")
    write_text(runner, f"{cfg.target}/etc/fonts/local.conf", read_text(str(source)))


def write_static_files(runner: Runner, cfg: TargetConfig, root_uuid: str, esp_uuid: str) -> None:
    # **先校验，再落盘。** 这一组守卫拦的是「装出来一个时间不对 / 键盘不对 /
    # 主机名不合法的系统」—— 那些问题都要等到重启之后才暴露，而重启之后
    # 用户在目标系统里，安装器的报错已经不在屏幕上了。
    options.validate_hostname(cfg.hostname)
    options.validate_timezone(cfg.timezone)
    options.validate_keymap(cfg.keymap)

    write_text(runner, f"{cfg.target}/etc/fstab", fstab_text(root_uuid, esp_uuid))
    write_text(runner, f"{cfg.target}/etc/locale.conf", locale_conf(cfg.locale))
    write_text(runner, f"{cfg.target}/etc/environment", environment_text())
    write_text(runner, f"{cfg.target}/etc/vconsole.conf", vconsole_conf(cfg.keymap))
    write_text(runner, f"{cfg.target}/etc/hostname", cfg.hostname + "\n")
    write_text(runner, f"{cfg.target}/etc/hosts", hosts(cfg.hostname))
    write_text(runner, f"{cfg.target}/etc/sudoers.d/10-wheel", sudoers_dropin(), mode=0o440)

    locale_gen = Path(f"{cfg.target}/etc/locale.gen")
    if locale_gen.is_file():
        text = read_text(str(locale_gen))
        if not has_locale(text, cfg.locale):
            raise InstallerError(
                f"目标系统的 locale.gen 里没有 {cfg.locale}",
                EXIT_CONFIGURE,
                hint="换一个 locale（名单见安装器的语言页），或确认目标清单里装上了 glibc",
            )
        write_text(runner, str(locale_gen), enable_locales(text, locales_to_enable(cfg)))
    elif not runner.dry_run:
        raise InstallerError(
            f"目标系统里没有 {locale_gen}（glibc 没装上？）",
            EXIT_CONFIGURE,
            hint="pacstrap 装完后再跑 configure；清单里要有 base",
        )

    # 时区用符号链接，不用复制文件：/usr/share/zoneinfo 是 tzdata 提供的，
    # 复制一份出来就成了第二份会漂移的真相。
    tz_target = f"{cfg.target}/etc/localtime"
    ensure_dir(runner, f"{cfg.target}/etc")
    runner.run(["ln", "-sf", f"/usr/share/zoneinfo/{cfg.timezone}", tz_target], exit_code=EXIT_CONFIGURE)


def verify_password(runner: Runner, cfg: TargetConfig, user: str) -> str:
    """确认某个账号的密码**真的**设上了，并返回 `passwd -S` 的状态行。

    为什么要断言：`chpasswd` 读到空输入时会**什么都不做却退出 0** —— 装完一路绿灯，
    重启之后谁也登不进去。这类失败必须在安装阶段就炸出来（M1 的验收判据是
    「装出来的系统能启动」，而一个登不进去的系统，等于没装上）。
    """
    if runner.dry_run:
        return "dry-run"
    out = (runner.run(chroot_argv(cfg.target, ["passwd", "-S", user]),
                      capture=True, exit_code=EXIT_CONFIGURE) or "").strip()
    fields = out.split()
    if len(fields) < 2 or fields[0] != user:
        raise InstallerError(
            f"读不出 {user} 的密码状态：{out or '（没有输出）'}",
            EXIT_CONFIGURE,
            hint="`passwd -S <用户>` 的输出形如 `mipl P 2026-09-22 0 99999 7 -1`",
        )
    state = fields[1]
    if state != "P":
        raise InstallerError(
            f"{user} 的密码没设上：passwd -S 说 {state}"
            "（P = 可用密码，L = 账号被锁，NP = 没有密码）",
            EXIT_CONFIGURE,
            hint=f"看目标盘 /etc/shadow 里 {user} 那一行的第二个字段：空或 `!` 就是没写进去",
        )
    return out


def reflector_guard(has_reflector: bool) -> list[str]:
    """禁用 reflector 自带定时入口；测速由网络与代理事件触发。"""
    if not has_reflector:
        return []
    return ["systemctl", "disable", "reflector.timer", "reflector.service"]


def target_has_reflector(target: str) -> bool:
    return Path(f"{target}/usr/lib/systemd/system/reflector.timer").is_file()


#: archlinuxcn-keyring 包提供的钥匙串文件：populate 之前必须先有它（pacstrap 装的）
ARCHLINUXCN_KEYRING = "usr/share/pacman/keyrings/archlinuxcn.gpg"


def require_archlinuxcn_keyring(runner: Runner, cfg: TargetConfig) -> None:
    """目标里的 `archlinuxcn` 钥匙串必须在 populate 之前存在。

    装后系统的 conf 已收紧（#135），`pacman-key --populate archlinuxcn` 依赖
    pacstrap 装进去的 `archlinuxcn-keyring` 包 —— 缺了就硬失败，不能静默跳到
    装后系统第一次 `pacman -Syu` 才报「签名无法校验」。
    """
    keyring = Path(cfg.target) / ARCHLINUXCN_KEYRING
    if runner.dry_run:
        # dry-run 只在没动过的盘上预览命令序列，目标里自然没有这个文件
        return
    if not keyring.is_file():
        raise InstallerError(
            f"目标系统里没有 {keyring}（archlinuxcn-keyring 没装上）",
            EXIT_CONFIGURE,
            hint="装后包清单里要有 archlinuxcn-keyring；pacstrap 装完后再跑 configure",
        )


def run_in_chroot(runner: Runner, cfg: TargetConfig, password: str,
                  root_password: str | None = None) -> None:
    """必须在目标系统里跑的几条。顺序有讲究，别调换。

    `root_password=None` 表示**保持 root 锁定**（只用 sudo 提权）—— 这是默认，
    但安装器会把这件事**说出来**：一个登不进去的 root 不该让人自己发现。
    """
    target = cfg.target
    validate_user(cfg.user)

    # 1. 用户与密码：密码走 stdin，**不进 argv**（argv 会留在进程列表与日志里）
    runner.reporter.emit(step_event("configure", "user", f"创建用户 {cfg.user}"))
    runner.run(chroot_argv(target, ["useradd", "-m", "-G", "wheel", "-s", "/bin/bash", cfg.user]),
               exit_code=EXIT_CONFIGURE)
    runner.reporter.emit(step_event("configure", "user-password", "设置用户密码"))
    runner.run(chroot_argv(target, ["chpasswd"]), input=f"{cfg.user}:{password}\n", exit_code=EXIT_CONFIGURE)
    verify_password(runner, cfg, cfg.user)

    # 2. root：设了就验，没设就明说 —— 不许静默留一个登不进去的 root
    runner.reporter.emit(step_event("configure", "root-password", "root 密码"))
    if root_password is not None:
        runner.run(chroot_argv(target, ["chpasswd"]), input=f"root:{root_password}\n", exit_code=EXIT_CONFIGURE)
        verify_password(runner, cfg, "root")
        runner.reporter.note("root 密码已设置（与用户密码同机制，走 stdin）")
    else:
        runner.reporter.note(
            f"root 未设密码（账号保持锁定）：只能用 {cfg.user} + sudo 提权。"
            f"要设就在装完之后 `arch-chroot {cfg.target} passwd root`，或重装时带上 --root-password-stdin"
        )

    # 3. locale：写在 /etc/locale.gen 里的是「要生成什么」，locale-gen 才真的生成
    runner.reporter.emit(step_event("configure", "locale", f"生成语言环境 {cfg.locale}"))
    runner.run(chroot_argv(target, ["locale-gen"]), exit_code=EXIT_CONFIGURE)

    # 4. keyring 再 populate 一次（幂等）—— roadmap §M1 把它算在 configure 的职责里，
    #    也是检查点 6 的排查入口：这一步没做，装后系统的 pacman -Syu 必挂
    runner.reporter.emit(step_event("configure", "keyring-refresh", "填充目标密钥环"))
    runner.reporter.note("几十秒")
    runner.run(chroot_argv(target, ["pacman-key", "--populate", "archlinux"]), exit_code=EXIT_CONFIGURE)
    # archlinuxcn 的 key 只能在这里导入：装后 conf 已收紧（#135），而它的 keyring
    # 包由 pacstrap 装进目标 —— packages.init_keyring 跑在 pacstrap 之前，那里没有它
    require_archlinuxcn_keyring(runner, cfg)
    runner.run(chroot_argv(target, ["pacman-key", "--populate", "archlinuxcn"]), exit_code=EXIT_CONFIGURE)

    # 5. 服务：检查点 6 要在装后系统里联网，NetworkManager 必须开机自起
    runner.reporter.emit(step_event("configure", "services", "启用 NetworkManager"))
    runner.run(chroot_argv(target, ["systemctl", "enable", "NetworkManager"]), exit_code=EXIT_CONFIGURE)
    runner.run(chroot_argv(target, ["systemctl", "enable", "mipl-mirror-watch.service"]),
               exit_code=EXIT_CONFIGURE)

    # 5.5 reflector 守卫（#23）：装了才关，没装就不产生任何命令
    if target_has_reflector(target):
        runner.reporter.emit(step_event("configure", "reflector", "关掉 reflector 的定时器"))
        runner.run(chroot_argv(target, reflector_guard(True)), exit_code=EXIT_CONFIGURE)
        runner.reporter.note("目标里有 reflector，已 disable reflector.timer / reflector.service（#23）")

    # 6. initramfs 放最后：它要往 /boot（= ESP）里写内核与 initramfs，
    #    所以必须在 ESP 挂好之后、boot.py 校验之前跑
    #    -P 连 fallback 救援镜像一起生成：弱 CPU 上这一步以分钟计，**先说出来**
    #    才有用（实机「卡了六分钟」的高发点之一）—— 说「要等几分钟」是给用户的
    #    预期，说「输出会持续到达」是替工具打包票（mkinitcpio 大部分时间在压缩，
    #    本来就不怎么输出），而那句空头支票实机反馈里被点过名。
    runner.reporter.emit(step_event("configure", "initramfs", "生成 initramfs（含救援镜像）"))
    runner.reporter.note("弱 CPU 上以分钟计；大部分时间在压缩，期间不会有新输出")
    runner.run(chroot_argv(target, ["mkinitcpio", "-P"]), exit_code=EXIT_CONFIGURE)


def configure_system(
    runner: Runner,
    cfg: TargetConfig,
    *,
    root_uuid: str,
    esp_uuid: str,
    password: str,
    root_password: str | None = None,
) -> None:
    copy_pacman_config(runner, cfg)
    copy_mirror_switch(runner, cfg)
    copy_fonts_conf(runner, cfg)
    write_static_files(runner, cfg, root_uuid, esp_uuid)
    run_in_chroot(runner, cfg, password, root_password)
