#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图标模块生成器：`vendor/icons/*.svg`（Phosphor regular，MIT）→ `renderer/js/icons.js`。

为什么生成：界面里用到的图标必须是**一个家族、统一线宽**（Phosphor regular 的 256 网格），
并且**离线可用**——Live 里没有网络、没有 npm。SVG 原件放在 `vendor/icons/`（连同 LICENSE），
本脚本把它们抽成一张 `{ 名字: 路径数据 }` 表，渲染层用 `icon(name)` 生成 `<svg>`。

    python3 app/tools/gen-icons.py --write   # 重生成
    python3 app/tools/gen-icons.py --check   # 比对（默认）

增删图标 = 往 `vendor/icons/` 放/删 SVG → `--write`。只依赖标准库。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SVG_RE = re.compile(r"<svg[^>]*viewBox=\"([^\"]+)\"[^>]*>(.*)</svg>", re.S)
NON_PATH_RE = re.compile(r"<(?!/?path)[^>]+>")

HEADER = """/**
 * 图标表 · 由 app/tools/gen-icons.py 从 vendor/icons/*.svg 生成 —— 不要手改。
 *
 * 来源：Phosphor Icons v2.1.1（regular，MIT，见 vendor/icons/LICENSE.txt）。
 * 家族纪律：**只用这一套**，不混其他图标库、不手画路径；需要新图标就往 vendor/icons/ 放原件再重生成。
 */

export const VIEW_BOX = '{view_box}';

export const ICONS = {{
"""


def parse(path: Path):
    text = path.read_text(encoding="utf-8")
    match = SVG_RE.search(text)
    if not match:
        raise ValueError(f"{path.name}：没找到 viewBox + 内容")
    view_box, body = match.group(1), match.group(2)
    body = NON_PATH_RE.sub("", body).strip()
    d = " ".join(re.findall(r'<path[^>]*\sd="([^"]+)"', body))
    if not d:
        raise ValueError(f"{path.name}：没有 path 数据")
    return view_box, d


def render(icons: dict[str, str], view_box: str) -> str:
    lines = [HEADER.format(view_box=view_box)]
    for name in sorted(icons):
        lines.append(f"  '{name}':\n    '{icons[name]}',\n")
    lines.append("};\n")
    lines.append(
        "\n/** 生成一个图标 `<svg>`（`currentColor`，尺寸由 CSS 决定）。 */\n"
        "export function icon(name, { className = '' } = {}) {\n"
        "  const d = ICONS[name];\n"
        "  if (!d) throw new Error(`不认识的图标：${name}`);\n"
        "  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');\n"
        "  svg.setAttribute('viewBox', VIEW_BOX);\n"
        "  svg.setAttribute('aria-hidden', 'true');\n"
        "  svg.setAttribute('focusable', 'false');\n"
        "  if (className) svg.setAttribute('class', className);\n"
        "  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');\n"
        "  path.setAttribute('d', d);\n"
        "  svg.append(path);\n"
        "  return svg;\n"
        "}\n"
    )
    return "".join(lines)


def main() -> int:
    here = Path(__file__).resolve()
    app_dir = here.parents[1]
    parser = argparse.ArgumentParser(description="Phosphor SVG → icons.js")
    parser.add_argument("--icons-dir", type=Path, default=app_dir / "vendor" / "icons")
    parser.add_argument("--out", type=Path, default=app_dir / "renderer" / "js" / "icons.js")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    files = sorted(args.icons_dir.glob("*.svg"))
    if not files:
        print(f"❌ {args.icons_dir} 里没有 SVG")
        return 2
    icons: dict[str, str] = {}
    view_box = None
    try:
        for path in files:
            box, d = parse(path)
            view_box = view_box or box
            if box != view_box:
                print(f"❌ {path.name} 的 viewBox 是 {box}，与家族的 {view_box} 不一致")
                return 2
            icons[path.stem] = d
    except (OSError, ValueError) as exc:
        print(f"❌ {exc}")
        return 2

    text = render(icons, view_box)
    if args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"✅ 写入 {args.out}（{len(icons)} 个图标）")
        return 0

    try:
        current = args.out.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"❌ 读不到 {args.out}：{exc}")
        return 2
    if current != text:
        print(f"❌ {args.out} 与 vendor/icons/ 不一致 —— 跑 `--write` 重生成")
        return 1
    print(f"✅ {args.out} 与 vendor/icons/ 一致（{len(icons)} 个图标）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
