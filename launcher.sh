#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CLIENT="$APP_DIR/Contents/Resources/hermes_voice_client.py"
VENV_DIR="$APP_DIR/Contents/Resources/venv"
PYTHON="$VENV_DIR/bin/python3"

# Check Python
if ! command -v python3 &>/dev/null; then
    osascript -e 'display dialog "Python 3 not found.\n\nInstall with:\nbrew install python3" buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

# Check system deps
if ! python3 -c "import sounddevice" 2>/dev/null; then
    # sounddevice not in system Python — check if portaudio C library exists
    PORTAUDIO_FOUND=false

    # Method 1: pkg-config
    if command -v pkg-config &>/dev/null && pkg-config --exists portaudio-2.0 2>/dev/null; then
        PORTAUDIO_FOUND=true
    fi

    # Method 2: look for the dylib directly (brew on Apple Silicon or Intel)
    if [ "$PORTAUDIO_FOUND" = false ]; then
        for lib_dir in /opt/homebrew/lib /usr/local/lib; do
            if [ -f "$lib_dir/libportaudio.dylib" ] || [ -f "$lib_dir/libportaudio.a" ]; then
                PORTAUDIO_FOUND=true
                break
            fi
        done
    fi

    if [ "$PORTAUDIO_FOUND" = false ]; then
        osascript -e 'display dialog "Missing portaudio.\n\nInstall with:\nbrew install portaudio ffmpeg" buttons {"OK"} default button "OK" with icon stop'
        exit 1
    fi
fi

# Create venv if not exists
if [ ! -f "$PYTHON" ]; then
    osascript -e 'display notification "Setting up Hermes Voice..." with title "Hermes Voice"'
    python3 -m venv "$VENV_DIR"
    "$PYTHON" -m pip install --quiet rumps sounddevice pynput requests
fi

# Install missing deps in venv
"$PYTHON" -c "import rumps, sounddevice, pynput, requests" 2>/dev/null || {
    osascript -e 'display dialog "Installing Python dependencies..." buttons {"OK"} default button "OK" giving up after 2'
    "$PYTHON" -m pip install --quiet rumps sounddevice pynput requests
}

# Launch client (prefer pythonw for GUI runloop)
if command -v pythonw3 &>/dev/null; then
    # pythonw3 doesn't know about venvs — use venv python directly but with GUI mode
    exec "$PYTHON" "$CLIENT"
else
    exec "$PYTHON" "$CLIENT"
fi
