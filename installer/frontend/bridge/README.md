# installer/frontend/bridge · 前端与后端的接线层

这里放**唯一允许**的前后端耦合：前端实现后端的 `Reporter` 协议，
把 `Event` 流翻译成 Qt 的信号；后端**不感知** Qt（见
[frontend/README.md](../README.md) 与 [installer/AGENTS.md](../../AGENTS.md) 第一条）。

## 为什么现在只有一个 `__init__.py`

**G3 只做原型，不做接线。** 原型的每一页直接吃注入的 `property`，不驱动真安装 ——
这是有意的：设计还没定，接线就是返工。

真接线要等三件事落地（都是后端改动，属线 H，见
[tech/07 §6](../../../docs/work/tech/07-M2界面设计.md)）：

| # | 缺什么 | 不解决会怎样 |
|---|---|---|
| 1 | `disk.list_candidates()` | 磁盘页没有数据源 —— 后端现在只能校验**给定**的路径 |
| 2 | 把编排循环从 `cli.py` 抽到 `pipeline.py` | 前端要么 import CLI 的私有函数、要么把四个步骤抄一遍，两条都破 `installer/AGENTS.md` |
| 3 | `confirm()` / 密码可由前端注入 | `cli.confirm()` 走 `input()`，GUI 永远拿不到 TTY |
| 4 | 键盘与时区可调 | `configure.py` 写死 `KEYMAP=us`，`cli.py` 写死 `Asia/Shanghai` |

## 接线时的形状（先写在这里，免得又抄一遍）

```python
# bridge/reporter.py —— 形状示意，不是实现
from PySide6.QtCore import QObject, Signal
from mipl_installer.events import Event

class QtReporter(QObject):
    event = Signal(str, str, object)   # phase, message, percent
    command = Signal(list)             # 一条外部命令

    def emit(self, event: Event) -> None:
        self.event.emit(event.phase, event.message, event.percent)

    def note(self, message: str) -> None: ...
```

**跨线程的规矩：** 后端是阻塞的，必须跑在工作线程里；`Event` 到界面的**唯一**通路
是 Qt 信号（自动排队到主线程）。**不许**在工作线程里直接改 QML 属性 ——
那是随机崩溃与偶发白屏的经典来源。

**日志不要自己攒：** `Reporter.command()` 已经把每条外部命令报出来了
（`util.py` 的 `Runner.run` 就调它），进度页的 `LogView` 直接吃它即可，
前端不要再去包装一层 `subprocess`。
