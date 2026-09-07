from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from app.graph.builder import ContinuationPolicy, GraphBuilder, Model
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RunRequest, RunResponse, ToolDefinition
from app.tools.registry import ToolRegistry


@dataclass
class Plan:
    tool_name: str | None
    reason: str
    tool: ToolDefinition | None = None


class AgentRuntime:
    def __init__(
        self,
        tools: ToolRegistry,
        memory: InMemoryStore,
        model: Callable[[str], str] | None = None,
        models: dict[str, Model] | None = None,
        continuation_policy: ContinuationPolicy | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._tools = tools
        self._memory = memory
        self._model = model
        self._models = models
        self._continuation_policy = continuation_policy or self._is_resolved
        self._checkpointer = checkpointer

    def set_checkpointer(self, checkpointer: Any | None) -> None:
        self._checkpointer = checkpointer

    def run(self, agent: AgentDefinition, request: RunRequest) -> RunResponse:
        graph = GraphBuilder(
            tools=self._tools,
            memory=self._memory,
            planner=self._plan,
            reflector=self._reflect,
            continuation_policy=self._continuation_policy,
            default_model=self._model,
            models=self._models,
            checkpointer=self._checkpointer,
        ).build(agent)
        result = graph.invoke(
            {"request": request, "steps": [], "loop_count": 0},
            {"configurable": {"thread_id": request.thread_id}},
        )
        return RunResponse(
            thread_id=request.thread_id,
            answer=result["answer"],
            status=result["status"],
            steps=result.get("steps", []),
            memories_used=result.get("memories", []),
        )

    def _plan(self, agent: AgentDefinition, message: str) -> Plan:
        message_lower = message.casefold()
        for tool in agent.tools:
            if tool.name.casefold() in message_lower:
                return Plan(tool_name=tool.name, reason=f"Use requested tool '{tool.name}'.", tool=tool)
        return Plan(tool_name=None, reason="Answer without a tool.")

    @staticmethod
    def _reflect(agent: AgentDefinition, result: str, memories: list[str], model: Model | None) -> str:
        context = f" Previous context: {' | '.join(memories)}." if memories else ""
        if model:
            prompt = f"System: {agent.system_prompt}\nUser request: {result}{context}"
            return model(prompt)
        return f"{agent.name}: {result}{context}"

    @staticmethod
    def _is_resolved(agent: AgentDefinition, loop_count: int, answer: str) -> bool:
        return False