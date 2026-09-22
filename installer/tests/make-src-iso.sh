#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# 把仓库里的 installer/ 打成一张**只读小 ISO**，给 Live 内排练用。
#
# 为什么是 ISO 而不是挂载共享目录：
#   * 线 E 还没把 installer/ 拷进 airootfs，所以 Live 里没有这份代码；
#   * 改 scripts/ 给 QEMU 加参数属线 E 的文件，不能碰；
#   * `MIPL_QEMU_EXTRA` 是 mipl.sh 已有的逃生口，只用它加一个光驱就够 ——
#     而 isofs 是内核自带的，比 9p 少一层「模块在不在」的不确定性。
#
# 不需要 root：产物落在 /tmp，不进 out/（out/ 是构建产物目录，别混进来）。
#
# 用法：  ./installer/tests/make-src-iso.sh [输出路径]
# 之后：  sudo MIPL_QEMU_EXTRA="-drive file=/tmp/mipl-installer-src.iso,media=cdrom,readonly=on,if=virtio" \
#           ./scripts/mipl.sh qemu --disk target.qcow2
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

self_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -P "${self_dir}/../.." && pwd)"
output="${1:-/tmp/mipl-installer-src.iso}"

command -v xorrisofs >/dev/null || {
  printf '[错误] 找不到 xorrisofs（包：libisoburn）\n' >&2
  exit 1
}

# -graft-points：把仓库里的 installer/ 放到 ISO 的 /installer ——
# Live 里就是 `/run/mipl-src/installer`，于是 PYTHONPATH 有确定的值。
xorrisofs -quiet -r -J -V MIPLSRC -o "${output}" \
  -graft-points "installer=${repo_root}/installer"

printf '[完成] %s（%s）\n' "${output}" "$(du -h "${output}" | cut -f1)"
printf '下一步：挂第二个光驱起 QEMU，见 docs/work/tech/04-安装逻辑与实测.md\n'
