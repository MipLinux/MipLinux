# installer/frontend/bridge · 前端与后端的接线层

这里放**唯一允许**的前后端耦合：前端实现后端的 `Reporter` 协议，把 `Event`
流翻译成 Qt 的信号；后端**不感知** Qt（见 [frontend/README.md](../README.md)
与 [installer/AGENTS.md](../../AGENTS.md) 第一条）。

## 目录

| 文件 | 管什么 |
|---|---|
| `paths.py` | 把 `backend/` 挂上 `sys.path` —— **漏了它只在 ISO 里发作**（见该文件头） |
| `reporter.py` | `QtReporter`：`Reporter` 协议的 Qt 实现，事件流的唯一通路 |
| `install.py` | `InstallController`：把阻塞的 `pipeline.run()` 放进工作线程 |
| `backend.py` | `Backend`：界面能问系统的事（探测 / 名单 / 校验 / 重启） |
| `records.py` | 后端事实 → 界面记录（**纯函数，不依赖 Qt**，所以能直接单测） |
| `icons.py` | Lucide 图标 provider（`image://lucide/…`） |
| `actions.py` | 重启那一个动作（`Backend.reboot()` 最终落到它） |

QML 侧看到两个对象（由 [mipl-installer](../mipl-installer) 挂上去）：

* `Backend` —— `candidates()` / `partitionPlan()` / `readiness()` / `network()` /
  `wifiNetworks()` / `connectWifi()` / `keymaps()` / `locales()` / `timezones()` /
  `validateUser()` / `validateHostname()` / `validateTimezone()` / `validateKeymap()` /
  `reboot()`；
* `Install` —— `start(request, dryRun)` / `cancel()`，以及
  `phaseChanged` / `logged` / `failed` / `succeeded` / `runningChanged` 五个信号。

## 跨线程的规矩（不变）

后端是阻塞的，跑在工作线程里；`Event` 到界面的**唯一**通路是 Qt 信号（自动排队到
主线程）。**不许**在工作线程里直接改 QML 属性 —— 那是随机崩溃与偶发白屏的经典来源。
`InstallController._run` 是唯一跑后端的地方，它除了 `emit` 信号什么都不碰。

**日志不要自己攒：** `Reporter.command()` 已经把每条外部命令报出来了
（`util.py` 的 `Runner.run` 就调它），进度页的 `LogView` 直接吃它即可，
前端不要再去包装一层 `subprocess`。

## 2026-09-26：四条缺口都补上了

技术栈定案时列的四个后端缺口（[tech/07 §6](../../../docs/work/tech/07-M2界面设计.md)）
不是「以后再说」，是接线的**前置条件**。它们现在的落点：

| # | 缺什么 | 现在在哪 |
|---|---|---|
| 1 | 候选磁盘枚举 | `disk.list_candidates()`（sysfs 枚举 + `blkid` 补文件系统，**不用 `lsblk` 的列表**） |
| 2 | 编排循环从 `cli.py` 抽出来 | `pipeline.py` —— CLI 与图形前端是同一个 `Plan` 的两个调用者 |
| 3 | `confirm()` / 密码可由前端注入 | `pipeline.run(confirm=…)` 是**必填参数**；密码走参数不走 stdin（界面已经在账户页收到了它，再让它抢 TTY 是缘木求鱼） |
| 4 | 键盘与时区可调 | `TargetConfig.keymap` 真参数 + `options.validate_timezone/keymap/hostname`（`vconsole.conf` 不再写死 `us`） |

**守卫一条都没少，而且都提前了。** 擦盘那道「逐字输入设备路径」的确认从 TTY 挪到了
擦除页上，并且 `InstallController._confirm` 会拿它与真正要擦的盘再对一次，对不上就
`EXIT_GUARD` 退出、一个字节都不动。参数校验（用户名 / 主机名 / 时区 / 键盘）在
`pipeline.preflight()` 里于**动盘之前**跑一遍 —— 以前只在落盘前跑，一个打错的时区名
会让人停在「盘已清空、系统装了一半」的现场。实测证据见
[tech/07 §8](../../../docs/work/tech/07-M2界面设计.md)（`tools/wiring-check.py`）。

## 排练开关：只有测试能打开

`Install.start(request, dryRun)` 第二个参数为真时只打印命令序列、不动盘。
**它不是界面上的一条路径**：流程壳从 `MipRehearsal` 这个上下文属性读它，而
`MipRehearsal` 只有 `tools/wiring-check.py` 会挂（Live 的入口不挂）。
签名里那个布尔位如果由界面决定，就等于把「假装装完了」做成了一个可点选项。
