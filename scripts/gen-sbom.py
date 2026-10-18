#!/usr/bin/env python3
"""从包清单生成 package-level SPDX 2.3 JSON。

许可证清单不手工维护：包名、版本、Licenses 都来自 pacman 的本地数据库。
在 Live 构建容器里用 `-Si` 查仓库；在装后 rootfs 里用 `--installed` 查已装包。
不联网、不修改包、不把 SBOM 当成 GPL 源码交付（源码见 SOURCE-OFFER.md）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SPDX_VERSION = "SPDX-2.3"
DATA_LICENSE = "CC0-1.0"


def read_pkglist(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    if not names:
        raise SystemExit(f"{path}: 包清单为空")
    return names


def pacman_fields(name: str, installed: bool) -> dict[str, str]:
    flag = "-Qi" if installed else "-Si"
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    proc = subprocess.run(
        ["pacman", flag, name],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise SystemExit(f"pacman {flag} {name} 失败: {detail}")

    fields: dict[str, str] = {}
    key: str | None = None
    for line in proc.stdout.splitlines():
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            fields[key] = value.strip()
        elif line.startswith(" ") and key:
            fields[key] = f"{fields[key]} {line.strip()}".strip()
    return fields


def license_declared(raw: str) -> str:
    """pacman 的 Licenses 字段映射到 SPDX；custom/unknown 用 NOASSERTION。"""
    value = raw.strip()
    if not value or value.lower() in {"custom", "unknown", "none"}:
        return "NOASSERTION"
    # SPDX 表达式允许字母、数字、. + - 与 AND/OR/WITH/括号；出现 custom 时不给假表达式。
    if "custom" in value.lower():
        return "NOASSERTION"
    if not re.fullmatch(r"[A-Za-z0-9.+()\- ]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+()\- ]+)*", value):
        return "NOASSERTION"
    return value


def spdx_id(name: str, index: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9.-]", "-", name)
    return f"SPDXRef-Package-{safe}-{index}"


def purl(name: str, version: str, fields: dict[str, str]) -> str:
    arch = fields.get("Architecture", "").strip()
    repo = fields.get("Repository", "").strip()
    value = f"pkg:alpm/arch/{name}@{version}"
    query = []
    if arch:
        query.append(f"arch={arch}")
    if repo:
        query.append(f"repository={repo}")
    if query:
        value += "?" + "&".join(query)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="从 MipLinux 包清单生成 SPDX 2.3 JSON")
    parser.add_argument("--pkglist", required=True, type=Path, help="每行一个包名；# 开头为注释")
    parser.add_argument("--output", required=True, type=Path, help="输出 JSON 路径")
    parser.add_argument("--installed", action="store_true", help="用 pacman -Qi（装后 rootfs）而不是 -Si")
    parser.add_argument("--name", default="MipLinux package SBOM", help="SPDX 文档名")
    args = parser.parse_args()

    names = read_pkglist(args.pkglist)
    packages = []
    for index, name in enumerate(names):
        fields = pacman_fields(name, args.installed)
        version = fields.get("Version", "").strip()
        if not version:
            raise SystemExit(f"{name}: pacman 输出缺少 Version")
        raw_license = fields.get("Licenses", "custom")
        declared = license_declared(raw_license)
        entry = {
            "SPDXID": spdx_id(name, index),
            "name": name,
            "versionInfo": version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": declared,
            "licenseComments": f"pacman Licenses: {raw_license.strip() or 'unknown'}",
            "copyrightText": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": purl(name, version, fields),
                }
            ],
        }
        packages.append(entry)

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    created = now.isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()[:16]
    doc = {
        "spdxVersion": SPDX_VERSION,
        "dataLicense": DATA_LICENSE,
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": args.name,
        "documentNamespace": f"https://github.com/MipLinux/MipLinux/spdx/{digest}-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: mip-sbom"],
        },
        "documentDescribes": [p["SPDXID"] for p in packages],
        "packages": packages,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写入 {args.output}（{len(packages)} 个包）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
