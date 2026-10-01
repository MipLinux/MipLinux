#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2 断言：35 个角色的 14 组前景/背景对比度达标（08 附录 A.3 的 14 组 × 亮/暗 = 28 组）。

方法（照抄 08 A.3 的说明，用纯 stdlib 重写 Material 的那三个函数）：
    tone(hex)            = HCT 的 T。MCU 里 Hct 的 tone 就是 sRGB 的 CIE L*（ColorUtils.lstarFromArgb）。
    y_from_tone(t)       = ColorUtils.yFromLstar   （相对亮度，0..100）
    Contrast.ratioOfTones(t1, t2) = (max(Y)+5) / (min(Y)+5)
    → 代数上等价于同一对颜色的 WCAG 相对亮度对比度 (L_hi+0.05)/(L_lo+0.05)，脚本内部会自洽断言这一点。

口径（Lead 已确认，写在这里以免以后被「修」掉）：
- 脚本以「按 A.3 的方法独立重算」为准；A.3 表格里的数字同时打印出来对比，**只提示、不判失败** ——
  08 A.4 的 node 复跑与 A.3 表格存在小数级差异（Lead 报过 14.41/14.38、16.39/16.30），
  本机这次独立重算与 A.3 表格逐项一致（最大差 0.005，即两位小数全等）；差异照实打印，
  不要为了让数字对上而改阈值。
- 另有一处文档/脚本不一致：A.4 的 node `PAIRS` 只有 13 组，漏了 A.3 表格第 2 行
  `on-surface / surface-container`；本脚本按 A.3 表格的 14 组来。
- 阈值只认 A.3：正文 ≥ 4.5:1，大字 / 图标 ≥ 3.0:1。

退出码：0 = 28 组全过；1 = 有组合不合格；2 = 输入/解析出错。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

KAPPA = 24389.0 / 27.0
EPSILON = 216.0 / 24389.0  # (6/29)^3

DOC_REL = "docs/work/tech/08-界面设计方向.md"

# 文档勘误登记（不就地改别人范围内的文档，脚本里显式登记 + 输出提示）：
# 08 A.3 表第 11 行写的是 `on-inverse-surface` / `inverse-surface`，但 MD3 的 35 角色与
# color.json 里只有 `inverse-on-surface`（A.4 的 node `PAIRS` 写的也是 inverseOnSurface）。
# A.3 该行的文档值 10.20 / 11.59 与 `inverse-on-surface` / `inverse-surface` 的重算结果
# 逐位相同，所以按勘误后的角色名计算，并在输出里打印这条提示。
DOC_ERRATA: dict[tuple[str, str], tuple[str, str]] = {
    ("on-inverse-surface", "inverse-surface"): ("inverse-on-surface", "inverse-surface"),
}


# ---------------------------------------------------------------- 颜色数学
def relative_luminance(hex_color: str) -> float:
    """WCAG / MCU 的相对亮度，0..1。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError("不是 6 位 hex 颜色: %r" % hex_color)

    def linearize(component_255: int) -> float:
        c = component_255 / 255.0
        return c / 12.92 if c <= 0.040449936 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def tone(hex_color: str) -> float:
    """Material 的 HCT tone（T 通道）＝该 sRGB 颜色的 CIE L*。"""
    y = relative_luminance(hex_color)
    return y * KAPPA if y <= EPSILON else 116.0 * (y ** (1.0 / 3.0)) - 16.0


def tone_to_y(t: float) -> float:
    """ColorUtils.yFromLstar：tone -> 相对亮度（0..100）。"""
    t = min(100.0, max(0.0, t))
    ft = (t + 16.0) / 116.0
    return 100.0 * (ft**3 if ft**3 > EPSILON else (116.0 * ft - 16.0) / KAPPA)


def ratio_of_tones(t1: float, t2: float) -> float:
    y1, y2 = tone_to_y(t1), tone_to_y(t2)
    lo, hi = min(y1, y2), max(y1, y2)
    return (hi + 5.0) / (lo + 5.0)


def wcag_ratio(hex_fg: str, hex_bg: str) -> float:
    y1, y2 = relative_luminance(hex_fg), relative_luminance(hex_bg)
    lo, hi = min(y1, y2), max(y1, y2)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------- 解析
def find_doc(start: Path) -> Path:
    for base in [start, *start.parents]:
        candidate = base / DOC_REL
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 %s（用 --doc 指定）" % DOC_REL)


def section_lines(text: str, heading_prefix: str) -> list[str]:
    """取以 heading_prefix 开头的标题到下一个二/三级标题之间的正文行。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(heading_prefix):
            start = i + 1
            break
    if start is None:
        raise ValueError("文档里找不到标题 %r" % heading_prefix)
    out = []
    for line in lines[start:]:
        if re.match(r"^#{2,3} ", line):
            break
        out.append(line)
    return out


def table_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def unbold(cell: str) -> str:
    return cell.replace("**", "").strip()


def strip_code(cell: str) -> str:
    m = re.findall(r"`([^`]+)`", cell)
    return m[0].strip() if m else cell.strip()


def parse_a3_pairs(doc_text: str) -> list[tuple[str, str, float, float, float]]:
    """A.3 表 -> [(fg, bg, 最低要求, dark 文档值, light 文档值)]。"""
    rows = table_rows(section_lines(doc_text, "### A.3 "))
    pairs = []
    for cells in rows:
        if len(cells) < 4:  # 组合 | 最低要求 | dark | light
            continue
        names = re.findall(r"`([^`]+)`", cells[0])
        if len(names) != 2:
            continue
        try:
            minimum = float(unbold(cells[1]))
            dark_doc = float(unbold(cells[2]))
            light_doc = float(unbold(cells[3]))
        except ValueError:
            continue
        pairs.append((names[0], names[1], minimum, dark_doc, light_doc))
    return pairs


# ---------------------------------------------------------------- 主流程
def main() -> int:
    parser = argparse.ArgumentParser(description="V2：对比度断言（08 附录 A.3 的 14 组 × 亮/暗）")
    here = Path(__file__).resolve()
    parser.add_argument("--color-json", type=Path, default=here.parent.parent / "color.json",
                        help="色板快照（默认：与本脚本同级的 ../color.json）")
    parser.add_argument("--doc", type=Path, default=None,
                        help="08 文档路径（默认自动从仓库根找 %s）" % DOC_REL)
    args = parser.parse_args()

    doc_path = args.doc or find_doc(here.parent)
    try:
        colors = json.loads(args.color_json.read_text(encoding="utf-8"))
        doc_text = doc_path.read_text(encoding="utf-8")
        pairs = parse_a3_pairs(doc_text)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("❌ 输入/解析出错：%s" % exc)
        return 2

    if not pairs:
        print("❌ 没从 %s 的 A.3 表里解析出任何组合" % doc_path)
        return 2

    dark, light = colors["dark"], colors["light"]
    print("色板   : %s（seed=%s, %d 角色）" % (args.color_json, colors["meta"]["seed"], len(dark)))
    print("文档   : %s（A.3 表 %d 组）" % (doc_path, len(pairs)))
    print()
    print("%-46s %-9s %-22s %-22s" % ("前景 / 背景", "要求", "dark 文档/重算/差", "light 文档/重算/差"))

    failures: list[str] = []
    max_delta = 0.0
    checked = 0
    for fg_doc, bg_doc, minimum, dark_doc, light_doc in pairs:
        fg, bg = DOC_ERRATA.get((fg_doc, bg_doc), (fg_doc, bg_doc))
        if (fg, bg) != (fg_doc, bg_doc):
            print("ℹ 文档勘误: A.3 写的 `%s` / `%s` 在色板里不存在，按 `%s` / `%s` 计算"
                  % (fg_doc, bg_doc, fg, bg))
        row = []
        for mode, palette, documented in (("dark", dark, dark_doc), ("light", light, light_doc)):
            if fg not in palette or bg not in palette:
                failures.append("%s 缺少角色 %s" % (mode, fg if fg not in palette else bg))
                row.append("角色缺失")
                continue
            value = ratio_of_tones(tone(palette[fg]), tone(palette[bg]))
            # 自洽：Contrast.ratioOfTones 必须等于同色 WCAG 相对亮度对比度
            if not math.isclose(value, wcag_ratio(palette[fg], palette[bg]), rel_tol=0, abs_tol=1e-9):
                failures.append("%s %s/%s: ratioOfTones 与 WCAG 口径不自洽" % (mode, fg, bg))
            checked += 1
            max_delta = max(max_delta, abs(value - documented))
            row.append("%6.2f/%6.2f/%+5.2f" % (documented, value, value - documented))
            if value < minimum:
                failures.append("%s %s / %s = %.2f < %.1f" % (mode, fg, bg, value, minimum))
        print("%-46s %-9s %-22s %-22s" % ("%s / %s" % (fg, bg), "%.1f:1" % minimum, row[0], row[1]))

    print()
    print("重算组数: %d（14 组 × 亮/暗）" % checked)
    print("与 A.3 文档值的最大差异: %.3f（仅提示：口径差异照实打印，不判失败）" % max_delta)
    if failures:
        print("❌ 不合格 %d 组：" % len(failures))
        for item in failures:
            print("   - %s" % item)
        return 1
    if checked != 28:
        print("❌ 只算了 %d 组，期望 28 组" % checked)
        return 1
    print("✅ 28 组全过，0 组不合格（正文 ≥ 4.5:1；大字 / 图标 ≥ 3.0:1）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
