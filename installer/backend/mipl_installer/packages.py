"""目标系统的包：读清单 → 初始化 keyring → `pacstrap`。

三处细节都是踩过的坑，写在代码里免得被「顺手简化」掉：

**1. keyring 必须在 pacstrap 之前初始化。**
`pacstrap -K` 会在目标里建一个**空** keyring，而紧接着的 `pacman -S` 要验包签名 ——
装不上。所以顺序是「先 `pacman-key --init` + `--populate archlinux`，再 pacstrap」，
并且**不**用 `-K`（那样等于把 keyring 重置回空的）。检查点 6 的经典故障
（「密钥没在目标系统初始化」）到此被结构性排除。

**2. `-M` / `-G`：不让 pacstrap 顺手把运行环境的东西抄进目标。**
默认它会把**运行系统**的 `/etc/pacman.d/mirrorlist` 抄进目标、还会复制运行系统的
keyring。前者在 Live 里恰好是对的、在别的机器上就是静默引入宿主源（D3 那一类错误）；
与其依赖「恰好」，不如关掉它，由 `configure.py` 显式写。

**3. `Include` 是在「正在运行的系统」上解析的，不是在 `-r <target>` 里。**
`pacstrap` 把 conf 复制到临时文件、用 `pacman -r <target> --config <tmpfile>` 装包 ——
`-r` 不重写 conf 里的绝对路径（pacstrap 自己在装完之后才 `cp` mirrorlist，就是证据）。
所以**跑安装器的地方必须是 MipLinux Live 自己**：它的 `/etc/pacman.d/mirrorlist`
就是我们写的国内源。在别的发行版上直接跑，会悄悄用宿主机的源。

包清单唯一来源（D6 / installer/AGENTS.md）：这里不写死任何包名，只读文件；
`profile/packages.x86_64` 是 **Live** 的清单，不许拿它当装后系统的清单（P10 未定，
M1 先读包内 `data/target-packages.x86_64`）。
"""

from __future__ import annotations

import re
from pathlib import Path

from .events import step_event
from .util import (
    EXIT_PACKAGES,
    EXIT_USAGE,
    InstallerError,
    Runner,
    ensure_dir,
)

#: M1 的临时目标清单。P10 定案后改指向唯一来源，这个文件届时删掉。
#: 放在**包内**的 data/ 里：它跟着包走 —— 线 E 把 installer/ 拷进 airootfs 时不会漏掉它。
PACKAGES_FILE_NAME = "target-packages.x86_64"
PACKAGES_FILE_DIR = "data"

#: Live 的清单：不是装后系统的清单，拿它来装会得到「Live 能跑、装完一堆用不上的东西」。
LIVE_PACKAGES_FILE = "packages.x86_64"


def default_packages_file() -> str:
    """`mipl_installer/data/target-packages.x86_64`（相对本包定位，不依赖 cwd）。"""
    return str(Path(__file__).resolve().parent / PACKAGES_FILE_DIR / PACKAGES_FILE_NAME)


def parse_package_list(text: str) -> list[str]:
    """一行一个包名，`#` 起注释，空行跳过。重复的按首次出现去重。"""
    packages: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        for token in line.split():
            if token not in seen:
                seen.add(token)
                packages.append(token)
    return packages


def read_package_list(path: str) -> list[str]:
    resolved = Path(path).expanduser()
    if not resolved.is_file():
        raise InstallerError(
            f"包清单不存在：{path}",
            EXIT_USAGE,
            hint=f"默认应该在 {default_packages_file()}；也可以用 --packages-file 指定",
        )
    if resolved.name == LIVE_PACKAGES_FILE and resolved.parent.name == "profile":
        raise InstallerError(
            f"这是 Live 的包清单，不是装后系统的：{path}",
            EXIT_USAGE,
            hint="两份清单的关系见 P10（docs/knowledge/06-待定事项.md）；M1 用 mipl_installer/data/target-packages.x86_64",
        )

    packages = parse_package_list(resolved.read_text(encoding="utf-8"))
    if not packages:
        raise InstallerError(
            f"包清单是空的：{path}",
            EXIT_USAGE,
            hint="至少要有 base 与 linux，否则装出来的系统起不来",
        )
    return packages


def init_keyring(runner: Runner, target: str) -> None:
    """在目标系统里建好并填充 keyring（**必须在 pacstrap 之前**，理由见模块开头）。"""
    gpgdir = f"{target}/etc/pacman.d/gnupg"
    ensure_dir(runner, f"{target}/etc/pacman.d")
    # 这两步是实机上「界面像卡死」的高发点（gpg 等熵、导入并签几百个键），
    # 而它们自己的输出又少 —— 先说一句「在动、要多久」，进度页才不至于沉默
    runner.reporter.emit(step_event("packages", "keyring-init", "初始化目标密钥环"))
    runner.reporter.note("缺熵的机器上这一步可能看似停住几十秒")
    runner.run(["pacman-key", "--gpgdir", gpgdir, "--init"], exit_code=EXIT_PACKAGES)
    runner.reporter.emit(step_event("packages", "keyring-populate", "导入并签署 Arch 密钥"))
    runner.reporter.note("几百个键要导入并签署，几十秒")
    runner.run(["pacman-key", "--gpgdir", gpgdir, "--populate", "archlinux"], exit_code=EXIT_PACKAGES)


#: pacman 的进度行：`(14/345) installing foo`。**只认数字与括号** ——
#: 括号后面那句人话会被 LANG 翻译（`正在安装`），而数字和括号在任何语言下都一样。
#: 分母就是这一批要处理的包数（含依赖），由 pacman 自己数出来 ——
#: 不用我们再问一遍仓库，也就不会出现「我们算 21、它装 345」那种对不上的分母。
PACKAGE_PROGRESS = re.compile(r"\((\d+)/(\d+)\)")


class PackageCounter:
    """把 pacman 的 `(14/345)` 接成阶段内的细进度。

    为什么要它：pacstrap 一次要处理几百个包、几分钟里没有别的动静，而界面上除了一句
    「正在下载并安装软件包」什么都没有 —— pacman 其实一直在报「第几个 / 共几个」。
    接出来的方式见 `Runner.run(on_line=…)`：回调拿到的是**同一条清洗过的行**，
    与日志里那行一字不差。

    同一个包会打多行（装包、检查密钥各一行），所以按 `(step, total)` 去重；
    认不出来的行直接放过 —— 这条解析只影响「有没有细进度」，绝不影响装包。
    """

    def __init__(self, reporter) -> None:
        self.reporter = reporter
        self._last: tuple[int, int] | None = None

    def feed(self, line: str) -> None:
        match = PACKAGE_PROGRESS.search(line)
        if not match:
            return
        current = (int(match.group(1)), int(match.group(2)))
        if current == self._last:
            return
        self._last = current
        self.reporter.emit(step_event(
            "packages", "install", f"安装软件包 {current[0]}/{current[1]}",
            step=current[0], total=current[1],
        ))


def pacstrap(runner: Runner, target: str, packages: list[str], pacman_conf: str,
             counter: PackageCounter | None = None) -> None:
    """装包。

    `-C` 显式给 conf（不用运行环境默认的那份含糊）；`-G` 不抄运行系统的 keyring
    （我们已经建好目标自己的）；`-M` 不抄它的 mirrorlist（`configure.py` 写）。
    `counter` 给了就一边跑一边把 `(n/m)` 接成细进度。
    """
    ensure_dir(runner, target)
    runner.run(
        ["pacstrap", "-C", pacman_conf, "-G", "-M", target, *packages],
        exit_code=EXIT_PACKAGES,
        on_line=counter.feed if counter is not None else None,
    )


def install(
    runner: Runner,
    target: str,
    packages_file: str,
    pacman_conf: str,
) -> list[str]:
    """keyring → pacstrap。返回装进目标的包清单（调用方拿它报数）。"""
    packages = read_package_list(packages_file)
    runner.reporter.note(f"目标包清单：{packages_file}（{len(packages)} 个包）")
    init_keyring(runner, target)
    runner.reporter.emit(step_event("packages", "install", "下载并安装软件包"))
    pacstrap(runner, target, packages, pacman_conf, counter=PackageCounter(runner.reporter))
    # configure.py 里还会再 `pacman-key --populate archlinux` 一次（幂等）：
    # roadmap §M1 把这条写进了 configure 的职责，留着它，检查点 6 的排查路径才和文档对得上。
    return packages
