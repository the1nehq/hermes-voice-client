#!/usr/bin/env python3
"""Hermes Voice — macOS menu bar app for push-to-talk voice with Hermes Agent.

Sits in your menu bar. Ctrl+Shift+Space to talk. Release to send.
Response plays through Mac speakers. No Dock icon — lives in menu bar only.

First-time setup:
    brew install portaudio ffmpeg
    pip3 install rumps sounddevice pynput requests
"""

import io
import sys
import time
import threading
import tempfile
import subprocess
import os
from pathlib import Path


def _alert(title, message):
    """Show a macOS dialog. Uses osascript directly to avoid rumps dependency."""
    subprocess.run(["osascript", "-e",
        f'display dialog "{message}" with title "{title}"'
        f' buttons {{"OK"}} default button "OK" with icon stop'],
        timeout=5)


# ── Lazy imports with visible error if anything is missing ──
try:
    import requests
    import sounddevice as sd
    import numpy as np
except ImportError as e:
    _alert("Hermes Voice — Missing Dependencies",
           f"{e}\n\nThe app launcher should have installed these.\n"
           "Re-open the app to retry, or run manually:\n"
           "brew install portaudio ffmpeg pkg-config")
    sys.exit(1)

# — Config ——————————————————————————————————————————
SERVER_URL = os.environ.get("HERMES_VOICE_SERVER", "http://100.114.1.6:9120")
HOTKEY = "<ctrl>+<shift>+<space>"
SAMPLE_RATE = 16000
CHANNELS = 1

# — Icons (emoji in menu bar — no icon file needed) —
ICON_IDLE = "🔹"       # Blue diamond: waiting
ICON_RECORDING = "🟢"  # Green circle: mic active
ICON_SENDING = "🟡"    # Yellow circle: processing
ICON_ERROR = "🔴"      # Red circle: error
ICON_PLAYING = "🔵"    # Blue circle: playing response


class HermesVoiceApp:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.stream = None
        self.recording_lock = threading.Lock()
        self.last_query = ""
        self.last_response_time = 0.0

        # Build rumps app
        import rumps
        self.app = rumps.App("Hermes Voice", title=ICON_IDLE)
        self._build_menu()
        self._setup_hotkey()

    # — Menu ————————————————————————————————————————
    def _build_menu(self):
        import rumps
        self.app.menu = [
            rumps.MenuItem("🎙  Push to Talk  (Ctrl+Shift+Space)", callback=None),
            None,
            rumps.MenuItem(f"⏱  Server: {SERVER_URL.rsplit(':',1)[0].replace('http://','')}", callback=None),
            None,
            rumps.MenuItem("⚙️  Preferences...", callback=self._preferences),
            rumps.MenuItem("🔄  Check Connection", callback=self._check_connection),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    # — Hotkey (pynput) —————————————————————————————
    def _setup_hotkey(self):
        from pynput import keyboard
        self._current_keys = set()

        def on_press(key):
            try:
                self._current_keys.add(key)
            except:
                pass
            if (keyboard.Key.ctrl in self._current_keys and
                keyboard.Key.shift in self._current_keys and
                keyboard.Key.space in self._current_keys):
                self._start_recording()

        def on_release(key):
            if (keyboard.Key.ctrl in self._current_keys and
                keyboard.Key.shift in self._current_keys):
                self._stop_recording()
            try:
                self._current_keys.discard(key)
            except:
                pass

        self._hotkey_listener = keyboard.Listener(
            on_press=on_press, on_release=on_release
        )
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    # — Audio recording ————————————————————————————
    def _start_recording(self):
        with self.recording_lock:
            if self.recording:
                return
            self.recording = True
            self.frames = []
            self.app.title = ICON_RECORDING
            try:
                self.stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    callback=self._audio_callback,
                )
                self.stream.start()
            except Exception as e:
                self.app.title = ICON_ERROR
                import rumps
                rumps.notification("Hermes Voice", "Mic Error", str(e))

    def _stop_recording(self):
        with self.recording_lock:
            if not self.recording:
                return
            self.recording = False
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None

        if not self.frames:
            self.app.title = ICON_IDLE
            return

        wav_bytes = self._encode_wav()
        if len(wav_bytes) < 800:
            self.app.title = ICON_IDLE
            return

        # Send in background thread
        self.app.title = ICON_SENDING
        threading.Thread(target=self._send_to_hermes, args=(wav_bytes,), daemon=True).start()

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            self.frames.append(indata.copy())

    def _encode_wav(self) -> bytes:
        import wave
        audio = np.concatenate(self.frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        return buf.read()

    # — Server communication ————————————————————————
    def _send_to_hermes(self, wav_bytes: bytes):
        import rumps
        t0 = time.time()
        try:
            resp = requests.post(
                f"{SERVER_URL}/voice",
                files={"audio": ("recording.wav", wav_bytes, "audio/wav")},
                timeout=120,
            )
            if resp.status_code == 200:
                elapsed = time.time() - t0
                self.last_response_time = elapsed
                self.app.title = ICON_PLAYING
                self._play_mp3(resp.content)
                self.app.title = ICON_IDLE
            else:
                self.app.title = ICON_ERROR
                # Auto-recover after 5s
                threading.Timer(5.0, lambda: setattr(self.app, 'title', ICON_IDLE) if self.app.title == ICON_ERROR else None).start()
        except requests.exceptions.ConnectionError:
            self.app.title = ICON_ERROR
            rumps.notification(
                "Hermes Voice",
                "Connection Failed",
                f"Cannot reach {SERVER_URL}",
            )
            threading.Timer(10.0, lambda: setattr(self.app, 'title', ICON_IDLE) if self.app.title == ICON_ERROR else None).start()
        except Exception as e:
            self.app.title = ICON_ERROR
            threading.Timer(5.0, lambda: setattr(self.app, 'title', ICON_IDLE) if self.app.title == ICON_ERROR else None).start()

    # — Audio playback —————————————————————————————
    def _play_mp3(self, mp3_bytes: bytes):
        """Play MP3 through system speakers using afplay."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(mp3_bytes)
            tmp = f.name
        try:
            subprocess.run(["afplay", tmp], check=True, timeout=120)
        except FileNotFoundError:
            # afplay is macOS-only — fallback for testing on other platforms
            try:
                from playsound3 import playsound
                playsound(tmp)
            except ImportError:
                pass
        finally:
            Path(tmp).unlink(missing_ok=True)

    # — Menu callbacks —————————————————————————————
    def _preferences(self, sender):
        import rumps
        window = rumps.Window(
            title="Hermes Voice Preferences",
            message=f"Server URL:\n{SERVER_URL}\n\nHotkey: Ctrl+Shift+Space\n\nTo change the server, set the HERMES_VOICE_SERVER\nenvironment variable before launching.",
            default_text=SERVER_URL,
            ok="OK",
        )
        window.run()

    def _check_connection(self, sender):
        import rumps
        try:
            resp = requests.get(f"{SERVER_URL}/health", timeout=5)
            if resp.status_code == 200:
                rumps.notification(
                    "Hermes Voice",
                    "Connected ✅",
                    f"Hermes server online\nLast response: {self.last_response_time:.1f}s",
                )
            else:
                rumps.notification("Hermes Voice", "Server Error", f"Status {resp.status_code}")
        except Exception:
            rumps.notification("Hermes Voice", "No Connection ❌", f"Cannot reach {SERVER_URL}")

    def _quit(self, sender):
        import rumps
        rumps.quit_application()

    # — Run ————————————————————————————————————————
    def run(self):
        self.app.run()


def check_deps():
    missing = []
    for mod, pkg in [("rumps", "rumps"), ("sounddevice", "sounddevice"),
                      ("pynput", "pynput"), ("requests", "requests")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Missing packages: {' '.join(missing)}")
        print(f"Install: pip3 install {' '.join(missing)}")
        sys.exit(1)


if __name__ == "__main__":
    check_deps()
    app = HermesVoiceApp()
    app.run()
