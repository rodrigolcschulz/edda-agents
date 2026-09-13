import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.transcription import FasterWhisperTranscriptionTool


class FakeWhisperModel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def transcribe(self, audio_path: str, language: str | None = None):
        self.calls.append((audio_path, language))
        return (
            [SimpleNamespace(text=" Primeiro trecho "), SimpleNamespace(text="segundo trecho")],
            SimpleNamespace(language="pt", language_probability=0.97),
        )


def test_transcription_tool_returns_structured_transcript(tmp_path: Path) -> None:
    audio_path = tmp_path / "problem.wav"
    audio_path.write_bytes(b"fake audio")
    model = FakeWhisperModel()
    tool = FasterWhisperTranscriptionTool(model_factory=lambda *_: model)

    result = json.loads(tool(json.dumps({"audio_path": str(audio_path), "language": "pt"})))

    assert result == {
        "type": "transcript",
        "text": "Primeiro trecho segundo trecho",
        "language": "pt",
        "confidence": 0.97,
        "model": "small",
        "provider": "faster-whisper",
    }
    assert model.calls == [(str(audio_path), "pt")]


def test_transcription_tool_reuses_loaded_model(tmp_path: Path) -> None:
    audio_path = tmp_path / "problem.wav"
    audio_path.write_bytes(b"fake audio")
    created_models: list[FakeWhisperModel] = []

    def factory(*_: str) -> FakeWhisperModel:
        model = FakeWhisperModel()
        created_models.append(model)
        return model

    tool = FasterWhisperTranscriptionTool(model_factory=factory)
    argument = json.dumps({"audio_path": str(audio_path)})

    tool(argument)
    tool(argument)

    assert len(created_models) == 1
    assert len(created_models[0].calls) == 2


def test_transcription_tool_rejects_missing_audio_path() -> None:
    tool = FasterWhisperTranscriptionTool(model_factory=lambda *_: FakeWhisperModel())

    with pytest.raises(ValueError, match="audio_path"):
        tool(json.dumps({}))