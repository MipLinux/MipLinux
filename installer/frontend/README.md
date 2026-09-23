# installer/frontend · 安装器前端（M2）

这里放 PySide6 的图形界面。**M1 阶段还没有代码** —— 这个文件存在的唯一目的，
是把接口先定下来，免得界面先写起来、把逻辑抄进前端（见 [installer/AGENTS.md](../AGENTS.md) 第一条约定）。

## 一条规则

**前端只订阅事件，不实现逻辑。** 唯一允许的依赖是后端的事件流：

```python
from mipl_installer.events import Event, Reporter
```

- `backend/mipl_installer/` 里**不许**出现 `PySide6` / `Qt` 的 import；
- `frontend/` 里**不许**出现分区、`pacstrap`、chroot 配置、写引导 —— 那些全在后端。
  界面要做进度条，就实现一个 `Reporter`：

```python
class QtReporter:                       # 前端侧
    def emit(self, event: Event) -> None: ...
```

事件名（后端 `events.PHASES`）是**稳定接口**：`start / disk / packages / configure / boot / done`。
改名字等于改接口，先和后端对齐。

## 目录（M2 落地时）

```
frontend/
└── mipl_installer_qt/      与 backend/mipl_installer 对称的包名
```

界面怎么被拉起来（`cage` kiosk、`frontend/mipl-installer` 入口）属线 E 的活，
见 [installer/AGENTS.md](../AGENTS.md) 与 [installer-roadmap.md](../../docs/work/installer-roadmap.md) §4 的 M0 / M2。
