import base64
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class LangfuseClient:
    """Small dependency-free Langfuse ingestion client.

    Tracing is disabled when public and secret keys are absent, which keeps local
    unit tests and deterministic development runs independent of infrastructure.
    """

    def __init__(
        self,
        host: str | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.host = (host or os.getenv("LANGFUSE_HOST", "http://localhost:3000")).rstrip("/")
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.public_key and self.secret_key)

    def record_generation(
        self,
        *,
        name: str,
        input_text: str,
        output_text: str,
        model: str,
        trace_id: str | None = None,
    ) -> str | None:
        if not self.enabled:
            return None

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        generation_id = str(uuid4())
        body: dict[str, Any] = {
            "id": generation_id,
            "traceId": trace_id or str(uuid4()),
            "name": name,
            "input": input_text,
            "output": output_text,
            "model": model,
            "startTime": now,
            "endTime": now,
        }
        payload = json.dumps({"batch": [{"type": "generation-create", "body": body}]}).encode("utf-8")
        credentials = base64.b64encode(f"{self.public_key}:{self.secret_key}".encode("utf-8")).decode("ascii")
        request = Request(
            f"{self.host}/api/public/ingestion",
            data=payload,
            headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout):
                return generation_id
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError("Langfuse ingestion request failed.") from error