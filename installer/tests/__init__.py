"""`installer/tests` 是可发现的测试包。

跑法（仓库根目录）：

    python3 -m unittest discover -s installer/tests -t installer

只用标准库，不在 Live 里引入任何测试依赖。
"""

import sys
from pathlib import Path

# 后端源码在 installer/backend/ 下，而仓库没有做打包（不装 pyproject、不 pip install），
# 所以这里把它的父目录塞进 sys.path —— 路径知识只留这一处，跑测试的人不用记环境变量。
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
