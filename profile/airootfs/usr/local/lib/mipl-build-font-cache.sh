#!/bin/sh
# 仅由 ISO 构建钩子调用；成功后删除，不能留到 Live 启动时才扫描字体。
set -eu

# mkarchiso 导出的构建时刻早于装包新建的字体目录。fontconfig 会把缓存的
# 目录时间截到 SOURCE_DATE_EPOCH，随后的校验却可能判它失效并删除。
# 同时消除纳秒，令缓存与 SquashFS 中只有秒精度的目录时间保持一致。
: "${SOURCE_DATE_EPOCH:?必须由 mkarchiso 的构建环境调用}"
for directory in /usr/share/fonts /usr/local/share/fonts; do
    if [ -d "$directory" ]; then
        find "$directory" -type d -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +
    fi
done
fc-cache --system-only --force --verbose

# fc-cache 在清理掉所有无效缓存时仍会返回 0，不能只相信退出码。
set -- /var/cache/fontconfig/*.cache-*
if [ ! -s "$1" ]; then
    echo '错误：Live 字体缓存仍为空，不能作为预生成成功。' >&2
    exit 1
fi
rm -- "$0"
