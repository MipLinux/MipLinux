# 12 · QEMU 自动化驱动（QMP 半段）

> 配套入口：`scripts/mipl-qmp.sh`（QMP 客户端）+ `scripts/mipl.sh qemu|installer --qmp`（开通道）。
> 串口 socket 驱动那半段归 `installer/tests/live-e2e.py`，本文只讲 QMP 这半段。

## 1. 为什么有它

QEMU 那一轮的「代发按键、截图、串口判据」之前没有仓库自带的入口：VM 起来之后，
每轮都要现搓 socat 和临时 python。现在人（以及提不了权的 AI Agent）用普通用户身份
就能把回归跑成可重复的脚本 —— 一条命令一个动作，退出码可判。

## 2. 怎么用

```bash
# 1. 起 VM 时开通道（root；无头验机把 -display none 写进环境变量，变量要跟在 sudo 后面）
sudo env MIPL_QEMU_EXTRA="-display none" ./scripts/mipl.sh qemu --qmp --serial file
# installer 同理：sudo ./scripts/mipl.sh installer --qmp
# 脚本会打印 QMP 通道路径，默认 out/qemu-qmp.sock

# 2. 另开终端，普通用户驱动（不需要 sudo）：
./scripts/mipl-qmp.sh status
./scripts/mipl-qmp.sh key ctrl-alt-f2
./scripts/mipl-qmp.sh type 'systemctl status mipl-installer'
./scripts/mipl-qmp.sh shot out/qmp-boot.png
./scripts/mipl-qmp.sh wait-for 'archiso login:' --timeout 60
./scripts/mipl-qmp.sh serial-tail
./scripts/mipl-qmp.sh quit
```

| 动作 | 作用 | 退出码 |
|---|---|---|
| `status` | `query-status`：VM 是否在跑 | 0 在跑；连不上非 0 |
| `key <组合>` | `send-key` 组合键（`ctrl-alt-f2`、`ret`、`down`、`shift-f5` …） | 0 发出 |
| `type <ASCII>` | 逐键敲入文本，大写与常用标点自动带 shift（US 布局） | 0 敲完 |
| `shot [文件]` | `screendump`。PNG 优先，QEMU 没编 PNG 时自动回落 PPM 并**打印实际格式**；默认 `out/qmp-shot.png` | 0 落盘 |
| `wait-for <正则> [--timeout N]` | 轮询 `out/installer-serial.log`（默认 60s），命中打印匹配行 | 命中 0；超时非 0 并打印日志尾部 |
| `serial-tail [N]` | 串口日志尾部（默认 20 行） | 0 |
| `quit` | QMP 关机（与关窗口同级） | 0 |

`MIPL_QMP_SOCK` 可顶掉默认 socket；`MIPL_OUT_DIR` 同理 —— 客户端与 `mipl.sh`
共用同一套路径约定，`wait-for` / `serial-tail` / 默认截图都跟着它走。

## 3. 为什么普通用户连得上（socket 权限走了哪条路）

实测 QEMU 11：`-qmp` 与 `-chardev socket` **都不收 `mode=`**（报
`Invalid parameter 'mode'`），unix socket 默认 0755 —— root 起的 QEMU 出的
socket 非属主连不上。两条候选里选了 **unix socket + mipl.sh 在 socket 出现后
chmod 0666**，不选 `tcp:127.0.0.1:<port>`：

- 通道地址是 out/ 里的**固定路径**，客户端与 mipl.sh 只说一个名字就对齐；
  tcp 要另约端口 —— 固定端口两台 VM 会撞车，动态端口又得多一份「端口写在哪」的协议。
- 暴露面两条路等价：都是本机可达（tcp 绑回环、socket 落在 out/），
  都是「这台机器上的任何用户都能操作这台测试 VM」—— 这正是这个工具要的。

`mipl.sh` 把 QEMU 放到后台、等 socket 一出现（bind 完成）就在**主流程**里
`chmod 0666`，再 `wait` 回前台：权限在 `connect()` 时按文件当前 mode 判，对已绑定的
socket 立即生效，不需要重启 QEMU。不挂独立的后台盯梢进程 —— 盯梢和 QEMU 同进程组，
用户 Ctrl+Z 拿回终端时整个组一起停，盯梢会被冻在 chmod 之前（#125 实测过这种死法）。
完整选型记录在 `scripts/mipl-qmp.sh` 头部注释。客户端自己**不提权**：连不上就打印
「通道没开」或「这条要用 sudo」，退出码非 0。

## 4. 失败时看哪里

| 现象 | 含义与做法 |
|---|---|
| `通道没开：… 不存在` | VM 没起，或没带 `--qmp`。先 `sudo ./scripts/mipl.sh qemu --qmp` |
| `通道没开：… 连不上` | QEMU 已退出，或 socket 是残留。重起 VM 即可 |
| `这条要用 sudo` | socket 在但权限没放开 —— 通常是用旧版 mipl.sh 起的 VM。用新版重起，**别 sudo** |
| `wait-for` 超时 | 非 0 退出并打印日志尾部：先看串口走到哪一步。日志不存在 = 没带 `--serial file` |
| 截图纯黑 | **别当失败**：cage 用 KMS 接手显示后 `screendump` 就是纯黑（[tech/04](04-安装逻辑与实测.md) §4.4 实测）。截图判据只用文本控制台（引导消息、登录提示），不要用黑屏当「窗口没出来」的证据 |
| QMP 报错 `<JSON>` | 命令被 QEMU 拒了（比如键名拼错会先被客户端拦住），看 `desc` 字段 |

## 5. 离线回归

```bash
./scripts/mipl-qmp.test.sh
```

假 QMP server（python3 标准库），**不需要 root / QEMU / ISO**。覆盖：握手顺序、
命令 JSON、键名映射、`type` 逐键、`shot` 的 PNG/PPM 两条路、`wait-for` 的命中与
超时退出码、`serial-tail`、连接失败的两句人话。退出码 0 = 全过。

## 6. 相关

- 无头 QEMU 与 `screendump` 的历史用法：[02-构建与QEMU测试](02-构建与QEMU测试.md) §C.3
- `screendump` 纯黑的实测结论：[04-安装逻辑与实测](04-安装逻辑与实测.md) §4.4
- 串口 socket 驱动：[`installer/tests/live-e2e.py`](../../installer/tests/live-e2e.py)
