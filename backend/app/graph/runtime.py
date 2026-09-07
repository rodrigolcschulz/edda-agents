from dataclasses import dataclass
from collections.abc import Callable

from app.guardrails.rules import RuleViolation, enforce_rules
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RuleStage, RunRequest, RunResponse, RunStep, ToolDefinition
from app.tools.registry import ToolRegistry


@dataclass
class Plan:
    tool_name: str | None
    reason: str
    tool: ToolDefinition | None = None


class AgentRuntime:
    def __init__(self, tools: ToolRegistry, memory: InMemoryStore, model: Callable[[str], str] | None = None) -> None:
        self._tools = tools
        self._memory = memory
        self._model = model

    def run(self, agent: AgentDefinition, request: RunRequest) -> RunResponse:
        steps: list[RunStep] = []
        try:
            enforce_rules(request.message, agent.rules, RuleStage.INPUT)
        except RuleViolation as error:
            return RunResponse(thread_id=request.thread_id, answer=str(error), status="blocked", steps=steps)

        memories = self._memory.recall(request.thread_id, request.user_id)
        steps.append(RunStep(name="memory", detail=f"Recalled {len(memories)} item(s)."))
        plan = self._plan(agent, request.message)
        steps.append(RunStep(name="plan", detail=plan.reason))

        result = request.message
        if plan.tool_name:
            if plan.tool and plan.tool.requires_confirmation and not self._is_confirmed(
                plan.tool.name, request.confirmed_tools
            ):
                steps.append(RunStep(name="confirmation", detail=f"Confirmation required for tool '{plan.tool.name}'."))
                return RunResponse(
                    thread_id=request.thread_id,
                    answer=f"Confirmation required for tool '{plan.tool.name}'.",
                    status="confirmation_required",
                    steps=steps,
                    memories_used=memories,
                )
            result = self._tools.execute(plan.tool_name, request.message)
            steps.append(RunStep(name="act", detail=f"Executed tool '{plan.tool_name}'."))

        answer = self._reflect(agent, result, memories)
        steps.append(RunStep(name="reflect", detail="Produced final response."))
        try:
            enforce_rules(answer, agent.rules, RuleStage.OUTPUT)
        except RuleViolation as error:
            return RunResponse(thread_id=request.thread_id, answer=str(error), status="blocked", steps=steps, memories_used=memories)

        self._memory.remember_message(request.thread_id, request.user_id, request.message)
        return RunResponse(thread_id=request.thread_id, answer=answer, status="completed", steps=steps, memories_used=memories)

    def _plan(self, agent: AgentDefinition, message: str) -> Plan:
        message_lower = message.casefold()
        for tool in agent.tools:
            if tool.name.casefold() in message_lower:
                return Plan(tool_name=tool.name, reason=f"Use requested tool '{tool.name}'.", tool=tool)
        return Plan(tool_name=None, reason="Answer without a tool.")

    @staticmethod
    def _is_confirmed(tool_name: str, confirmed_tools: list[str]) -> bool:
        return any(tool_name.casefold() == confirmed.casefold() for confirmed in confirmed_tools)

    def _reflect(self, agent: AgentDefinition, result: str, memories: list[str]) -> str:
        context = f" Previous context: {' | '.join(memories)}." if memories else ""
        if self._model:
            prompt = f"System: {agent.system_prompt}\nUser request: {result}{context}"
            return self._model(prompt)
        return f"{agent.name}: {result}{context}"