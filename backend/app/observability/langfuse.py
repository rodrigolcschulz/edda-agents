import base64
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass
class EvalCase:
    name: str
    input_text: str
    expected_output: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    name: str
    input_text: str
    expected_output: str
    actual_output: str
    score: float
    passed: bool


@dataclass(frozen=True)
class RegressionReport:
    baseline_pass_rate: float
    current_pass_rate: float
    drop: float
    passed: bool


class AgentEvaluator:
    """Deterministic evaluator suitable for local regression checks."""

    def __init__(self, model: Callable[[str], str]) -> None:
        self._model = model

    def evaluate(self, cases: Sequence[EvalCase]) -> list[EvalResult]:
        results: list[EvalResult] = []
        for case in cases:
            actual = self._model(case.input_text)
            passed = self._matches(case, actual)
            results.append(
                EvalResult(
                    name=case.name,
                    input_text=case.input_text,
                    expected_output=case.expected_output,
                    actual_output=actual,
                    score=1.0 if passed else 0.0,
                    passed=passed,
                )
            )
        return results

    @staticmethod
    def pass_rate(results: Sequence[EvalResult]) -> float:
        if not results:
            return 0.0
        return sum(1 for result in results if result.passed) / len(results)

    @staticmethod
    def compare_to_baseline(
        baseline: Sequence[EvalResult],
        current: Sequence[EvalResult],
        max_drop: float = 0.0,
    ) -> RegressionReport:
        baseline_pass_rate = AgentEvaluator.pass_rate(baseline)
        current_pass_rate = AgentEvaluator.pass_rate(current)
        drop = baseline_pass_rate - current_pass_rate
        return RegressionReport(
            baseline_pass_rate=baseline_pass_rate,
            current_pass_rate=current_pass_rate,
            drop=drop,
            passed=drop <= max_drop,
        )

    @staticmethod
    def _matches(case: EvalCase, actual: str) -> bool:
        expected = case.expected_output.strip().casefold()
        normalized_actual = actual.strip().casefold()
        match = case.metadata.get("match", "exact")
        if match == "contains":
            return expected in normalized_actual
        if match == "not_contains":
            return expected not in normalized_actual
        if match != "exact":
            raise ValueError(f"Unsupported evaluation match mode: {match}")
        return normalized_actual == expected


def load_eval_cases(path: str | Path) -> list[EvalCase]:
    """Load a versioned evaluation dataset from a JSON array."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Evaluation dataset must be a JSON array.")
    return [EvalCase(**case) for case in payload]


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
        duration_ms: float | None = None,
        usage: dict[str, int] | None = None,
        metadata: dict[str, Any] | None = None,
        cost: float | None = None,
    ) -> str | None:
        if not self.enabled:
            return None

        end_time = datetime.now(UTC)
        start_time = end_time if duration_ms is None else end_time.fromtimestamp(end_time.timestamp() - duration_ms / 1000, UTC)
        generation_id = str(uuid4())
        body: dict[str, Any] = {
            "id": generation_id,
            "traceId": trace_id or str(uuid4()),
            "name": name,
            "input": input_text,
            "output": output_text,
            "model": model,
            "startTime": start_time.isoformat().replace("+00:00", "Z"),
            "endTime": end_time.isoformat().replace("+00:00", "Z"),
            "costDetails": {"total": cost} if cost is not None else {},
        }
        if usage:
            body["usage"] = {**usage, "total": sum(usage.values())}
        if metadata:
            body["metadata"] = metadata
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