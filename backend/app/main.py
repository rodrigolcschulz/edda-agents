from fastapi import FastAPI

from app.graph.runtime import AgentRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RunRequest, RunResponse
from app.tools.registry import ToolRegistry

app = FastAPI(title="AgentForge API", version="0.1.0")
tools = ToolRegistry()
tools.register("echo", lambda argument: f"Tool result: {argument}")
runtime = AgentRuntime(tools=tools, memory=InMemoryStore())


def health() -> dict[str, str]:
    return {"status": "ok"}


app.get("/health")(health)


def run_agent(agent: AgentDefinition, request: RunRequest) -> RunResponse:
    return runtime.run(agent, request)


app.post("/v1/agents/run", response_model=RunResponse)(run_agent)