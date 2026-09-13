from collections.abc import Callable, Iterator
import json
from pathlib import Path
from typing import Any


WhisperModelFactory = Callable[[str, str, str], Any]


class FasterWhisperTranscriptionTool:
    """Transcribes a local audio artifact through faster-whisper."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        model_factory: WhisperModelFactory | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model_factory = model_factory
        self._model: Any | None = None

    def __call__(self, argument: str) -> str:
        request = self._parse_request(argument)
        audio_path = Path(request["audio_path"])
        if not audio_path.is_file():
            raise ValueError(f"Audio file '{audio_path}' does not exist.")

        segments, info = self._get_model().transcribe(
            str(audio_path),
            language=request.get("language"),
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        result = {
            "type": "transcript",
            "text": text,
            "language": getattr(info, "language", request.get("language")),
            "confidence": getattr(info, "language_probability", None),
            "model": self.model_size,
            "provider": "faster-whisper",
        }
        return json.dumps(result, ensure_ascii=False)

    def _get_model(self) -> Any:
        if self._model is None:
            factory = self._model_factory or self._default_model_factory
            self._model = factory(self.model_size, self.device, self.compute_type)
        return self._model

    @staticmethod
    def _parse_request(argument: str) -> dict[str, Any]:
        try:
            request = json.loads(argument)
        except json.JSONDecodeError as error:
            raise ValueError("Transcription input must be valid JSON.") from error
        if not isinstance(request, dict) or not request.get("audio_path"):
            raise ValueError("Transcription input must include 'audio_path'.")
        return request

    @staticmethod
    def _default_model_factory(model_size: str, device: str, compute_type: str) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "Speech support is not installed. Install the optional dependency with 'pip install -e .[speech]'."
            ) from error
        return WhisperModel(model_size, device=device, compute_type=compute_type)
