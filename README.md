# Hermes Voice Client

Push-to-talk voice interface for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Lives in your Mac menu bar — no Dock icon, no window clutter.

<img src="https://img.shields.io/badge/platform-macOS%2012%2B-blue" alt="macOS 12+">
<img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">

## How It Works

```
Ctrl+Shift+Space (hold)  →  🟢 Mic captures audio
           ↓
         Release  →  🟡 WAV sent to Hermes server (Tailscale)
           ↓
Server: STT (Whisper) → LLM (Hermes) → TTS (ElevenLabs)
           ↓
         🟢  Response plays through Mac speakers
```

Menu bar icon shows status at a glance:
- 🔹 Idle (waiting for hotkey)
- 🟢 Recording (mic active)
- 🟡 Processing (Hermes thinking)
- 🔴 Error (connection lost)

## Quick Install (Mac)

### 1. Download
Get `HermesVoice.app.zip` from [Releases](https://github.com/the1nehq/hermes-voice-client/releases).

### 2. Install dependencies
```bash
brew install portaudio ffmpeg
pip3 install rumps sounddevice pynput requests
```

### 3. Run
Unzip, drag to `/Applications`. First launch: **right-click → Open** (unsigned app).

The app appears in your menu bar. Press **Ctrl+Shift+Space** to talk.

## Server Setup

`server.py` runs on your Hermes server:

```bash
pip install openai-whisper fastapi uvicorn
python3 server.py  # starts on :9120
```

Set `HERMES_VOICE_SERVER` env var if your server isn't at `100.114.1.6:9120`.

## Architecture

```
┌────────────────────┐        ┌───────────────────────┐
│   Mac Client       │  WAV   │   Hermes Server        │
│                    │───────▶│                       │
│ Menu bar app       │        │ :9120 Voice API        │
│ Ctrl+Shift+Space   │◀───────│  STT (Whisper)         │
│   → mic capture    │  MP3   │  LLM (Hermes CLI)      │
│   ← speaker play   │        │  TTS (ElevenLabs)      │
└────────────────────┘        └───────────────────────┘
         Tailscale                        Docker
```

## License

MIT
