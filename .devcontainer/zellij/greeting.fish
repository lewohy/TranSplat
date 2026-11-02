# Copied to ~/.config/fish/conf.d/ at image build time.
# Shown in place of zellij's release notes, only in the first pane of each zellij session.
if set -q ZELLIJ; and test "$ZELLIJ_PANE_ID" = 0
    function fish_greeting
        echo "zellij 세션: $ZELLIJ_SESSION_NAME"
        echo "  Ctrl o → d   세션 유지하고 나가기 (detach, 터미널 창을 닫아도 동일)"
        echo "  Ctrl o → w   세션 목록 / 전환"
        echo "  Ctrl q       세션 종료 (안의 프로세스도 모두 종료)"
        echo "  마우스 휠 / Ctrl s   스크롤백, Shift+드래그   터미널 자체 텍스트 선택"
    end
end
