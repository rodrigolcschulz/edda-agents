from dataclasses import dataclass
from collections.abc import Callable
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.graph.builder import ContinuationPolicy, GraphBuilder, Model
from app.graph.hello import ModelResponse
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RunRequest, RunResponse, ToolDefinition
from app.observability.langfuse import LangfuseClient
from app.observability.pricing import estimate_cost, pricing_for, pricing_version
from app.observability.runs import RunStore
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
        tracer: LangfuseClient | None = None,
        run_store: RunStore | None = None,
    ) -> None:
        self._tools = tools
        self._memory = memory
        self._model = model
        self._models = models
        self._continuation_policy = continuation_policy or self._is_resolved
        self._checkpointer = checkpointer
        self._tracer = tracer
        self._run_store = run_store

    def set_checkpointer(self, checkpointer: Any | None) -> None:
        self._checkpointer = checkpointer

    def set_run_store(self, run_store: RunStore | None) -> None:
        self._run_store = run_store

    def run(self, agent: AgentDefinition, request: RunRequest) -> RunResponse:
        run_id = str(uuid4())
        trace_id = str(uuid4())
        if self._run_store:
            self._run_store.start(agent, request, run_id, trace_id)
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
        started_at = perf_counter()
        try:
            result = graph.invoke(
                {"request": request, "steps": [], "loop_count": 0},
                {"configurable": {"thread_id": request.thread_id}},
            )
        except Exception as error:
            if self._run_store:
                self._run_store.fail(run_id, error, (perf_counter() - started_at) * 1000)
            raise
        duration_ms = (perf_counter() - started_at) * 1000
        usage = result.get("model_usage", {})
        input_tokens = usage.get("input", 0)
        output_tokens = usage.get("output", 0)
        model_name = result.get("model_name", agent.model)
        pricing = pricing_for(model_name)
        estimated_cost = estimate_cost(model_name, input_tokens, output_tokens)
        response = RunResponse(
            thread_id=request.thread_id,
            run_id=run_id,
            trace_id=trace_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model_name=model_name,
            estimated_cost=float(estimated_cost) if estimated_cost is not None else None,
            cost_currency=pricing.currency if pricing else None,
            answer=result["answer"],
            status=result["status"],
            steps=result.get("steps", []),
            memories_used=result.get("memories", []),
        )
        if self._run_store:
            self._run_store.finish(
                response,
                agent,
                duration_ms,
                [step.model_dump(mode="json") for step in response.steps],
            )
        if self._tracer:
            try:
                self._tracer.record_generation(
                    name="agent-runtime",
                    input_text=request.message,
                    output_text=response.answer,
                    model=model_name,
                    trace_id=trace_id,
                    duration_ms=duration_ms,
                    usage=usage,
                    metadata={
                        "run_id": run_id,
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "thread_id": request.thread_id,
                        "pricing_version": pricing_version(),
                    },
                    cost=float(estimated_cost) if estimated_cost is not None else None,
                )
            except RuntimeError:
                pass
        return response

    def _plan(self, agent: AgentDefinition, message: str) -> Plan:
        message_lower = message.casefold()
        for tool in agent.tools:
            if tool.name.casefold() in message_lower:
                return Plan(tool_name=tool.name, reason=f"Use requested tool '{tool.name}'.", tool=tool)
        return Plan(tool_name=None, reason="Answer without a tool.")

    @staticmethod
    def _reflect(agent: AgentDefinition, result: str, memories: list[str], model: Model | None) -> str | ModelResponse:
        context = f" Previous context: {' | '.join(memories)}." if memories else ""
        if model:
            prompt = f"System: {agent.system_prompt}\nUser request: {result}{context}"
            generate = getattr(model, "generate", None)
            if generate:
                return generate(prompt)
            return model(prompt)
        return f"{agent.name}: {result}{context}"

    @staticmethod
    def _is_resolved(agent: AgentDefinition, loop_count: int, answer: str) -> bool:
        return False