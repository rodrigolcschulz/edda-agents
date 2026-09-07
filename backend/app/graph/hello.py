from collections.abc import Callable
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.observability.langfuse import LangfuseClient


class HelloState(TypedDict, total=False):
    message: str
    response: str


Model = Callable[[str], str]


class OllamaModel:
    def __init__(self, model: str = "qwen3:14b", base_url: str | None = None, timeout: float = 120.0) -> None:
        self.model = model
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout

    def __call__(self, message: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": message}],
                "stream": False,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError(f"Ollama request failed for model '{self.model}'.") from error

        try:
            return result["message"]["content"]
        except (KeyError, TypeError) as error:
            raise RuntimeError("Ollama returned an invalid chat response.") from error


def deterministic_model(message: str) -> str:
    """Development model used to exercise graph execution without credentials."""
    return f"Deterministic response: {message}"


def build_hello_graph(model: Model = deterministic_model, tracer: LangfuseClient | None = None):
    def llm_node(state: HelloState) -> HelloState:
        response = model(state["message"])
        if tracer:
            tracer.record_generation(
                name="hello-llm",
                input_text=state["message"],
                output_text=response,
                model=getattr(model, "model", "custom"),
            )
        return {"response": response}

    graph = StateGraph(HelloState)
    graph.add_node("llm", llm_node)
    graph.add_edge(START, "llm")
    graph.add_edge("llm", END)
    return graph.compile()