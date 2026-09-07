from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.graph.checkpoint import PostgresCheckpointer
from app.graph.hello import OllamaModel
from app.graph.runtime import AgentRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RunRequest, RunResponse
from app.tools.registry import ToolRegistry
from app.tools.sandbox import SandboxedTool

checkpointer: PostgresCheckpointer | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global checkpointer
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        checkpointer = PostgresCheckpointer(database_url)
        checkpointer.setup()
        runtime.set_checkpointer(checkpointer.saver)
    yield
    if checkpointer:
        checkpointer.close()
        runtime.set_checkpointer(None)
        checkpointer = None


app = FastAPI(title="AgentForge API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
tools = ToolRegistry()
tools.register_sandboxed(
    "echo",
    SandboxedTool(image="edda-agents-tool-runner", command=("python", "/runner/runner.py", "echo")),
)
runtime = AgentRuntime(tools=tools, memory=InMemoryStore(), model=OllamaModel())


def health() -> dict[str, str]:
    return {"status": "ok"}


app.get("/health")(health)


def run_agent(agent: AgentDefinition, request: RunRequest) -> RunResponse:
    return runtime.run(agent, request)


app.post("/v1/agents/run", response_model=RunResponse)(run_agent)