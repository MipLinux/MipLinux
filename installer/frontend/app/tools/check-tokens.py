#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V1 断言：token 字面值与「唯一来源」逐项一致。

三方比对（T2）：
    颜色 : tokens/color.json（快照）↔ MiplColor.qml 字面值 ↔ 08 文档 附录 A.2 表
    字形 : MiplType.qml ↔ 08 §3.2 表（15 档 × 字号 / 行高 / 字距 / 字重）
    形状 : MiplShape.qml ↔ 08 §3.3 表 + README（接口冻结）§3.3 的 `名字 值` 行
    间距 : MiplSpace.qml ↔ 08 §3.4 正文取值 + README §3.4 的 `名字 值` 行
    动效 : MiplMotion.qml ↔ 08 §3.6 时长表 / 缓动表 + README §3.5 的名字与时长行
    缩放 : MiplScale.qml ↔ README §3.6 + 08 §3.10

口径：
- 08 文档与 README 都是**运行期读文件**，脚本里不另抄一份取值表；代码里只固化两条东西：
  ① kebab-case -> camelCase 这条命名规则；② 哪个段落是权威表。
- 发现不一致 → 报错退出非 0，**不就地改任何单例**（单例属于 tokens 线的另一份交付）。
- 本脚本只看静态字面值。**QML 的 `on-*` 信号处理器陷阱静态查不出来**（qmllint 也静默），
  那一条由 tools/probe-tokens.py 真加载来抓；两个脚本互补。

退出码：0 = 全部一致；1 = 有不一致；2 = 输入 / 解析出错。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOC_REL = "docs/work/tech/08-界面设计方向.md"
MINUS = "\u2212"  # 08 §3.2 表里的 Unicode 减号


# ------------------------------------------------------------------ 工具
def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_up(start: Path, rel: str) -> Path:
    for base in [start, *start.parents]:
        candidate = base / rel
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 %s（可用命令行参数指定）" % rel)


def kebab_to_camel(name: str) -> str:
    parts = name.split("-")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def camel_to_kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def section_lines(text: str, heading_prefix: str) -> list[str]:
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith(heading_prefix)), None)
    if start is None:
        raise ValueError("找不到标题 %r" % heading_prefix)
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


def code_cells(cell: str) -> list[str]:
    return [m.strip() for m in re.findall(r"`([^`]+)`", cell)]


def plain(cell: str) -> str:
    return cell.replace("**", "").strip()


def as_float(text: str) -> float:
    return float(text.replace(MINUS, "-"))


def num_list(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?[\d.]+", text.replace(MINUS, "-"))]


# ------------------------------------------------------------------ 文档解析
def doc_colors(doc: str) -> dict[str, tuple[str, str]]:
    """附录 A.2：kebab 角色名 -> (dark, light)。"""
    out = {}
    for cells in table_rows(section_lines(doc, "### A.2 ")):
        if len(cells) < 3:
            continue
        role = code_cells(cells[0])
        dark, light = code_cells(cells[1]), code_cells(cells[2])
        if len(role) == 1 and re.fullmatch(r"#[0-9a-fA-F]{6}", dark[0] if dark else ""):
            out[role[0]] = (dark[0].lower(), light[0].lower())
    return out


def doc_type(doc: str) -> dict[str, tuple[float, float, float, float]]:
    """§3.2 表：kebab 角色 -> (size, lineHeight, tracking, weight)。"""
    out = {}
    for cells in table_rows(section_lines(doc, "### 3.2 ")):
        if len(cells) < 5:
            continue
        role = code_cells(cells[0])
        if len(role) != 1:
            continue
        try:
            out[role[0]] = (as_float(cells[1]), as_float(cells[2]), as_float(cells[3]), as_float(cells[4]))
        except ValueError:
            continue
    return out


def doc_shape(doc: str) -> dict[str, float]:
    """§3.3 表：`corner-extra-small` -> extra-small（再转 camel）。"""
    out = {}
    for cells in table_rows(section_lines(doc, "### 3.3 ")):
        if len(cells) < 2:
            continue
        token = code_cells(cells[0])
        if len(token) != 1 or not token[0].startswith("corner-"):
            continue
        try:
            out[token[0][len("corner-"):]] = as_float(cells[1])
        except ValueError:
            continue
    return out


def doc_space_values(doc: str) -> list[float]:
    """§3.4 正文：6 档 + 页面级 1 档。"""
    values: list[float] = []
    m = re.search(r"只用 6 档：`([^`]+)`", doc)
    if m:
        values += [float(x) for x in re.findall(r"[\d.]+", m.group(1))]
    m = re.search(r"另加页面级\s*`([\d.]+)`", doc)
    if m:
        values.append(float(m.group(1)))
    return sorted(values)


def doc_motion(doc: str) -> tuple[dict[str, float], dict[str, list[float]]]:
    """§3.6：时长表（每行两组）+ 缓动表。"""
    lines = section_lines(doc, "### 3.6 ")
    durations: dict[str, float] = {}
    easings: dict[str, list[float]] = {}
    for cells in table_rows(lines):
        if len(cells) == 4:
            for name_cell, value_cell in ((cells[0], cells[1]), (cells[2], cells[3])):
                name = code_cells(name_cell)
                if len(name) == 1 and re.fullmatch(r"[\d.]+", plain(value_cell)):
                    durations[name[0]] = float(plain(value_cell))
        elif len(cells) == 2 and "(" in cells[1]:
            values = num_list(plain(cells[1]))
            if len(values) != 4:
                continue
            for name in code_cells(cells[0]):
                if name.startswith("easing"):
                    easings[name] = values
    return durations, easings


def doc_scale(doc: str) -> tuple[list[float], list[str]]:
    """§3.10：界面层四档取值与「小 / 默认 / 大 / 更大」。"""
    lines = section_lines(doc, "### 3.10 ")
    text = "\n".join(lines)
    steps: list[float] = []
    # 四个数都必须带小数点：否则会误匹配 §3.7 的图标档 `15 / 18 / 24 / 36`
    m = re.search(r"`(\d+\.\d+ / \d+\.\d+ / \d+\.\d+ / \d+\.\d+)`", text)
    if m:
        steps = [float(x) for x in m.group(1).split("/")]
    names: list[str] = []
    m = re.search(r"四档「([^」]+)」", text)
    if m:
        names = [x.strip() for x in m.group(1).split("/")]
    return steps, names


# ------------------------------------------------------------------ README 解析
def readme_space(readme: str) -> dict[str, float]:
    out = {}
    for cell, value in re.findall(r"`([A-Za-z]+) (\d+)`", "\n".join(section_lines(readme, "### 3.4 "))):
        out[cell] = float(value)
    return out


def readme_shape(readme: str) -> dict[str, float]:
    out = {}
    for cell, value in re.findall(r"`([A-Za-z]+) (\d+)`", "\n".join(section_lines(readme, "### 3.3 "))):
        out[cell] = float(value)
    return out


def readme_durations(readme: str) -> dict[str, float]:
    text = "\n".join(section_lines(readme, "### 3.5 "))
    span = next((s for s in re.findall(r"`([^`]+)`", text) if "short1" in s), "")
    return {name: float(value) for name, value in re.findall(r"([A-Za-z]+\d+)\s+(\d+)", span)}


def readme_easing_names(readme: str) -> set[str]:
    text = "\n".join(section_lines(readme, "### 3.5 "))
    return set(re.findall(r"`(easing[A-Za-z]+)", text))


def readme_type_roles(readme: str) -> list[str]:
    text = "\n".join(section_lines(readme, "### 3.2 "))
    span = next((s for s in re.findall(r"`([^`]+)`", text) if "displayLarge" in s), "")
    return span.split()


def readme_scale(readme: str) -> tuple[list[float], float]:
    text = "\n".join(section_lines(readme, "### 3.6 "))
    steps: list[float] = []
    m = re.search(r"`steps\s*=\s*\[([^\]]+)\]`", text)
    if m:
        steps = [float(x) for x in m.group(1).split(",")]
    m = re.search(r"默认\s*`([\d.]+)`", text)
    return steps, float(m.group(1)) if m else float("nan")


# ------------------------------------------------------------------ QML 解析
def without_comments(qml: str) -> str:
    """去掉 // 行注释与 /* */ 块注释：结构断言只看代码，不看注释（注释里会解释「不乘 factor」之类）。"""
    qml = re.sub(r"/\*.*?\*/", "", qml, flags=re.S)
    return re.sub(r"//[^\n]*", "", qml)


def qml_colors(text: str) -> tuple[dict[str, tuple[str, str]], dict[str, str], list[str]]:
    """MiplColor.qml -> ({camel: (dark, light)}, {alias: 目标属性}, 结构问题)。"""
    literals = re.findall(
        r'readonly property color (\w+): MiplTheme\.dark \? "(#[0-9a-f]{6})" : "(#[0-9a-f]{6})"', text
    )
    values = {name: (dark.lower(), light.lower()) for name, dark, light in literals}
    aliases = {alias: target for alias, _obj, target in
               re.findall(r"readonly property alias (\w+): (\w+)\.(\w+)", text)}
    problems = []
    code = without_comments(text)
    if re.search(r"^\s*property color ", code, re.M):
        problems.append("MiplColor 里出现了可写的 `property color`（冻结要求全部 readonly）")
    if re.search(r"XMLHttpRequest|JSON\.parse", code):
        problems.append("MiplColor 里出现了运行期读 JSON 的写法（冻结要求运行期不读 JSON）")
    bad_aliases = {a: t for a, t in aliases.items() if a != t}
    if bad_aliases:
        problems.append("alias 名与目标属性名不一致：%r" % bad_aliases)
    return values, aliases, problems


def qml_type(text: str) -> tuple[dict[str, dict[str, float]], dict[str, str], list[str]]:
    """MiplType.qml -> ({role: {size,lineHeight,tracking,weight}}, 家族, 结构问题)。"""
    roles: dict[str, dict[str, float]] = {}
    problems = []
    for name, block in re.findall(r"readonly property MiplTypeScale (\w+): MiplTypeScale \{([^{}]*)\}", text):
        fields: dict[str, float] = {}
        for field, value, scaled in re.findall(
            r"(\w+):\s*(-?[\d.]+)\s*(\*\s*MiplScale\.factor)?", block
        ):
            fields[field] = float(value)
            if field in ("size", "lineHeight") and not scaled:
                problems.append("MiplType.%s.%s 没有乘 MiplScale.factor" % (name, field))
            if field in ("tracking", "weight") and scaled:
                problems.append("MiplType.%s.%s 不该乘 MiplScale.factor" % (name, field))
        roles[name] = fields
    families = dict(re.findall(r'readonly property string (family\w*): "([^"]+)"', text))
    return roles, families, problems


def qml_scaled_reals(text: str, what: str) -> tuple[dict[str, float], list[str]]:
    """形状 / 间距：每个 real 都必须 = 基准 × MiplScale.factor。"""
    pairs = re.findall(r"readonly property real (\w+): ([\d.]+) \* MiplScale\.factor", text)
    values = {name: float(value) for name, value in pairs}
    declared = re.findall(r"readonly property real (\w+):", text)
    problems = ["%s.%s 不是 `基准 * MiplScale.factor` 形式" % (what, n) for n in declared if n not in values]
    return values, problems


def qml_motion(text: str) -> tuple[dict[str, float], dict[str, list[float]], list[str]]:
    durations = {name: float(value) for name, value in
                 re.findall(r"readonly property real (\w+): (\d+) \* motionScale", text)}
    declared = re.findall(r"readonly property real (\w+):", text)
    easings = {name: num_list(values) for name, values in
               re.findall(r"readonly property var (\w+): \[([^\]]+)\]", text)}
    problems = []
    if re.search(r"\*\s*MiplScale\.factor", without_comments(text)):
        problems.append("MiplMotion 里有时长乘了 MiplScale.factor（时长只乘 motionScale）")
    problems += ["MiplMotion.%s 不是 `基准 * motionScale` 形式" % n for n in declared if n not in durations]
    return durations, easings, problems


def qml_scale(text: str) -> tuple[float, list[float], list[str]]:
    factor = float(re.search(r"property real factor: ([\d.]+)", text).group(1))
    steps = num_list(re.search(r"readonly property var steps: \[([^\]]+)\]", text).group(1))
    labels = [s.strip().strip('"') for s in
              re.search(r"readonly property var labels: \[([^\]]+)\]", text).group(1).split(",")]
    return factor, steps, labels


# ------------------------------------------------------------------ 比对
class Checker:
    def __init__(self) -> None:
        self.checks = 0
        self.problems: list[str] = []

    def eq(self, label: str, got, want) -> None:
        self.checks += 1
        if got != want:
            self.problems.append("%s：QML=%r，来源=%r" % (label, got, want))

    def ok(self, label: str, condition: bool) -> None:
        self.checks += 1
        if not condition:
            self.problems.append(label)


def main() -> int:
    here = Path(__file__).resolve()
    qml_root = here.parents[3]  # .../qml（tools -> tokens -> Mipl -> qml）
    parser = argparse.ArgumentParser(description="V1：token 字面值三方比对")
    parser.add_argument("--tokens-dir", type=Path, default=here.parent.parent,
                        help="tokens 目录（默认：脚本所在 tools/ 的上一级）")
    parser.add_argument("--color-json", type=Path, default=None, help="默认 <tokens-dir>/color.json")
    parser.add_argument("--doc", type=Path, default=None, help="08 文档（默认自动找 %s）" % DOC_REL)
    parser.add_argument("--readme", type=Path, default=None, help="默认 <qml>/README.md")
    args = parser.parse_args()

    tokens: Path = args.tokens_dir.resolve()
    color_json: Path = args.color_json or tokens / "color.json"
    readme_path: Path = args.readme or qml_root / "README.md"

    try:
        snapshot = json.loads(read_text(color_json))
        doc = read_text(args.doc or find_up(here.parent, DOC_REL))
        readme = read_text(readme_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("❌ 输入/解析出错：%s" % exc)
        return 2

    try:
        qml_color_text = read_text(tokens / "MiplColor.qml")
        qml_type_text = read_text(tokens / "MiplType.qml")
        qml_shape_text = read_text(tokens / "MiplShape.qml")
        qml_space_text = read_text(tokens / "MiplSpace.qml")
        qml_motion_text = read_text(tokens / "MiplMotion.qml")
        qml_scale_text = read_text(tokens / "MiplScale.qml")
    except OSError as exc:
        print("❌ 读不到单例：%s" % exc)
        return 2

    c = Checker()
    print("color.json : %s" % color_json)
    print("08 文档     : %s" % (args.doc or find_up(here.parent, DOC_REL)))
    print("接口冻结    : %s" % readme_path)
    print("tokens     : %s" % tokens)
    print()

    # ---- 颜色：三方比对
    dark, light = snapshot["dark"], snapshot["light"]
    c.ok("color.json 不是 35 个角色（实际 %d）" % len(dark), len(dark) == 35)
    qml_values, qml_aliases, color_problems = qml_colors(qml_color_text)
    for problem in color_problems:
        c.ok(problem, False)
    documented = doc_colors(doc)
    print("== 颜色：color.json ↔ MiplColor.qml ↔ 08 附录 A.2 ==")
    c.ok("08 A.2 表不是 35 个角色（实际 %d）" % len(documented), len(documented) == 35)
    c.ok("MiplColor.qml 不是 35 个属性（实际 %d）" % len(qml_values), len(qml_values) == 35)
    for role in dark:
        camel = kebab_to_camel(role)
        c.eq("MiplColor.%s(dark) vs color.json" % camel, qml_values.get(camel, (None, None))[0], dark[role])
        c.eq("MiplColor.%s(light) vs color.json" % camel, qml_values.get(camel, (None, None))[1], light[role])
        if role in documented:
            c.eq("color.json.%s(dark) vs 08 A.2" % role, dark[role], documented[role][0])
            c.eq("color.json.%s(light) vs 08 A.2" % role, light[role], documented[role][1])
        else:
            c.ok("08 A.2 缺角色 %s" % role, False)
    for role in documented:
        c.ok("color.json 缺 08 A.2 的角色 %s" % role, role in dark)
    for alias, target in qml_aliases.items():
        c.ok("MiplColor.%s 是 alias 但目标 %s 不存在" % (alias, target), target in qml_values)
    color_bad = len(c.problems)
    if color_bad == 0:
        print("  ✅ 35 角色 × 2 模式全部一致（color.json / MiplColor.qml / 08 A.2 三方）")
    else:
        print("  ❌ 颜色有 %d 处不一致" % color_bad)

    # ---- 字形
    print("== 字形：MiplType.qml ↔ 08 §3.2 ↔ README §3.2 ==")
    before = len(c.problems)
    qml_roles, families, type_problems = qml_type(qml_type_text)
    doc_roles = doc_type(doc)
    c.ok("08 §3.2 表不是 15 档（实际 %d）" % len(doc_roles), len(doc_roles) == 15)
    c.ok("MiplType 不是 15 档（实际 %d）" % len(qml_roles), len(qml_roles) == 15)
    role_names = readme_type_roles(readme)
    c.ok("README §3.2 的 15 档名单与 MiplType 不一致：%r" % sorted(set(role_names) ^ set(qml_roles)),
         set(role_names) == set(qml_roles))
    for role, (size, line_height, tracking, weight) in doc_roles.items():
        camel = kebab_to_camel(role)
        fields = qml_roles.get(camel, {})
        for field, want in (("size", size), ("lineHeight", line_height), ("tracking", tracking), ("weight", weight)):
            c.eq("MiplType.%s.%s vs 08 §3.2" % (camel, field), fields.get(field), want)
    c.eq("MiplType.family", families.get("family"), "Noto Sans")
    c.eq("MiplType.familyCjk", families.get("familyCjk"), "Noto Sans CJK SC")
    c.eq("MiplType.familyMono", families.get("familyMono"), "Noto Sans Mono")
    c.eq("MiplType.cjkTracking", float(re.search(r"cjkTracking: ([\d.]+)", qml_type_text).group(1)), 0.0)
    for problem in type_problems:
        c.ok(problem, False)
    print("  ✅ 15 档 × 4 字段一致" if len(c.problems) == before else "  ❌ 字形有 %d 处不一致" % (len(c.problems) - before))

    # ---- 形状
    print("== 形状：MiplShape.qml ↔ 08 §3.3 ↔ README §3.3 ==")
    before = len(c.problems)
    shape_values, shape_problems = qml_scaled_reals(qml_shape_text, "MiplShape")
    for problem in shape_problems:
        c.ok(problem, False)
    for token, value in doc_shape(doc).items():
        c.eq("MiplShape.%s vs 08 §3.3" % kebab_to_camel(token), shape_values.get(kebab_to_camel(token)), value)
    for name, value in readme_shape(readme).items():
        c.eq("MiplShape.%s vs README §3.3" % name, shape_values.get(name), value)
    c.ok("MiplShape 不是 7 档（实际 %d）" % len(shape_values), len(shape_values) == 7)
    print("  ✅ 7 档一致" if len(c.problems) == before else "  ❌ 形状有 %d 处不一致" % (len(c.problems) - before))

    # ---- 间距
    print("== 间距：MiplSpace.qml ↔ 08 §3.4 ↔ README §3.4 ==")
    before = len(c.problems)
    space_values, space_problems = qml_scaled_reals(qml_space_text, "MiplSpace")
    for problem in space_problems:
        c.ok(problem, False)
    c.eq("08 §3.4 的 7 个取值（排序后）", sorted(space_values.values()), doc_space_values(doc))
    for name, value in readme_space(readme).items():
        c.eq("MiplSpace.%s vs README §3.4" % name, space_values.get(name), value)
    c.ok("MiplSpace 不是 7 档（实际 %d）" % len(space_values), len(space_values) == 7)
    print("  ✅ 7 档一致" if len(c.problems) == before else "  ❌ 间距有 %d 处不一致" % (len(c.problems) - before))

    # ---- 动效
    print("== 动效：MiplMotion.qml ↔ 08 §3.6 ↔ README §3.5 ==")
    before = len(c.problems)
    durations, easings, motion_problems = qml_motion(qml_motion_text)
    for problem in motion_problems:
        c.ok(problem, False)
    doc_durations, doc_easings = doc_motion(doc)
    c.ok("08 §3.6 时长不是 16 档（实际 %d）" % len(doc_durations), len(doc_durations) == 16)
    for name, value in doc_durations.items():
        camel = kebab_to_camel(name)
        c.eq("MiplMotion.%s vs 08 §3.6" % camel, durations.get(camel), value)
    for name, value in readme_durations(readme).items():
        c.eq("MiplMotion.%s vs README §3.5" % name, durations.get(name), value)
    for name, values in doc_easings.items():
        camel = kebab_to_camel(name)
        c.eq("MiplMotion.%s vs 08 §3.6" % camel, easings.get(camel), values)
    c.ok("MiplMotion 的缓动名单与 README §3.5 不一致：%r" % sorted(readme_easing_names(readme) ^ set(easings)),
         readme_easing_names(readme) == set(easings))
    c.eq("MiplMotion 时长档数", len(durations), 16)
    c.eq("MiplMotion 缓动条数", len(easings), 7)
    print("  ✅ 16 时长 + 7 缓动一致" if len(c.problems) == before else "  ❌ 动效有 %d 处不一致" % (len(c.problems) - before))

    # ---- 缩放
    print("== 缩放：MiplScale.qml ↔ README §3.6 ↔ 08 §3.10 ==")
    before = len(c.problems)
    factor, steps, labels = qml_scale(qml_scale_text)
    readme_steps, readme_default = readme_scale(readme)
    doc_steps, doc_names = doc_scale(doc)
    c.eq("MiplScale.factor 默认值", factor, 1.0)
    c.eq("MiplScale.steps vs README §3.6", steps, readme_steps)
    c.eq("MiplScale.steps vs 08 §3.10", steps, doc_steps)
    c.eq("MiplScale.factor 默认值 vs README §3.6", factor, readme_default)
    c.eq("labels 档数", len(labels), 4)
    for index, name in enumerate(doc_names):
        label = labels[index] if index < len(labels) else ""
        c.ok("第 %d 档标签缺中文名 %r：%r" % (index + 1, name, label), name in label)
        c.ok("第 %d 档标签缺百分比 %s%%：%r" % (index + 1, int(steps[index] * 100), label),
             "%d%%" % round(steps[index] * 100) in label)
    print("  ✅ 四档取值与标签一致" if len(c.problems) == before else "  ❌ 缩放有 %d 处不一致" % (len(c.problems) - before))

    print()
    print("比对项：%d" % c.checks)
    if c.problems:
        print("❌ 不一致 %d 处：" % len(c.problems))
        for problem in c.problems:
            print("   - %s" % problem)
        return 1
    print("✅ 全部一致：35 角色 × 2 模式全部一致 + 字形 / 形状 / 间距 / 动效 / 缩放逐项对上文档")
    return 0


if __name__ == "__main__":
    sys.exit(main())
