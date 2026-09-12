from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


WorkflowNodeKind = Literal["agent"]


class WorkflowNode(BaseModel):
    id: str
    kind: WorkflowNodeKind
    agent_id: str
    input_mapping: dict[str, str] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    source_node_id: str
    target_node_id: str


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    version: int = Field(default=1, ge=1)
    nodes: list[WorkflowNode] = Field(min_length=1)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    entry_node: str
    output_node: str


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    content: Any
    source_node_id: str | None = None


class NodeRun(BaseModel):
    workflow_run_id: str
    node_id: str
    agent_run_id: str
    status: str
    model_name: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float | None = None
    cost_currency: str | None = None
    duration_ms: float = 0
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    trace_id: str


class WorkflowRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    workflow_version: int = 1
    status: str
    input: dict[str, Any]
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    current_node: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    node_runs: list[NodeRun] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float | None = 0
    cost_currency: str | None = "USD"
    models_used: list[str] = Field(default_factory=list)
    duration_ms: float = 0
    output_artifact_id: str | None = None
    error: str | None = None


class WorkflowRunResponse(BaseModel):
    run: WorkflowRun
    output: Artifact


class WorkflowExecutionRequest(BaseModel):
    workflow: WorkflowDefinition
    input: dict[str, Any]
    user_id: str = "workflow-user"
