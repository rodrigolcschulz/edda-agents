from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.graph.hello import OllamaModel
from app.graph.runtime import AgentRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RunRequest, RunResponse
from app.tools.registry import ToolRegistry

app = FastAPI(title="AgentForge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
tools = ToolRegistry()
tools.register("echo", lambda argument: f"Tool result: {argument}")
runtime = AgentRuntime(tools=tools, memory=InMemoryStore(), model=OllamaModel())


def health() -> dict[str, str]:
    return {"status": "ok"}


app.get("/health")(health)


def run_agent(agent: AgentDefinition, request: RunRequest) -> RunResponse:
    return runtime.run(agent, request)


app.post("/v1/agents/run", response_model=RunResponse)(run_agent)