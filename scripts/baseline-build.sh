#!/usr/bin/env bash
# 基线构建脚本 —— 用未修改的 releng profile 构建 ISO
#
# 用途：这是「第一次构建」的辅助脚本。首次建议按文档手工执行一遍，
#       理解每一步在做什么；之后可以改用这个脚本。
#
# 文档：docs/work/tech/01-容器环境搭建.md
#       docs/work/tech/02-构建与QEMU测试.md
#
# 用法：
#   ./scripts/baseline-build.sh                # 交互式，进入容器后手动执行
#   ./scripts/baseline-build.sh --auto         # 交互式 + 自动执行构建
#
set -euo pipefail

# ── 配置 ────────────────────────────────────────────────────────────
CONTAINER_DIR="/var/lib/machines/archbuild"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/out"
BOOTSTRAP_URL="https://mirrors.tuna.tsinghua.edu.cn/archlinux/iso/latest/archlinux-bootstrap-x86_64.tar.zst"
BOOTSTRAP_FILE="/tmp/archlinux-bootstrap-x86_64.tar.zst"
PROFILE="/usr/share/archiso/configs/releng"

AUTO_BUILD=0
[[ "${1:-}" == "--auto" ]] && AUTO_BUILD=1

# ── 辅助函数 ────────────────────────────────────────────────────────
info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m警告:\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ ${EUID} -eq 0 ]] || die "需要 root 权限。请用 sudo 运行。"
}

# ── 步骤 1 · 下载 bootstrap ─────────────────────────────────────────
step_download() {
  if [[ -f "${BOOTSTRAP_FILE}" ]]; then
    info "bootstrap 已存在，跳过下载: ${BOOTSTRAP_FILE}"
    return
  fi
  info "下载 Arch bootstrap…"
  info "  ${BOOTSTRAP_URL}"
  curl -L --progress-bar -o "${BOOTSTRAP_FILE}" "${BOOTSTRAP_URL}"
  info "下载完成: $(du -h "${BOOTSTRAP_FILE}" | cut -f1)"
}

# ── 步骤 2 · 解压成容器 ─────────────────────────────────────────────
step_extract() {
  if [[ -f "${CONTAINER_DIR}/etc/os-release" ]]; then
    info "容器目录已存在且看起来有效，跳过解压"
    return
  fi
  info "解压到 ${CONTAINER_DIR}…"
  mkdir -p "${CONTAINER_DIR}"
  # --numeric-owner 保留 uid/gid；--strip-components=1 去掉顶层 root.x86_64/
  tar --numeric-owner -xpf "${BOOTSTRAP_FILE}" \
      -C "${CONTAINER_DIR}" --strip-components=1

  [[ -f "${CONTAINER_DIR}/etc/os-release" ]] \
    || die "解压结果异常：找不到 ${CONTAINER_DIR}/etc/os-release"
  info "解压完成"
}

# ── 步骤 3 · 进入容器 ───────────────────────────────────────────────
step_enter() {
  info "准备输出目录: ${OUT_DIR}"
  mkdir -p "${OUT_DIR}"

  if [[ "${AUTO_BUILD}" -eq 1 ]]; then
    info "自动模式：在容器内执行初始化 + 构建"
    cat <<'INNER' > "${CONTAINER_DIR}/root/baseline-build.sh"
#!/usr/bin/env bash
set -euo pipefail
PROFILE="/usr/share/archiso/configs/releng"

echo "==> 初始化密钥环（若尚未初始化）"
if [[ ! -d /etc/pacman.d/gnupg/private-keys-v1.d ]] || \
   [[ -z "$(ls -A /etc/pacman.d/gnupg/private-keys-v1.d 2>/dev/null)" ]]; then
  pacman-key --init
  pacman-key --populate archlinux
else
  echo "    已初始化，跳过"
fi

echo "==> 安装/确认 archiso"
pacman -S --needed --noconfirm archiso

echo "==> 工具链检查"
for c in mkarchiso pacstrap arch-chroot mkinitcpio mksquashfs xorriso; do
  printf '    %-14s ' "$c"
  command -v "$c" >/dev/null 2>&1 && echo "OK" || { echo "缺失"; exit 1; }
done

echo "==> 开始构建（原版 releng）"
mkarchiso -v -w /tmp/work -o /out "${PROFILE}"

echo "==> 构建完成，产物："
ls -lh /out/*.iso
INNER
    chmod +x "${CONTAINER_DIR}/root/baseline-build.sh"

    systemd-nspawn -D "${CONTAINER_DIR}" \
      --bind "${OUT_DIR}:/out" \
      -b --machine=archbuild \
      /root/baseline-build.sh
  else
    info "进入容器。请在容器内执行："
    cat <<'HINT'

  # 首次需要先初始化密钥环
  pacman-key --init && pacman-key --populate archlinux

  # 安装构建工具链
  pacman -S archiso

  # 构建原版 releng
  mkarchiso -v -w /tmp/work -o /out /usr/share/archiso/configs/releng

HINT
    systemd-nspawn -D "${CONTAINER_DIR}" \
      --bind "${OUT_DIR}:/out" \
      -b --machine=archbuild
  fi
}

# ── 主流程 ──────────────────────────────────────────────────────────
main() {
  require_root

  command -v systemd-nspawn >/dev/null 2>&1 \
    || die "找不到 systemd-nspawn"

  step_download
  step_extract
  step_enter

  if [[ "${AUTO_BUILD}" -eq 1 ]]; then
    info "产物列表："
    ls -lh "${OUT_DIR}"/*.iso 2>/dev/null || warn "未找到 ISO 产物"
    echo
    info "下一步：QEMU 引导验证"
    cat <<EOF

  cd ${OUT_DIR}
  cp /usr/share/edk2/x64/OVMF_VARS.4m.fd .
  qemu-system-x86_64 -enable-kvm -m 4096 \\
    -drive if=pflash,format=raw,readonly=on \\
      -file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \\
    -drive if=pflash,format=raw -file=./OVMF_VARS.fd \\
    -cdrom archlinux-*.iso -boot order=d \\
    -netdev user,id=n0 -device virtio-net,netdev=n0

  预期结果：出现 [root@archiso ~]# 提示符
  （官方 releng 没有桌面环境，命令行提示符就是成功）

EOF
  fi
}

main
