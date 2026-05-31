# Hermes Voice Client

Push-to-talk voice interface for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Mac client captures mic on hotkey, sends to Hermes server for STT→LLM→TTS, plays response through speakers.

## Architecture

```
┌──────────────────┐        ┌───────────────────────┐
│   Mac Client     │  WAV   │   Hermes Server        │
│                  │───────▶│                       │
│ Ctrl+Shift+Space │        │ :9120 Voice API        │
│   → mic capture  │◀───────│  STT (Whisper)         │
│   ← speaker out  │  MP3   │  LLM (Hermes CLI)      │
│                  │        │  TTS (ElevenLabs)      │
└──────────────────┘        └───────────────────────┘
```

- **Mic active only while hotkey held** — does not block system audio or voice calls
- Response latency ~7 seconds (STT + LLM + TTS)
- German voice support via ElevenLabs

## Setup (Mac)

### 1. Install dependencies
```bash
brew install portaudio ffmpeg
pip3 install sounddevice pynput requests
```

### 2. Download client
```bash
curl -o hermes_voice_client.py https://raw.githubusercontent.com/the1nehq/hermes-voice-client/main/hermes_voice_client.py
```

### 3. Run
```bash
python3 hermes_voice_client.py
```

Set `SERVER_URL` in the script if your Hermes server is not at `100.114.1.6:9120`.

## Server Setup

The `server.py` runs on your Hermes server:

```bash
pip install openai-whisper fastapi uvicorn
python3 server.py  # starts on :9120
```

A systemd service file is recommended for production.

## License

MIT
