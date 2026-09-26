"""前端怎么找到后端包（`mipl_installer`）。

**这不是多此一举，而且漏了它只在 ISO 里才会炸。** 构建脚本把整个 `installer/`
拷进 `/usr/local/lib/mipl-installer/`（`scripts/baseline-build.sh` 的
`stage_profile`），入口是 `/usr/local/bin/mipl-installer` 这个软链 —— 于是：

    frontend/                      ← `__file__` 解析之后在这里（HERE）
    backend/mipl_installer/        ← 包在这里，**但不在 sys.path 上**

仓库里跑单测不用管（`installer/tests/__init__.py` 自己接了路径），
`sudo ./scripts/mipl.sh shell` 里也没人替我们接。所以路径知识只留这一处：
入口（`mipl-installer`）与工具（`tools/*.py`）都调 `ensure_backend_on_path()`。
"""

from __future__ import annotations

import sys
from pathlib import Path

#: `frontend/` 的父目录就是 `installer/`（仓库里）或 `/usr/local/lib/mipl-installer/`（ISO 里）
HERE = Path(__file__).resolve().parent.parent
BACKEND = HERE.parent / "backend"


def ensure_backend_on_path() -> Path:
    """把 `backend/` 挂到 `sys.path` 上，返回它的路径。幂等。"""
    if BACKEND.is_dir() and str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    return BACKEND
