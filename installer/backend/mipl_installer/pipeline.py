"""编排：把四个阶段按依赖顺序串起来，并让「失败」有个统一的收尾。

**为什么单独一个模块。** 这段循环原来关在 `cli.py` 里（`_State` + 四个 `_step_*`），
于是 M2 的图形前端只剩两条路：import CLI 的私有函数，或者把四个步骤再抄一遍。
两条都破 [installer/AGENTS.md](../../AGENTS.md) 第一条（前端只订阅事件、不实现逻辑）。
抽到这里之后，CLI 与 Qt 前端是**同一个接口的两个调用者**。

**谁负责守卫。** 这里有一处刻意做成「注入口」而不是「可省项」的东西：

* `confirm` —— 动盘之前的二次确认。CLI 注入的是「读 TTY 让人逐字敲设备路径」，
  图形前端注入的是「擦除页上那道逐字输入的结论」。`run()` 在动盘之前**一定**会调它，
  注入方省不掉，也不该省。
* `should_cancel` —— 只允许**阶段之间**取消，不允许掐断正在跑的命令：
  `pacstrap` 跑到一半被杀，留下的是一个谁都说不清的半成品。取消走的是与失败
  **同一条**收尾路径（卸载目标），不会留下挂着一堆挂载点的现场。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import boot, configure, disk, options, packages, util
from .configure import TargetConfig
from .events import Event, Reporter, step_event
from .util import EXIT_USAGE, InstallerError, Runner

#: 执行顺序即依赖顺序：分区 → 装包 → 配置 → 引导
STEP_ORDER = ("disk", "packages", "configure", "boot")

#: dry-run 且目标不是块设备时，按这个大小算布局（只为把命令序列打印出来）
DRY_RUN_ASSUMED_SIZE = 40 * disk.GiB

#: 用户取消时的退出码（与 Ctrl-C 同一个：130 = 128 + SIGINT）
EXIT_CANCELLED = 130


@dataclass
class State:
    """阶段之间递的东西。默认值是占位符 —— dry-run 下就停在这里。"""

    esp: str = util.DRY
    root: str = util.DRY
    root_uuid: str = util.DRY
    esp_uuid: str = util.DRY
    #: root **真的**挂上 target 了没有。由 `disk.mount_target` 在挂上那一刻置位，
    #: 收尾据此决定要不要卸 —— 不能等 `step_disk` 返回（#105）。
    mounted: bool = False
    packages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Plan:
    """一次安装的**全部意图**：界面上收集到的每个值都落在这里。

    这个对象是前端与后端之间唯一的「要装成什么样」的载体 —— 有它，前端就不必
    拼 argv，后端也不必知道界面上有哪几页。字段与 `TargetConfig` 一一对应，
    `config()` 是唯一的翻译点。
    """

    disk: str
    target: str = util.DEFAULT_TARGET
    hostname: str = "mipl"
    user: str = "mipl"
    locale: str = "zh_CN.UTF-8"
    timezone: str = "Asia/Shanghai"
    keymap: str = "us"
    #: None = 用包清单的出厂路径（`packages.default_packages_file()`）
    packages_file: str | None = None
    pacman_conf: str = "/etc/pacman.conf"
    mirrorlist: str = "/etc/pacman.d/mirrorlist"
    fonts_conf: str = "/etc/fonts/local.conf"
    steps: tuple[str, ...] = STEP_ORDER
    no_nvram: bool = False
    keep_mounted: bool = False

    def config(self) -> TargetConfig:
        return TargetConfig(
            target=self.target,
            hostname=self.hostname,
            user=self.user,
            locale=self.locale,
            timezone=self.timezone,
            keymap=self.keymap,
            pacman_conf=self.pacman_conf,
            mirrorlist=self.mirrorlist,
            fonts_conf=self.fonts_conf,
        )

    def packages_path(self) -> str:
        return self.packages_file or packages.default_packages_file()


#: 动盘之前的二次确认。签名是「计划 + 算好的布局 + 汇报口」，实现里可以问人、
#: 也可以直接返回（`--yes` / 界面上已经确认过）。**它是必填参数**：没有默认
#: 实现，免得有人顺手用 `lambda: None` 把守卫抹掉。
ConfirmHook = Callable[[Plan, disk.Layout, Reporter], None]

#: 取消请求的探针，只在阶段之间被调用。
CancelProbe = Callable[[], bool]

#: 阶段 → 界面上那句「正在做什么」。
#:
#: **放在后端**：前端自己编一句，就是在描述它没做的事 ——「正在从镜像源下载并
#: 安装软件包」这句话是真是假，只有后端知道。前端只负责把它显示出来。
PHASE_ACTIONS = {
    "start": "正在准备安装环境",
    "disk": "正在重新分区并创建文件系统",
    "packages": "正在从镜像源下载并安装软件包",
    "configure": "正在写入系统配置与账户",
    "boot": "正在安装引导",
}


class Cancelled(InstallerError):
    """用户取消。它不是「错误」，但走**同一条**收尾路径：半装的盘留在那里，
    比一句报错更难查（也违反「不许在残骸上继续」）。"""

    def __init__(self) -> None:
        super().__init__(
            "已取消安装",
            EXIT_CANCELLED,
            hint="本次不再继续；盘上留下的是半成品，重新装一次会整盘重来",
        )


def parse_steps(raw: str) -> tuple[str, ...]:
    """`"boot,disk"` → `("disk", "boot")`：按**依赖顺序**跑，不按人敲的顺序。"""
    requested = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in requested if s not in STEP_ORDER]
    if unknown:
        raise InstallerError(
            f"不认识的阶段：{'、'.join(unknown)}",
            EXIT_USAGE,
            hint=f"可选：{'、'.join(STEP_ORDER)}",
        )
    if not requested:
        raise InstallerError("一个阶段都没选", EXIT_USAGE, hint=f"例如 --steps {','.join(STEP_ORDER)}")
    return tuple(s for s in STEP_ORDER if s in requested)


# ── 阶段 ──────────────────────────────────────────────────────────────
def step_disk(runner: Runner, plan: Plan, cfg: TargetConfig, layout: disk.Layout, state: State) -> None:
    state.esp, state.root = disk.wipe_and_partition(runner, plan.disk, layout)
    disk.make_filesystems(runner, state.esp, state.root)
    # 挂上 root 的那一刻就把 `state.mounted` 立起来：ESP 挂载失败、或下面 UUID
    # 读不到时 root 已经挂在盘上了，收尾必须知道（#105）。
    disk.mount_target(runner, state.root, state.esp, cfg.target,
                      on_root_mounted=lambda: setattr(state, "mounted", True))
    # 两个 UUID 是 fstab 与引导项的原料，读不到会当场报错（见 disk.uuid_of）
    runner.reporter.emit(step_event("disk", "uuids", "读取分区 UUID"))
    state.root_uuid = disk.uuid_of(runner, state.root)
    state.esp_uuid = disk.uuid_of(runner, state.esp)


def step_packages(runner: Runner, plan: Plan, cfg: TargetConfig, state: State) -> None:
    state.packages = packages.install(runner, cfg.target, plan.packages_path(), cfg.pacman_conf)


def step_configure(runner: Runner, plan: Plan, cfg: TargetConfig, state: State,
                   password: str, root_password: str | None) -> None:
    configure.configure_system(
        runner, cfg,
        root_uuid=state.root_uuid,
        esp_uuid=state.esp_uuid,
        password=password,
        root_password=root_password,
    )


def step_boot(runner: Runner, plan: Plan, cfg: TargetConfig, state: State) -> None:
    boot.install_bootloader(runner, cfg, state.root_uuid, no_nvram=plan.no_nvram)
    boot.verify(runner, cfg, state.root_uuid)


#: 目标系统里安装日志的固定位置（从挂载起持续并写，不是收尾拷贝）
TARGET_LOG_NAME = "var/log/mipl-installer-install.log"


def attach_target_log(runner: Runner, plan: Plan, reporter: Reporter) -> None:
    """目标盘挂上之后，把日志**持续并写**进目标盘。

    目标盘是安装期间唯一既写得进、又活得过重启/断电的地方。持续写（而不是收尾
    抄一份）意味着：某一步挂死被强杀时，盘上躺着的是到挂死点为止的完整日志 ——
    挂载之前的那几行也由 reporter 在挂落点时从内存补写进去。测试阶段 Bug 多，
    复盘材料必须**默认**就在，不需要任何开关。
    """
    attach = getattr(reporter, "attach_log_path", None)
    if attach is None or runner.dry_run:
        return
    dest = Path(plan.target) / TARGET_LOG_NAME
    try:
        # 建目录也放进 try：目标盘满 / 只读时 `mkdir` 同样会抛 OSError ——
        # 它在 try 外面的话，「日志写不进去不许拖累安装」这句就只对了一半。
        util.ensure_dir(runner, str(dest.parent))
        attach(str(dest))
    except OSError as exc:
        # 日志写不进去不许把安装拖下水：Live 侧那份还在。这一句要说 ——
        # 它意味着「出事后盘上没有证据」，与「日志会写进盘里」正相反。
        reporter.note(f"日志写不进目标盘（{dest}）：{exc}；只保留 Live 侧日志")
        return
    # 记在 reporter 上：失败收尾会先卸载目标，卸完这个路径就看不见了 ——
    # `cli.log_locations()` 靠它把「唯一活过重启的那份日志」报出来。
    try:
        reporter.target_log_path = str(dest)  # type: ignore[attr-defined]
    except AttributeError:
        pass
    # **挂上了不说。** 「我们把日志写到哪儿了」在正常流程里是自我指涉的噪音
    # （实机反馈）；它只在出事时有用，那时由 `cli.log_locations()` 报出来。
    # reporter 上留的这条路径就是「确实挂上并写出来过」的凭据 —— 卸载之后
    # 目录里已经看不到了，但目标盘上那份文件还在。


def detach_target_log(reporter: Reporter) -> None:
    """收尾卸载**之前**把目标盘上的日志关掉。

    不关的话，日志句柄开在目标文件系统上，`umount -R` 一律 `目标忙`（EBUSY）——
    于是「卸载目标」这句旁白与事实相反，挂载留在盘上，下一次开工被自己的残留
    拦在门外。这是实测出来的：取消与正常装完都会中招（#105）。

    关掉之后目标盘那份日志停在关掉前那一行，Live 侧那份继续写到底。
    """
    detach = getattr(reporter, "detach_log_paths", None)
    if detach is None:
        return
    detach()


# ── 动盘之前 ──────────────────────────────────────────────────────────
def preflight(plan: Plan) -> None:
    """**动盘之前**把参数能查的都查掉。

    这几条校验在 `configure` 阶段落盘前还会再跑一遍（最后一道），但那时盘已经
    擦干净了 —— 一个打错的时区名会让用户停在「盘已清空、系统装了一半」的现场。
    所以往前提：**能不能装、参数对不对，都该在 `confirm` 之前有答案。**
    纯函数，不碰盘，也不需要 root。

    阶段列表也在这里查：`Plan` 是公开接口（CLI 与前端共用），`steps` 不一定
    经过 `parse_steps()`。一个拼错的阶段名原来会在 `STEP_TOOLS[step]` 处冒
    `KeyError`；一个重复的 `disk` 会把盘**擦两遍** —— 都必须在碰盘之前拒绝。
    """
    _validate_steps(plan.steps)
    configure.validate_user(plan.user)
    options.validate_hostname(plan.hostname)
    options.validate_locale(plan.locale)
    options.validate_timezone(plan.timezone)
    options.validate_keymap(plan.keymap)
    # 目标挂载点也要在这里查：开工前的自动清理拿它当**归属判据**（`target` 之下
    # 就当成我们自己的残留去卸），而清理跑在守卫之前。`--target /` 放进来的话，
    # 这一关之前的守卫一次都不会跑（#105 复核）。
    options.validate_target(plan.target)


def _validate_steps(steps: tuple[str, ...]) -> None:
    """`Plan.steps` 必须是 `STEP_ORDER` 的子集、不重复、不为空。"""
    steps = tuple(steps)
    if not steps:
        raise InstallerError("一个阶段都没选", EXIT_USAGE,
                             hint=f"例如 --steps {','.join(STEP_ORDER)}")
    unknown = [step for step in steps if step not in STEP_ORDER]
    if unknown:
        raise InstallerError(f"不认识的阶段：{'、'.join(unknown)}", EXIT_USAGE,
                             hint=f"可选：{'、'.join(STEP_ORDER)}")
    repeated = sorted({step for step in steps if steps.count(step) > 1})
    if repeated:
        raise InstallerError(
            f"阶段重复：{'、'.join(repeated)}",
            EXIT_USAGE,
            hint="每个阶段只能跑一次 —— 重复的 disk 会把盘擦两遍，一个字节都还没动",
        )


def resolve_layout(plan: Plan, runner: Runner, reporter: Reporter) -> disk.Layout:
    """算布局，顺便把「该不该动手」的全套守卫跑一遍（`disk.assert_usable`）。

    dry-run 且目标不是块设备时走假定容量：dry-run 的用途就是在一台什么设备都
    没有的机器上先把命令序列看一遍。
    """
    if runner.dry_run and not util.is_block_device(plan.disk):
        reporter.note(
            f"dry-run：{plan.disk} 不是块设备，按 {util.human_size(DRY_RUN_ASSUMED_SIZE)} 计算布局"
        )
        return disk.plan_layout(DRY_RUN_ASSUMED_SIZE)
    mountinfo = util.read_text("/proc/self/mountinfo")
    return disk.assert_usable(
        plan.disk,
        size_bytes=util.size_of_device(plan.disk),
        sources=disk.mount_sources(mountinfo),
        target_mountpoint=plan.target,
        target_mounts=disk.mounts_under(mountinfo, plan.target),
        blocking_ancestors=disk.ancestor_mounts(mountinfo, plan.target),
    )


# ── 主循环 ────────────────────────────────────────────────────────────
def run(
    plan: Plan,
    reporter: Reporter,
    *,
    password: str,
    confirm: ConfirmHook,
    root_password: str | None = None,
    dry_run: bool = False,
    should_cancel: CancelProbe | None = None,
) -> State:
    """按顺序跑完 `plan.steps`，返回阶段之间递下来的 `State`。

    密码走**参数**而不是 stdin：界面已经在账户页收到它了，再让它去抢 TTY 是
    缘木求鱼（而且密码进 argv 会留在进程列表里，这条红线不变）。
    """
    runner = Runner(reporter, dry_run=dry_run)
    cfg = plan.config()

    # 先验参数（纯函数，不碰盘），再查 root 与工具，最后才谈布局与确认 ——
    # 顺序就是「代价从低到高」：一个打错的时区名不该等到盘擦完才说
    preflight(plan)

    if not dry_run:
        util.require_root()
        for step in plan.steps:
            runner.require(util.STEP_TOOLS[step])
        # 上一次被强杀 / 断电时，我们自己的挂载会留在目标命名空间里。**必须在守卫
        # 之前清**：否则它先被 `targetMounted` 拦下，而且那块盘还会被 `diskInUse`
        # 误读成「正在被使用」。只碰目标路径下的东西，祖先上的外来挂载不碰（#105）。
        disk.cleanup_stale_target(runner, plan.target)

    layout = resolve_layout(plan, runner, reporter)
    confirm(plan, layout, reporter)

    state = State()
    try:
        # `start` 是 `events.PHASES` 的第一段 —— 前端那条六段进度条按它点亮。
        # 以前只有 CLI 时不发这一段（终端里没人画进度条），有了界面就必须发。
        reporter.emit(Event("start", PHASE_ACTIONS["start"]))
        for step in plan.steps:
            if should_cancel is not None and should_cancel():
                raise Cancelled()
            reporter.emit(Event(step, PHASE_ACTIONS.get(step, f"阶段：{step}")))
            if step == "disk":
                step_disk(runner, plan, cfg, layout, state)
                if state.mounted:
                    # 盘挂上了就有了持久化落点：从这一刻起日志并写到目标盘
                    attach_target_log(runner, plan, reporter)
            elif step == "packages":
                step_packages(runner, plan, cfg, state)
            elif step == "configure":
                step_configure(runner, plan, cfg, state, password, root_password)
            elif step == "boot":
                step_boot(runner, plan, cfg, state)
    except BaseException:
        # 失败（或取消）就卸干净：留一堆挂载只会让下一次尝试更难查，
        # 也不许在残骸上接着装。（日志不用抢救：一直在目标盘上并写着）
        # 判据是「root 真的挂上过」，不是「disk 阶段跑完了」—— 后者会漏掉
        # ESP 挂载失败、UUID 读不到这两条普通失败路径（#105）。
        if state.mounted:
            reporter.note("失败收尾：卸载目标")
            # 先关掉目标盘上那份日志：开着它 umount 一定 `目标忙`（#105 实测）
            detach_target_log(reporter)
            disk.unmount_target(runner, cfg.target)
        raise
    else:
        if state.mounted and not plan.keep_mounted:
            reporter.note("卸载目标")
            detach_target_log(reporter)
            disk.unmount_target(runner, cfg.target)

    accounts = f"账号：{plan.user}（密码已设，wheel 组，可 sudo）"
    accounts += "、root（已设密码）" if root_password is not None else "、root（未设密码，保持锁定）"
    reporter.emit(Event("done", "装完了 —— 现在可以重启（Live 里 `poweroff`）", percent=100,
                        detail=accounts))
    return state
