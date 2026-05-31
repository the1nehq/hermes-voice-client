#!/usr/bin/env python3
"""Hermes Voice API — accept audio, transcribe, run through Hermes, return TTS.
Runs on the server, called by Mac voice client.
"""
import io
import os
import sys
import tempfile
import shutil
import subprocess
import hashlib
import time
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
AUDIO_SERVE = HERMES_HOME / "audio_serve"
AUDIO_CACHE = HERMES_HOME / "audio_cache"
VENV_PYTHON = str(HERMES_HOME / "hermes-agent/venv/bin/python3")
HERMES_BIN = str(HERMES_HOME / "hermes-agent/venv/bin/hermes")

AUDIO_SERVE.mkdir(parents=True, exist_ok=True)
AUDIO_CACHE.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Hermes Voice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcribe audio using openai-whisper (already installed)."""
    import whisper
    # Save to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        model = whisper.load_model("base")
        result = model.transcribe(tmp_path, language="de")
        text = result["text"].strip()
        return text
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def text_to_speech_elevenlabs(text: str) -> bytes:
    """Generate TTS using ElevenLabs API (matches Hermes config)."""
    # Read API key from .env
    env_file = HERMES_HOME / ".env"
    api_key = None
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY=") and len(line) > 20:
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not found in .env")

    # Read voice_id from config
    import yaml
    config = yaml.safe_load((HERMES_HOME / "config.yaml").read_text())
    voice_id = config.get("tts", {}).get("elevenlabs", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB")
    model_id = config.get("tts", {}).get("elevenlabs", {}).get("model_id", "eleven_multilingual_v2")

    import requests
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs TTS failed: {resp.status_code} {resp.text[:200]}")
    return resp.content


def ogg_to_mp3(ogg_bytes: bytes) -> bytes:
    """Convert OGG audio to MP3 using ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f_in:
        f_in.write(ogg_bytes)
        ogg_path = f_in.name

    mp3_path = ogg_path.replace(".ogg", ".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", ogg_path, "-acodec", "libmp3lame", "-ab", "128k", mp3_path],
            capture_output=True, timeout=15, check=True
        )
        return Path(mp3_path).read_bytes()
    finally:
        Path(ogg_path).unlink(missing_ok=True)
        Path(mp3_path).unlink(missing_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-voice-api"}


@app.post("/voice")
async def voice_to_voice(audio: UploadFile = File(...)):
    """
    Receive audio → transcribe → Hermes LLM → TTS → return MP3.
    """
    audio_bytes = await audio.read()
    if len(audio_bytes) < 800:
        return Response(status_code=400, content="Audio too short")

    t_start = time.time()

    # 1. STT
    try:
        text = transcribe_audio(audio_bytes)
    except Exception as e:
        return Response(status_code=500, content=f"STT failed: {e}")

    if not text or len(text) < 2:
        return Response(status_code=422, content="No speech detected")

    print(f"[voice-api] Transcribed ({time.time()-t_start:.1f}s): {text[:100]}")

    # 2. Hermes LLM (resume last session for continuity)
    try:
        result = subprocess.run(
            [HERMES_BIN, "chat", "-q", "-c", text],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": str(Path.home())},
        )
        response_text = result.stdout.strip()
        if not response_text and result.stderr:
            response_text = result.stderr.strip()
        # Clean ANSI escape codes
        import re
        response_text = re.sub(r'\x1b\[[0-9;]*m', '', response_text)
        response_text = response_text.strip()
    except subprocess.TimeoutExpired:
        response_text = "(Hermes did not respond in time)"
    except Exception as e:
        return Response(status_code=500, content=f"LLM call failed: {e}")

    if not response_text:
        response_text = "(Hermes gave no response)"

    print(f"[voice-api] Hermes response ({time.time()-t_start:.1f}s): {response_text[:100]}")

    # 3. TTS
    try:
        ogg_bytes = text_to_speech_elevenlabs(response_text)
    except Exception as e:
        return Response(status_code=500, content=f"TTS failed: {e}")

    # 4. Convert to MP3
    try:
        mp3_bytes = ogg_to_mp3(ogg_bytes)
    except Exception:
        # ffmpeg failed, fall back to OGG
        return Response(content=ogg_bytes, media_type="audio/ogg")

    print(f"[voice-api] Done in {time.time()-t_start:.1f}s")
    return Response(content=mp3_bytes, media_type="audio/mpeg")


@app.get("/")
async def root():
    return {"service": "Hermes Voice API", "endpoints": ["POST /voice", "GET /health"]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9120)
