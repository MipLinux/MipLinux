#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V1 · token 三方比对（Electron 版）

    color.json（品牌色板快照） ↔ palette.css（生成物） ↔ docs/work/tech/10 附录 A.1（文档表）

外加两条设计 token 的结构断言（tech/10 §4 / §5）：
  - 圆角只用规定的五档、`--ui-scale` 有默认值、动效时长四档齐全、有 reduced-motion 降级；
  - 双主题都定义了 tech/10 列出的设计 token；
  - `palette.css` 是生成物（顶部必须写明 gen-tokens.py），不许手改。

    python3 app/tools/check-tokens.py          # 退出码 0 = 全过

只依赖标准库；不需要 root、不需要 Electron、不联网。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOC_REL = "docs/work/tech/10-安装器界面视觉方向.md"
TOKEN_COUNT = 35

#: tech/10 §4 锁死的圆角档位（多一档少一档都算漂）
EXPECTED_RADII = {
    "--r-shell": "26px",
    "--r-core": "18px",
    "--r-field": "14px",
    "--r-dialog": "24px",
    "--r-pill": "999px",
}

#: tech/10 §5 的四档时长
EXPECTED_DURATIONS = ("--dur-fast", "--dur-base", "--dur-slow", "--dur-page")

#: 双主题都必须有的设计 token（tech/10 §2 的色 + §7 的判据）
REQUIRED_DESIGN_TOKENS = (
    "--bg", "--surface", "--surface-solid", "--surface-2", "--hairline", "--hairline-strong",
    "--text", "--text-muted", "--text-faint",
    "--accent", "--accent-hover", "--on-accent", "--accent-soft", "--accent-line",
    "--success", "--warning", "--danger", "--on-danger",
    "--aurora-1", "--aurora-2", "--aurora-3",
    "--shadow-1", "--shadow-2", "--shadow-3", "--focus-ring",
)


def find_up(start: Path, rel: str) -> Path:
    for parent in [start, *start.parents]:
        candidate = parent / rel
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"往上找不到 {rel}（从 {start} 起）")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class Checker:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def ok(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ✅ {label}")
        else:
            print(f"  ❌ {label}" + (f" —— {detail}" if detail else ""))
            self.problems.append(label)

    def eq(self, label: str, got, want) -> None:
        self.ok(label, got == want, f"实际 {got!r}，期望 {want!r}")


# ---------------------------------------------------------------- 解析

def doc_palette(doc: str) -> dict[str, tuple[str, str]]:
    """tech/10 附录 A.1 的色板表 → {角色: (dark, light)}。"""
    start = doc.find("### A.1")
    end = doc.find("### A.2", start if start >= 0 else 0)
    if start < 0 or end < 0:
        raise ValueError("tech/10 里找不到 A.1 / A.2 小节")
    table: dict[str, tuple[str, str]] = {}
    for line in doc[start:end].splitlines():
        match = re.match(
            r"^\|\s*`([\w-]+)`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|",
            line,
        )
        if match:
            table[match.group(1)] = (match.group(2).lower(), match.group(3).lower())
    return table


def css_theme_all_vars(css: str, theme: str) -> dict[str, str]:
    """取主题块里的**全部** `--token: 值`（含 rgba / 多值阴影）。"""
    pattern = re.compile(r"\[data-theme=[\"']" + theme + r"[\"']\]\s*\{([\s\S]*?)\}")
    match = pattern.search(css)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        hit = re.match(r"\s*(--[\w-]+):\s*(.+?);\s*$", line)
        if hit:
            values[hit.group(1)] = hit.group(2).strip()
    return values


def css_theme_vars(css: str, theme: str) -> dict[str, str]:
    """取 `[data-theme="<theme>"] { ... }` 块里的 `--token: #hex`。"""
    pattern = re.compile(r"\[data-theme=[\"']" + theme + r"[\"']\]\s*\{([\s\S]*?)\}")
    match = pattern.search(css)
    if not match:
        return {}
    values: dict[str, str] = {}
    for hit in re.finditer(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", match.group(1)):
        values[hit.group(1)] = hit.group(2).lower()
    return values


# ---------------------------------------------------------------- main

def main() -> int:
    here = Path(__file__).resolve()
    app_dir = here.parents[1]  # tools -> app
    parser = argparse.ArgumentParser(description="V1：品牌色板与设计 token 的静态断言")
    parser.add_argument("--color-json", type=Path, default=app_dir / "design" / "color.json")
    parser.add_argument("--palette-css", type=Path, default=app_dir / "renderer" / "css" / "palette.css")
    parser.add_argument("--tokens-css", type=Path, default=app_dir / "renderer" / "css" / "tokens.css")
    parser.add_argument("--doc", type=Path, default=None)
    args = parser.parse_args()

    try:
        snapshot = json.loads(read(args.color_json))
        palette_css = read(args.palette_css)
        tokens_css = read(args.tokens_css)
        doc_path = args.doc or find_up(here.parent, DOC_REL)
        doc = read(doc_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"❌ 输入/解析出错：{exc}")
        return 2

    c = Checker()
    print(f"color.json : {args.color_json}")
    print(f"palette.css: {args.palette_css}")
    print(f"tokens.css : {args.tokens_css}")
    print(f"tech/10    : {doc_path}")
    print()

    # ---- 1. 色板三方：color.json ↔ palette.css ↔ tech/10 A.1
    print("== 品牌色板：color.json ↔ palette.css ↔ tech/10 附录 A.1 ==")
    documented = doc_palette(doc)
    dark, light = snapshot.get("dark", {}), snapshot.get("light", {})
    c.ok(f"color.json 是 {TOKEN_COUNT} 个角色（实际 {len(dark)}）", len(dark) == TOKEN_COUNT)
    c.eq("亮/暗角色集一致", sorted(dark), sorted(light))
    c.ok(f"tech/10 A.1 表是 {TOKEN_COUNT} 行（实际 {len(documented)}）", len(documented) == TOKEN_COUNT)

    css_dark = css_theme_vars(palette_css, "dark")
    css_light = css_theme_vars(palette_css, "light")
    c.ok(f"palette.css dark 是 {TOKEN_COUNT} 个角色（实际 {len(css_dark)}）", len(css_dark) == TOKEN_COUNT)
    c.ok(f"palette.css light 是 {TOKEN_COUNT} 个角色（实际 {len(css_light)}）", len(css_light) == TOKEN_COUNT)

    mismatches = 0
    for role in dark:
        for theme, values, source in (("dark", css_dark, dark), ("light", css_light, light)):
            if values.get(f"--md-{role}") != source[role]:
                mismatches += 1
        if role in documented:
            if dark[role] != documented[role][0] or light[role] != documented[role][1]:
                mismatches += 1
        else:
            c.ok(f"tech/10 A.1 缺角色 {role}", False)
    c.ok(f"35 角色 × 2 模式 × 2 来源全部一致（不一致 {mismatches} 处）", mismatches == 0)
    missing_in_json = [role for role in documented if role not in dark]
    c.ok("color.json 覆盖 tech/10 A.1 的全部角色", not missing_in_json, f"缺 {missing_in_json}")

    c.ok("palette.css 顶部写明由 gen-tokens.py 生成", "gen-tokens.py" in palette_css.split("\n")[0])

    # ---- 2. tokens.css 的结构断言（tech/10 §2 / §4 / §5）
    print("== 设计 token：tokens.css 的结构 ==")
    radii = dict(re.findall(r"(--r-[\w-]+):\s*([^;]+);", tokens_css))
    for name, value in EXPECTED_RADII.items():
        c.eq(f"圆角 {name}", radii.get(name), value)
    c.ok(
        "圆角没有多余的档位",
        set(radii) == set(EXPECTED_RADII),
        f"多出 {sorted(set(radii) - set(EXPECTED_RADII))}",
    )
    c.ok("--ui-scale 有默认值 1", re.search(r"--ui-scale:\s*1\s*;", tokens_css) is not None)
    for name in EXPECTED_DURATIONS:
        c.ok(f"{name} 已定义", re.search(re.escape(name) + r":\s*\d+ms\s*;", tokens_css) is not None)
    c.ok("有 reduced-motion 降级", "prefers-reduced-motion" in tokens_css)

    for theme in ("dark", "light"):
        tokens = css_theme_all_vars(tokens_css, theme)
        missing = [name for name in REQUIRED_DESIGN_TOKENS if name not in tokens]
        c.ok(f"{theme} 主题的设计 token 齐全（{len(REQUIRED_DESIGN_TOKENS)} 项）", not missing, f"缺 {missing}")

    print()
    if c.problems:
        print(f"❌ {len(c.problems)} 项不合格")
        return 1
    print("✅ 品牌色板三方一致；设计 token 结构合规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
