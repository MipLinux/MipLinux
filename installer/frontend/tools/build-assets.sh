#!/usr/bin/env bash
# 从 LOGO 源图生成界面用的小图。
#
# **为什么要有这个脚本：** LOGO 的源图在仓库外（维护者的图片目录），
# 而且它不该以 1 MB 的原尺寸进仓库或进 ISO —— Live 是极简 kiosk，镜像体积是要算的。
# 所以仓库里只放「怎么生成」，生成物由本体决定要不要提交（见 assets/README.md）。
#
# 用法：
#   bash installer/frontend/tools/build-assets.sh            # 缺什么建什么
#   bash installer/frontend/tools/build-assets.sh --force    # 全部重建
#   bash installer/frontend/tools/build-assets.sh --quiet    # 只在出错时说话
#
# 换 LOGO：改 MIPL_LOGO_SRC 或者把新图放到同一个位置再跑一次。

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASSETS="$(cd -- "$HERE/.." && pwd)/assets"

#: LOGO 源图。仓库外 —— 可以用环境变量覆盖。
MIPL_LOGO_SRC="${MIPL_LOGO_SRC:-/home/neo/Pictures/Pictures/MipLinuxLogo.png}"

#: 目标尺寸 → 输出文件名。数值是**裁掉透明边之后的**长边像素。
#:   512  欢迎页主视觉（显示 240px，留 2x 余量给 HiDPI）
#:    96  页头小标（显示 32px，留 3x）
SIZES=(
      "512:mipl-logo-hero.png"
      "96:mipl-logo-mark.png"
)

QUIET=0
FORCE=0
for arg in "$@"; do
      case "$arg" in
            --quiet) QUIET=1 ;;
            --force) FORCE=1 ;;
            -h|--help)
                  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
                  exit 0
                  ;;
            *)
                  echo "不认识的参数：$arg" >&2
                  exit 2
                  ;;
      esac
done

log() { [[ "$QUIET" == "1" ]] || printf '%s\n' "$*"; }

if [[ ! -f "$MIPL_LOGO_SRC" ]]; then
      cat >&2 <<EOF
找不到 LOGO 源图：$MIPL_LOGO_SRC

  → 换台机器时把它放回这个位置，或用 MIPL_LOGO_SRC 指过去：
        MIPL_LOGO_SRC=/path/to/MipLinuxLogo.png bash $0 --force
EOF
      exit 1
fi

if ! command -v magick >/dev/null 2>&1 && ! command -v convert >/dev/null 2>&1; then
      echo "需要 ImageMagick（magick 或 convert）" >&2
      exit 1
fi

# ImageMagick 7 改成了 magick，6 还是 convert —— 两个都认，别写死。
if command -v magick >/dev/null 2>&1; then
      IM=(magick)
else
      IM=(convert)
fi

mkdir -p "$ASSETS"

for spec in "${SIZES[@]}"; do
      size="${spec%%:*}"
      name="${spec##*:}"
      out="$ASSETS/$name"

      if [[ -f "$out" && "$FORCE" != "1" ]]; then
            log "  $name 已存在（--force 可重建）"
            continue
      fi

      # -trim 去掉透明边：源图四周有大量留白（实测内容只占 1112x973，
      # 画布是 1254x1254），不裁的话界面里显示的 logo 会小一大圈。
      # -resize "512x512>" 只在更大时缩小，不放大 —— 放大只会糊。
      "${IM[@]}" "$MIPL_LOGO_SRC" \
            -trim +repage \
            -resize "${size}x${size}>" \
            -strip \
            "$out"

      log "  $name  $(identify -format '%wx%h' "$out")  $(du -h "$out" | cut -f1)"
done

log "LOGO 资产就绪 → $ASSETS"
