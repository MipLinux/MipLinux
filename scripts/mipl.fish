#!/usr/bin/env fish
# ─────────────────────────────────────────────────────────────────────
# mipl · fish 入口（薄封装）
#
#   sudo ./scripts/mipl.fish doctor
#   sudo ./scripts/mipl.fish qemu
#
# 所有逻辑都在同目录的 mipl.sh 里，这里只做两件事：
#   1. 转发 —— 两套实现一定会漂移，而漂移出来的差异只会在「换机器时」
#      暴露，那正是最不该出问题的时候；
#   2. 提前做一次 root 检查，好把提示写成 fish 里能直接用的形式。
#
# 和 mipl.sh 一样：一律要求 root，**不自己提权**。
#
# 想让命令更短，在 ~/.config/fish/functions/mipl.fish 里写个函数：
#
#   function mipl --description 'MipLinux 项目操作台'
#       sudo /绝对路径/scripts/mipl.sh $argv
#   end
#
# 注意 fish 函数没法直接 sudo —— sudo 只接受可执行文件，不认 shell 函数。
# 所以函数体里是「先 sudo，再带脚本路径」。
#
# 这里用 return 而不是 exec：作为函数被 autoload 时 exec 会把你自己
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

if test (id -u) -ne 0
    echo "[错误] 需要 root 权限，当前是普通用户。" >&2
    echo >&2
    echo "  脚本不会自己 sudo，请显式提权后重跑：" >&2
    echo "    sudo $entry $argv" >&2
    echo >&2
    return 1
end

bash "$entry" $argv
return $status
