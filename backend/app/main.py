from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.store import AgentDraftStore
from app.graph.checkpoint import PostgresCheckpointer
from app.graph.hello import OpenAIModel, OllamaModel, deterministic_model
from app.graph.runtime import AgentRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, DraftResponse, RunRequest, RunResponse
from app.models.agent import AgentDefinition, DraftResponse, DraftSummary, RunRequest, RunResponse
from app.observability.langfuse import LangfuseClient
from app.tools.registry import ToolRegistry
from app.tools.sandbox import SandboxedTool

checkpointer: PostgresCheckpointer | None = None
draft_store: AgentDraftStore | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global checkpointer, draft_store
    database_url = os.getenv("DATABASE_URL")
    draft_store = AgentDraftStore(database_url)
    draft_store.setup()
    if database_url:
        checkpointer = PostgresCheckpointer(database_url)
        checkpointer.setup()
        runtime.set_checkpointer(checkpointer.saver)
    yield
    if checkpointer:
        checkpointer.close()
        runtime.set_checkpointer(None)
        checkpointer = None
    if draft_store:
        draft_store.close()
        draft_store = None


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
runtime = AgentRuntime(
    tools=tools,
    memory=InMemoryStore(),
    model=OllamaModel(),
    models={
        "local-deterministic": deterministic_model,
        "qwen3:14b": OllamaModel("qwen3:14b"),
        "gpt-4o-mini": OpenAIModel("gpt-4o-mini"),
    },
    tracer=LangfuseClient(),
)


def health() -> dict[str, str]:
    return {"status": "ok"}


app.get("/health")(health)


def run_agent(agent: AgentDefinition, request: RunRequest) -> RunResponse:
    return runtime.run(agent, request)


app.post("/v1/agents/run", response_model=RunResponse)(run_agent)


def save_draft(agent: AgentDefinition) -> DraftResponse:
    if draft_store is None:
        raise RuntimeError("Draft store is not initialized.")
    return DraftResponse(agent=agent, version=draft_store.save(agent))


app.post("/v1/agents/drafts", response_model=DraftResponse)(save_draft)


def list_drafts() -> list[DraftSummary]:
    if draft_store is None:
        raise RuntimeError("Draft store is not initialized.")
    return [DraftSummary(id=agent_id, name=name, version=version) for agent_id, name, version in draft_store.list()]


app.get("/v1/agents/drafts", response_model=list[DraftSummary])(list_drafts)


def get_draft(agent_id: str) -> DraftResponse:
    if draft_store is None:
        raise RuntimeError("Draft store is not initialized.")
    saved = draft_store.get(agent_id)
    if saved is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Agent draft not found.")
    version, agent = saved
    return DraftResponse(agent=agent, version=version)


app.get("/v1/agents/drafts/{agent_id}", response_model=DraftResponse)(get_draft)