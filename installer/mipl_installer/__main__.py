"""`python3 -m mipl_installer` 的入口。

单独一个文件，是为了让「怎么被调用」和「怎么干活」分开：
Live 侧入口 `installer/bin/mipl-installer`（由 cage 拉起，属线 E）最终也是调
`cli.main()`，不复制这里的任何逻辑。
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
