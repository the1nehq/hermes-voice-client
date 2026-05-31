#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CLIENT="$APP_DIR/Contents/Resources/hermes_voice_client.py"
VENV_DIR="$APP_DIR/Contents/Resources/venv"
PYTHON="$VENV_DIR/bin/python3"

# ── Help the C compiler find Homebrew libraries (Apple Silicon + Intel) ──
export CPATH="/opt/homebrew/include:/usr/local/include${CPATH:+:$CPATH}"
export LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"

# ── Check Python ──
if ! command -v python3 &>/dev/null; then
    osascript -e 'display dialog "Python 3 not found.\n\nInstall with:\nbrew install python3" buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

# ── Check system deps ──
if ! python3 -c "import sounddevice" 2>/dev/null; then
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

# ── Create venv if not exists ──
if [ ! -f "$PYTHON" ]; then
    osascript -e 'display notification "Setting up Hermes Voice..." with title "Hermes Voice"'
    python3 -m venv "$VENV_DIR"
fi

# ── Install / verify Python deps in venv ──
if ! "$PYTHON" -c "import rumps, sounddevice, pynput, requests" 2>/dev/null; then
    osascript -e 'display dialog "Installing Python dependencies...\nThis may take a minute." buttons {"OK"} default button "OK" giving up after 2'
    "$PYTHON" -m pip install --quiet rumps sounddevice pynput requests || {
        # pip failed — rebuild venv from scratch
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        "$PYTHON" -m pip install --quiet rumps sounddevice pynput requests || {
            osascript -e 'display dialog "Failed to install Python dependencies.\n\nMake sure these are installed first:\nbrew install portaudio ffmpeg pkg-config\n\nThen re-open the app." buttons {"OK"} default button "OK" with icon stop'
            exit 1
        }
    }
fi

# ── Launch client ──
exec "$PYTHON" "$CLIENT"
