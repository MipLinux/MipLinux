# installer/frontend · 安装器前端（M2）

这里放 PySide6 的图形界面。

> **状态：** G3 已完成**设计语言 + 全部页面可跑原型**（2026-09-25，逐页过审）。
> 原型是 QML，能单独取图、也是 M2 真实现的雏形 —— **不做静态稿**，
> 免得设计语言出现两份会漂移的真相。设计规格与实测状态见
> [docs/work/tech/07-M2界面设计.md](../../docs/work/tech/07-M2界面设计.md)。
>
> 页面按流程串起来是（`qml/pages/`，`shots.py --list` 可看全部）：
> 加载 → 欢迎 → 语言 → 键盘 → 时区 → 网络 → 系统磁盘 → 磁盘分区 → 确认擦除 →
> 主机名 → 账户 → 安装详情 → 安装（含失败）→ 结束。
> 另有 `GalleryPage.qml`（控件与状态总览）、`AdvancedPanel.qml`（高级模式面板）。

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

**这一条同样管校验逻辑：** 用户名的合法性来自后端 `configure.validate_user`，
前端**调用**它，不重写一份正则 —— 重写就是「唯一来源」约定在验证逻辑上的翻版。

## 目录

```
frontend/
├── mipl-installer          Live 侧入口（cage 拉起）
├── mipl-kiosk              kiosk 启动脚本（过 seatd-launch 起 cage）
├── assets/                 LOGO 资产（PNG 进仓库，理由见 assets/README.md）
├── icons/lucide/           Lucide 图标，**只放界面用到的那些**（见 icons/README.md）
├── qml/
│   ├── theme/              设计令牌（Tokens.qml）—— 全项目唯一的视觉真相
│   ├── components/         控件：PageShell / Button / Card / Field / Alert / Badge / …
│   ├── pages/              流程各页（欢迎 → … → 结束，见上）+ 失败态 + 高级模式面板
│   └── GalleryPage.qml     控件与状态同屏总览（评审看它）
├── bridge/                 前后端接线层（G3 只留说明，见 bridge/README.md）
└── tools/
    ├── shots.py            把页面渲染成 PNG（本机迭代与评审取图）
    └── build-assets.sh     从 LOGO 源图生成界面用的小图
```

**包名不跟目录名走**（[installer/AGENTS.md](../AGENTS.md)）：目录按角色分，
import 名一律是 `mipl_installer`；前端的 Python 侧沿用这个约定。

## 怎么跑原型

**不要用 `qmlscene` / `qml`** —— 本机实测这两个 Qt 工具连纯 QML 文件都加载不了
（`Library import requires a version`，成因见 [tech/07 §1](../../docs/work/tech/07-M2界面设计.md)）。

```bash
# 取图（默认全部页面 → out/m2-prototype/）
python3 installer/frontend/tools/shots.py
python3 installer/frontend/tools/shots.py --page welcome        # 只看一页
python3 installer/frontend/tools/shots.py --list                # 有哪些页面
python3 installer/frontend/tools/shots.py --size 1024x600       # 验小屏降级
python3 installer/frontend/tools/shots.py --out /tmp/m2-shots   # out/ 属 root 时用它

# 在真实 kiosk 里看（要重建 ISO）
sudo ./scripts/mipl.sh build
sudo ./scripts/mipl.sh installer --serial console
```

`shots.py` 走 PySide6 的 `QQmlApplicationEngine`，**与 `mipl-installer` 是同一条路** ——
所以它不是临时脚手架，而是本机迭代的标准姿势。

## 界面怎么被拉起来

`cage` kiosk 那条链属线 E 的活，见 [installer/AGENTS.md](../AGENTS.md) 与
[installer-roadmap.md](../../docs/work/installer-roadmap.md) §4 的 M0 / M2；
启动链的逐步拆解在 [tech/04](../../docs/work/tech/04-安装逻辑与实测.md) §1。
