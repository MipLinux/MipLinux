#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""品牌色板生成器：`design/color.json` → `renderer/css/palette.css`。

为什么生成而不是手抄
--------------------
35 个 MD3 角色 × 亮/暗 = 70 个值。手抄一次就会漂，而这份色板是**品牌资产**
（种子色取自 logo，由官方算法离线生成）。JSON 是快照，CSS 是它在界面里的落地 —— 方向固定：
**JSON → CSS**，绝不反向。改动只改 JSON（或重生成 JSON），再跑本脚本。

    python3 app/tools/gen-tokens.py --write   # 重生成 palette.css
    python3 app/tools/gen-tokens.py --check   # 比对（默认）

守卫：`check-tokens.py` 还会把 CSS 与 `docs/work/tech/08` 附录 A.2 的表比一遍，
所以「JSON → CSS → 文档」三方都锁住。只依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HEADER = """/* 品牌色板 · 由 app/tools/gen-tokens.py 从 design/color.json 生成 —— 不要手改。
 *
 * 35 个 MD3 角色 × 亮/暗，种子 {seed}（取自 logo，官方算法离线生成）。
 * 换色板 = 改 design/color.json（或它的生成脚本）→ 跑 `python3 app/tools/gen-tokens.py --write`
 * → 跑 `python3 app/tools/check-tokens.py` 确认与 docs/work/tech/08 附录 A.2 仍然一致。
 */

"""


def render(snapshot: dict) -> str:
    seed = snapshot.get("meta", {}).get("seed", "?")
    roles = list(snapshot["dark"].keys())
    parts = [HEADER.format(seed=seed)]
    for theme in ("dark", "light"):
        parts.append(f'[data-theme="{theme}"] {{\n')
        for role in roles:
            parts.append(f"  --md-{role}: {snapshot[theme][role]};\n")
        parts.append("}\n\n")
    return "".join(parts)


def main() -> int:
    here = Path(__file__).resolve()
    app_dir = here.parents[1]
    parser = argparse.ArgumentParser(description="color.json → palette.css")
    parser.add_argument("--color-json", type=Path, default=app_dir / "design" / "color.json")
    parser.add_argument("--out", type=Path, default=app_dir / "renderer" / "css" / "palette.css")
    parser.add_argument("--write", action="store_true", help="重生成")
    parser.add_argument("--check", action="store_true", help="比对（默认动作）")
    args = parser.parse_args()

    try:
        snapshot = json.loads(args.color_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"❌ 读不到色板快照：{exc}")
        return 2

    text = render(snapshot)
    if args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"✅ 写入 {args.out}（{len(snapshot['dark'])} 角色 × 2 模式）")
        return 0

    try:
        current = args.out.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"❌ 读不到 {args.out}：{exc}")
        return 2
    if current != text:
        print(f"❌ {args.out} 与 color.json 不一致 —— 跑 `--write` 重生成")
        return 1
    print(f"✅ {args.out} 与 color.json 一致（{len(snapshot['dark'])} 角色 × 2 模式）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
