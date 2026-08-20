from __future__ import annotations

import os
from pathlib import Path


class OpenAITranscriber:
    def __init__(self, client: object | None = None, model: str | None = None) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        self._client = client
        self._model = model or os.getenv("PEOPLE_MESSENGER_TRANSCRIBE_MODEL", "gpt-transcribe")

    def transcribe(self, audio_path: Path) -> str:
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        with audio_path.open("rb") as audio:
            result = self._client.audio.transcriptions.create(model=self._model, file=audio)
        text = getattr(result, "text", "").strip()
        if not text:
            raise RuntimeError("Transcription returned no text")
        return text
