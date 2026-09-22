"""MipLinux 安装器核心。

这个包**不依赖 Qt** —— 界面（`mipl_installer_qt`）只是它的第二个调用者，
所以「分区 → 装包 → 配置 → 写引导」这条链必须先在没有界面的情况下跑通
（installer/AGENTS.md 的「逻辑先于外壳」）。

两条结构性约定：

* 外部命令一律经 `util.Runner`，不在这里直接 `subprocess` —— 单测注入替身
  就能验证「会跑哪些命令」，不必真的动盘。
* 系统盘的写操作集中在 `disk.py` / `boot.py`，其余模块是可断言的纯函数。

入口：`python3 -m mipl_installer --help`
"""

__version__ = "0.1.0"
