from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RuleStage(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class AgentRule(BaseModel):
    name: str
    stage: RuleStage
    blocked_terms: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    name: str
    description: str
    requires_confirmation: bool = False


class McpServerDefinition(BaseModel):
    name: str
    command: str
    allowed_tools: list[str] = Field(default_factory=list)


class ModelRouterDefinition(BaseModel):
    simple_model: str
    complex_model: str
    complexity_threshold: int = Field(default=120, ge=1)


class AgentDefinition(BaseModel):
    id: str
    name: str
    system_prompt: str
    model: str = "local-deterministic"
    model_router: ModelRouterDefinition | None = None
    tools: list[ToolDefinition] = Field(default_factory=list)
    rules: list[AgentRule] = Field(default_factory=list)
    mcp_servers: list[McpServerDefinition] = Field(default_factory=list)
    max_steps: int = Field(default=3, ge=1, le=10)


class RunRequest(BaseModel):
    thread_id: str
    user_id: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    confirmed_tools: list[str] = Field(default_factory=list)


class RunStep(BaseModel):
    name: str
    detail: str


class RunResponse(BaseModel):
    thread_id: str
    answer: str
    status: str
    steps: list[RunStep]
    memories_used: list[str] = Field(default_factory=list)