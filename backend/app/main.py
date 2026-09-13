from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.agents.store import AgentDraftStore
from app.graph.checkpoint import PostgresCheckpointer
from app.graph.hello import OpenAIModel, OllamaModel, deterministic_model
from app.graph.runtime import AgentRuntime
from app.graph.workflow import WorkflowRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, DraftResponse, DraftSummary, RunRequest, RunResponse
from app.models.workflow import WorkflowExecutionRequest, WorkflowRunResponse
from app.observability.langfuse import LangfuseClient
from app.observability.runs import RunStore
from app.tools.registry import ToolRegistry
from app.tools.sandbox import SandboxedTool
from app.tools.transcription import FasterWhisperTranscriptionTool
from app.models.workflow import WorkflowDefinition, WorkflowDraftResponse, WorkflowSummary
from app.workflows.store import WorkflowDefinitionStore

checkpointer: PostgresCheckpointer | None = None
draft_store: AgentDraftStore | None = None
run_store: RunStore | None = None
workflow_store: WorkflowDefinitionStore | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global checkpointer, draft_store, run_store, workflow_store
    database_url = os.getenv("DATABASE_URL")
    draft_store = AgentDraftStore(database_url)
    draft_store.setup()
    run_store = RunStore(database_url)
    run_store.setup()
    workflow_store = WorkflowDefinitionStore(database_url)
    workflow_store.setup()
    runtime.set_run_store(run_store)
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
    if run_store:
        run_store.close()
        run_store = None
        runtime.set_run_store(None)
    if workflow_store:
        workflow_store.close()
        workflow_store = None


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
tools.register(
    "transcribe",
    FasterWhisperTranscriptionTool(
        model_size=os.getenv("WHISPER_MODEL", "small"),
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
    ),
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


async def transcribe_upload(audio: UploadFile = File(...), language: str | None = Form(default=None)) -> dict[str, object]:
    filename = audio.filename or "audio"
    suffix = Path(filename).suffix.lower()
    allowed_types = {
        ".wav": {"audio/wav", "audio/x-wav", "audio/wave"},
        ".mp3": {"audio/mpeg", "audio/mp3"},
        ".ogg": {"audio/ogg", "application/ogg"},
        ".opus": {"audio/opus", "audio/ogg", "application/ogg"},
    }
    content_type = audio.content_type.split(";", 1)[0].strip().lower() if audio.content_type else None
    if suffix not in allowed_types or (content_type and content_type not in allowed_types[suffix]):
        raise HTTPException(status_code=415, detail="Only WAV, MP3, OGG, and Opus audio files are supported.")

    temporary_path: str | None = None
    total_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
            temporary_path = temporary_file.name
            while chunk := await audio.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > 25 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Audio file must be smaller than 25 MB.")
                temporary_file.write(chunk)

        argument = json.dumps({"audio_path": temporary_path, "language": language})
        result = tools.execute("transcribe", argument)
        return json.loads(result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        await audio.close()
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


app.post("/v1/tools/transcribe")(transcribe_upload)


def run_workflow(request: WorkflowExecutionRequest) -> WorkflowRunResponse:
    if draft_store is None:
        raise RuntimeError("Draft store is not initialized.")

    def resolve_agent(agent_id: str) -> AgentDefinition:
        saved = draft_store.get(agent_id)
        if saved is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Agent draft '{agent_id}' not found.")
        return saved[1]

    workflow_runtime = WorkflowRuntime(runtime, resolve_agent, run_store, tools)
    return workflow_runtime.run(request.workflow, request.input, request.user_id)


app.post("/v1/workflows/run", response_model=WorkflowRunResponse)(run_workflow)


def save_workflow(workflow: WorkflowDefinition) -> WorkflowDraftResponse:
    if workflow_store is None:
        raise RuntimeError("Workflow store is not initialized.")
    version = workflow_store.save(workflow)
    saved = workflow.model_copy(update={"version": version})
    return WorkflowDraftResponse(workflow=saved, version=version)


app.post("/v1/workflows", response_model=WorkflowDraftResponse)(save_workflow)


def list_workflows() -> list[WorkflowSummary]:
    if workflow_store is None:
        raise RuntimeError("Workflow store is not initialized.")
    return [WorkflowSummary(id=workflow_id, name=name, version=version) for workflow_id, name, version in workflow_store.list()]


app.get("/v1/workflows", response_model=list[WorkflowSummary])(list_workflows)


def get_workflow(workflow_id: str) -> WorkflowDraftResponse:
    if workflow_store is None:
        raise RuntimeError("Workflow store is not initialized.")
    saved = workflow_store.get(workflow_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    version, workflow = saved
    return WorkflowDraftResponse(workflow=workflow, version=version)


app.get("/v1/workflows/{workflow_id}", response_model=WorkflowDraftResponse)(get_workflow)


def delete_workflow(workflow_id: str) -> Response:
    if workflow_store is None:
        raise RuntimeError("Workflow store is not initialized.")
    if not workflow_store.delete(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.delete("/v1/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)(delete_workflow)


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


def delete_draft(agent_id: str) -> Response:
    if draft_store is None:
        raise RuntimeError("Draft store is not initialized.")
    if not draft_store.delete(agent_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Agent draft not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.delete("/v1/agents/drafts/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)(delete_draft)