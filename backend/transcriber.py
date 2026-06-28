"""
Audio transcription using local Whisper (tiny model for speed).
Downloads audio from a URL (Twilio media URL) and transcribes it.
"""

import os
import tempfile
import urllib.request
import whisper
from pathlib import Path

# Lazy-loaded model
_model = None


def get_model():
    global _model
    if _model is None:
        _model = whisper.load_model("tiny")
    return _model


def transcribe_audio_file(audio_path: str) -> str:
    """Transcribe a local audio file to German text."""
    model = get_model()
    result = model.transcribe(audio_path, language="de")
    return result["text"].strip()


def download_and_transcribe(media_url: str) -> str:
    """Download audio from a URL and transcribe it."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        tmp_path = f.name

    try:
        urllib.request.urlretrieve(media_url, tmp_path)
        text = transcribe_audio_file(tmp_path)
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def transcribe_text(text: str) -> str:
    """Pass-through for text input (already transcribed by WhatsApp)."""
    return text.strip()