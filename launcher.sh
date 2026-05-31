#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CLIENT="$APP_DIR/Contents/Resources/hermes_voice_client.py"

# Must use pythonw (GUI Python) for menu bar apps
PYTHON=""
for p in /usr/bin/pythonw3 /usr/local/bin/pythonw3 /opt/homebrew/bin/pythonw3; do
    if [ -x "$p" ]; then
        PYTHON="$p"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    # Fallback: python3 but with a warning
    PYTHON="python3"
fi

# Quick dep check — only pip install if missing, non-interactive
$PYTHON -c "import rumps, sounddevice, pynput, requests" 2>/dev/null || {
    osascript -e 'display dialog "Hermes Voice needs Python packages.\n\nRun in Terminal:\n\npip3 install rumps sounddevice pynput requests\n\nThen reopen this app." buttons {"OK"} default button "OK" with icon stop' &
    exit 1
}

# Show startup notification
osascript -e 'display notification "🔹 Hermes Voice ready — Ctrl+Shift+Space to talk" with title "Hermes Voice"' &

exec $PYTHON "$CLIENT"
