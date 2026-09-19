# 仅在物理 TTY 下把 locale 降级为英文，避免中文豆腐块
if [ "$TERM" = "linux" ]; then
    case "$(tty)" in
        /dev/tty[1-6])
            export LANG=en_US.UTF-8
            export LANGUAGE=en_US
            ;;
    esac
fi
