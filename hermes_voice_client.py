#!/usr/bin/env python3
"""Hermes Voice Client — Mac push-to-talk voice interface.
Press Ctrl+Shift+Space to talk. Release to send. Response plays through Mac speakers.

First-time setup:
    brew install portaudio ffmpeg
    pip3 install sounddevice pynput requests playsound3

To use: python3 hermes_voice_client.py
"""
import io
import sys
import time
import queue
import threading
import tempfile
from pathlib import Path

import requests
import sounddevice as sd
import numpy as np

# — Config ——————————————————————————————
SERVER_URL = "http://100.114.1.6:9120"  # Hermes server on Tailscale
HOTKEY = "<ctrl>+<shift>+<space>"  # pynput format
SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_TIMEOUT = 60  # max recording seconds

# — Audio capture ———————————————————————
class AudioRecorder:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.stream = None

    def start(self):
        self.frames = []
        self.recording = True
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=self._callback,
        )
        self.stream.start()
        print("🎤 Recording... (release key to send)")

    def stop(self) -> bytes:
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.frames:
            return b""

        audio = np.concatenate(self.frames, axis=0)
        # Save as WAV in memory
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        return buf.read()

    def _callback(self, indata, frames, time_info, status):
        if self.recording:
            self.frames.append(indata.copy())


# — Hotkey handling —————————————————————
def run():
    recorder = AudioRecorder()
    recording_lock = threading.Lock()
    is_recording = False

    def on_press(key):
        nonlocal is_recording
        with recording_lock:
            if not is_recording:
                is_recording = True
                recorder.start()

    def on_release(key):
        nonlocal is_recording
        with recording_lock:
            if is_recording:
                is_recording = False
                wav_bytes = recorder.stop()
                if len(wav_bytes) < 800:
                    print("⚠️  Recording too short — ignored")
                    return

                # Send to server
                print("📡 Sending to Hermes...")
                t0 = time.time()
                try:
                    resp = requests.post(
                        f"{SERVER_URL}/voice",
                        files={"audio": ("recording.wav", wav_bytes, "audio/wav")},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        print(f"✅ Response received ({time.time()-t0:.1f}s)")
                        _play_mp3(resp.content)
                    else:
                        print(f"❌ Server error: {resp.status_code} — {resp.text[:200]}")
                except requests.exceptions.ConnectionError:
                    print(f"❌ Cannot reach server at {SERVER_URL}")
                except Exception as e:
                    print(f"❌ Error: {e}")

    # Hotkey via pynput
    from pynput import keyboard

    # Use a global hotkey combo
    current_keys = set()

    def on_press_kb(key):
        try:
            current_keys.add(key)
        except:
            pass
        if keyboard.Key.ctrl in current_keys and keyboard.Key.shift in current_keys and keyboard.Key.space in current_keys:
            on_press(key)

    def on_release_kb(key):
        if keyboard.Key.ctrl in current_keys and keyboard.Key.shift in current_keys:
            on_release(key)
        try:
            current_keys.discard(key)
        except:
            pass

    print(f"🦞 Hermes Voice Client ready")
    print(f"   Hotkey: Ctrl+Shift+Space (push to talk)")
    print(f"   Server: {SERVER_URL}")
    print(f"   Mic:    {sd.query_devices(kind='input')['name'] if sd.query_devices(kind='input') else 'default'}")
    print(f"   Speaker: {sd.query_devices(kind='output')['name'] if sd.query_devices(kind='output') else 'default'}")
    print()

    with keyboard.Listener(on_press=on_press_kb, on_release=on_release_kb) as listener:
        listener.join()


def _play_mp3(mp3_bytes: bytes):
    """Play MP3 audio through system speakers."""
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        tmp = f.name
    try:
        # macOS: afplay
        subprocess.run(["afplay", tmp], check=True, timeout=60)
    except FileNotFoundError:
        # Linux fallback
        try:
            from playsound3 import playsound
            playsound(tmp)
        except ImportError:
            print("⚠️  Install playsound3: pip3 install playsound3")
    finally:
        Path(tmp).unlink(missing_ok=True)


if __name__ == "__main__":
    # Check deps
    try:
        import pynput
    except ImportError:
        print("Missing pynput. Install with: pip3 install pynput")
        sys.exit(1)

    try:
        import sounddevice
    except ImportError:
        print("Missing sounddevice. Install with: pip3 install sounddevice")
        sys.exit(1)

    run()
