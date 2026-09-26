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
* **mirrorlist 的来源是运行系统**（Live），不是代码里的字符串 —— 不在 Python 里
  再抄一份镜像地址，否则国内源就有了第二份会漂移的真相。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import options
from .util import (
    EXIT_CONFIGURE,
    InstallerError,
    Runner,
    chroot_argv,
    ensure_dir,
    read_text,
    write_text,
)

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

    target: str = "/mnt"
    hostname: str = "mipl"
    user: str = "mipl"
    locale: str = "zh_CN.UTF-8"
    timezone: str = "Asia/Shanghai"
    #: 控制台键盘映射（`/etc/vconsole.conf` 的 `KEYMAP`）。**以前写死 `us`** ——
    #: 界面里那个键盘页因此是个摆设（Issue #64）。现在它是真参数。
    keymap: str = "us"
    #: 运行系统上的两份输入（Live 里就是出厂设置）
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
    # 与 Live 出厂（profile/airootfs/etc/environment）同一份真相：fcitx5 需要这三个
    # 变量才会被 GTK / Qt 程序选为输入法模块，没有它们「装了 fcitx5 也打不了中文」。
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
    """把运行系统（Live）的 pacman.conf 与它 Include 的文件一起写进目标。

    Include 的目标在**运行系统**上解析（pacman 的语义，不是相对 conf 文件）。
    少一个文件就硬失败：静默跳过会在装后系统的第一次 `pacman -Syu` 才暴露。
    """
    conf_path = Path(cfg.pacman_conf)
    if not conf_path.is_file():
        raise InstallerError(
            f"找不到 pacman 配置：{cfg.pacman_conf}",
            EXIT_CONFIGURE,
            hint="默认读运行系统的 /etc/pacman.conf —— 这个安装器要在 Live 里跑",
        )
    text = read_text(str(conf_path))
    includes = iter_includes(text)

    write_text(runner, f"{cfg.target}/etc/pacman.conf", text)

    if not includes:
        # conf 里没有 Include（构建期那份 profile/pacman.conf 就是这种写法），
        # 那就至少把 mirrorlist 写进去。
        if not Path(cfg.mirrorlist).is_file():
            raise InstallerError(
                f"找不到 mirrorlist：{cfg.mirrorlist}",
                EXIT_CONFIGURE,
                hint="装后系统要靠它找仓库（检查点 6），不能没有",
            )
        write_text(runner, f"{cfg.target}/etc/pacman.d/mirrorlist", read_text(cfg.mirrorlist))
        return

    for include in includes:
        source = Path(include)
        if not source.is_absolute():
            source = conf_path.parent / source
        if not source.is_file():
            raise InstallerError(
                f"pacman.conf 里 Include 的文件不存在：{include}",
                EXIT_CONFIGURE,
                hint=f"在运行系统上找不到 {source} —— 那是国内源的 mirrorlist，装后系统缺它就升不了级",
            )
        write_text(runner, f"{cfg.target}{include}", read_text(str(source)))


def copy_fonts_conf(runner: Runner, cfg: TargetConfig) -> None:
    """把运行系统（Live）的字体 fallback 配置复制进目标。

    与 pacman.conf / mirrorlist 同一个哲学：出厂设置在 Live（airootfs），安装器
    不复制第二份字符串 —— 中文 fallback 只该有一份真相。字体**包**是清单的事
    （P10 未定），这份配置先就位：等包进来，fallback 立即生效。
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
    """装后系统的 mirrorlist 不能被 reflector 覆盖（#23）。

    reflector 装了就关掉它的 timer / service —— 它一跑，装后系统写好的国内源
    就被重排/换掉，第一次 `pacman -Syu` 直接断（#23 已经踩过）。现在目标清单
    里没有 reflector，这条是**防线**：等 M4 的清单把它带进来时自动生效。
    """
    if not has_reflector:
        return []
    return ["systemctl", "disable", "reflector.timer", "reflector.service"]


def target_has_reflector(target: str) -> bool:
    return Path(f"{target}/usr/lib/systemd/system/reflector.timer").is_file()


def run_in_chroot(runner: Runner, cfg: TargetConfig, password: str,
                  root_password: str | None = None) -> None:
    """必须在目标系统里跑的几条。顺序有讲究，别调换。

    `root_password=None` 表示**保持 root 锁定**（只用 sudo 提权）—— 这是默认，
    但安装器会把这件事**说出来**：一个登不进去的 root 不该让人自己发现。
    """
    target = cfg.target
    validate_user(cfg.user)

    # 1. 用户与密码：密码走 stdin，**不进 argv**（argv 会留在进程列表与日志里）
    runner.run(chroot_argv(target, ["useradd", "-m", "-G", "wheel", "-s", "/bin/bash", cfg.user]),
               exit_code=EXIT_CONFIGURE)
    runner.run(chroot_argv(target, ["chpasswd"]), input=f"{cfg.user}:{password}\n", exit_code=EXIT_CONFIGURE)
    verify_password(runner, cfg, cfg.user)

    # 2. root：设了就验，没设就明说 —— 不许静默留一个登不进去的 root
    if root_password is not None:
        runner.run(chroot_argv(target, ["chpasswd"]), input=f"root:{root_password}\n", exit_code=EXIT_CONFIGURE)
        verify_password(runner, cfg, "root")
        runner.reporter.note("root 密码已设置（与用户密码同机制，走 stdin）")
    else:
        runner.reporter.note(
            f"root 未设密码（账号保持锁定）：只能用 {cfg.user} + sudo 提权。"
            "要设就在装完之后 `arch-chroot /mnt passwd root`，或重装时带上 --root-password-stdin"
        )

    # 3. locale：写在 /etc/locale.gen 里的是「要生成什么」，locale-gen 才真的生成
    runner.run(chroot_argv(target, ["locale-gen"]), exit_code=EXIT_CONFIGURE)

    # 4. keyring 再 populate 一次（幂等）—— roadmap §M1 把它算在 configure 的职责里，
    #    也是检查点 6 的排查入口：这一步没做，装后系统的 pacman -Syu 必挂
    runner.run(chroot_argv(target, ["pacman-key", "--populate", "archlinux"]), exit_code=EXIT_CONFIGURE)

    # 5. 服务：检查点 6 要在装后系统里联网，NetworkManager 必须开机自起
    runner.run(chroot_argv(target, ["systemctl", "enable", "NetworkManager"]), exit_code=EXIT_CONFIGURE)

    # 5.5 reflector 守卫（#23）：装了才关，没装就不产生任何命令
    if target_has_reflector(target):
        runner.run(chroot_argv(target, reflector_guard(True)), exit_code=EXIT_CONFIGURE)
        runner.reporter.note("目标里有 reflector，已 disable reflector.timer / reflector.service（#23）")

    # 6. initramfs 放最后：它要往 /boot（= ESP）里写内核与 initramfs，
    #    所以必须在 ESP 挂好之后、boot.py 校验之前跑
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
    copy_fonts_conf(runner, cfg)
    write_static_files(runner, cfg, root_uuid, esp_uuid)
    run_in_chroot(runner, cfg, password, root_password)
