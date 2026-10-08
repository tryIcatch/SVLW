#!/usr/bin/env bash
for name in sim-preview sim-vnc sim-xterm sim-openbox sim-xvfb; do
    tmux kill-session -t "$name" 2>/dev/null || true
done
echo 'Virtual desktop components stopped. Training processes in other tmux sessions are untouched.'
