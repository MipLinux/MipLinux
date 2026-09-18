#!/usr/bin/env fish
# ─────────────────────────────────────────────────────────────────────
# mipl · fish 入口（薄封装）
#
#   ./scripts/mipl.fish doctor
#   ./scripts/mipl.fish qemu
#
# 所有逻辑都在同目录的 mipl.sh 里，这里只做转发 —— 两套实现一定会漂移，
# 而漂移出来的差异只会在「换机器时」暴露，那正是最不该出问题的时候。
#
# 两种用法都支持：
#   1. 直接当脚本跑：        ./scripts/mipl.fish qemu
#   2. 软链成 fish 函数：    ln -s "$PWD/scripts/mipl.fish" ~/.config/fish/functions/mipl.fish
#      之后直接敲 `mipl qemu`（脚本自身路径会被 realpath 解析回仓库）
#
# 注意这里用 return 而不是 exec：作为函数被 autoload 时 exec 会把你自己
# 的交互式 fish 替换掉。return 在函数里返回、在顶层脚本里等价于退出。
# ─────────────────────────────────────────────────────────────────────

set -l self (status --current-filename)
if test -z "$self"
    echo "mipl.fish: 无法确定自身路径" >&2
    return 1
end

set -l dir (dirname (realpath $self))
set -l entry "$dir/mipl.sh"

if not test -f "$entry"
    echo "mipl.fish: 找不到 $entry" >&2
    return 1
end

bash "$entry" $argv
return $status
