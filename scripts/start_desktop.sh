#!/usr/bin/env bash
set -euo pipefail
AUTHFILE="$HOME/.Xauthority-sim"
mkdir -p "$HOME/.vnc" "$HOME/remote-sim-viz/frames"
chmod 700 "$HOME/.vnc" "$HOME/remote-sim-viz" "$HOME/remote-sim-viz/frames"
touch "$AUTHFILE"
chmod 600 "$AUTHFILE"
if ! xauth -f "$AUTHFILE" list ':1' | grep -q .; then
    xauth -f "$AUTHFILE" add :1 . "$(mcookie)"
fi
if ! tmux has-session -t sim-xvfb 2>/dev/null; then
    tmux new-session -d -s sim-xvfb "Xvfb :1 -screen 0 1600x900x24 -nolisten tcp -auth '$AUTHFILE'"
fi
for i in $(seq 1 20); do
  if DISPLAY=:1 XAUTHORITY="$AUTHFILE" xdpyinfo >/dev/null 2>&1; then break; fi
  sleep 0.25
done
DISPLAY=:1 XAUTHORITY="$AUTHFILE" xdpyinfo | grep dimensions
if ! tmux has-session -t sim-openbox 2>/dev/null; then
    tmux new-session -d -s sim-openbox "DISPLAY=:1 XAUTHORITY='$AUTHFILE' openbox"
fi
if ! tmux has-session -t sim-xterm 2>/dev/null; then
    tmux new-session -d -s sim-xterm "DISPLAY=:1 XAUTHORITY='$AUTHFILE' xterm -geometry 100x24+50+50"
fi
if [ ! -f "$HOME/.vnc/passwd" ]; then
    echo "No VNC password. Run: x11vnc -storepasswd '$HOME/.vnc/passwd'"
    exit 1
fi
if ! tmux has-session -t sim-vnc 2>/dev/null; then
    tmux new-session -d -s sim-vnc "x11vnc -display :1 -auth '$AUTHFILE' -rfbauth '$HOME/.vnc/passwd' -rfbport 5901 -localhost -forever -shared -noxdamage"
fi
echo "VNC (loopback only) started. Check: ss -lnt | grep 5901"
