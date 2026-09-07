from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.guardrails.rules import RuleViolation, enforce_rules
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RuleStage, RunRequest, RunStep
from app.tools.registry import ToolRegistry


Model = Callable[[str], str]
Planner = Callable[[AgentDefinition, str], Any]
Reflector = Callable[[AgentDefinition, str, list[str], Model | None], str]
ContinuationPolicy = Callable[[AgentDefinition, int, str], bool]


class AgentGraphState(TypedDict, total=False):
    request: RunRequest
    memories: list[str]
    plan: Any
    result: str
    answer: str
    status: str
    steps: list[RunStep]
    model: Model | None
    loop_count: int
    should_continue: bool


class GraphBuilder:
    def __init__(
        self,
        tools: ToolRegistry,
        memory: InMemoryStore,
        planner: Planner,
        reflector: Reflector,
        continuation_policy: ContinuationPolicy,
        default_model: Model | None = None,
        models: dict[str, Model] | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._tools = tools
        self._memory = memory
        self._planner = planner
        self._reflector = reflector
        self._continuation_policy = continuation_policy
        self._default_model = default_model
        self._models = models or {}
        self._checkpointer = checkpointer

    def build(self, agent: AgentDefinition):
        def input_guardrail(state: AgentGraphState) -> AgentGraphState:
            try:
                enforce_rules(state["request"].message, agent.rules, RuleStage.INPUT)
            except RuleViolation as error:
                return {"answer": str(error), "status": "blocked"}
            return {}

        def recall_memory(state: AgentGraphState) -> AgentGraphState:
            request = state["request"]
            memories = self._memory.recall(request.thread_id, request.user_id)
            return {"memories": memories, "steps": [*state["steps"], RunStep(name="memory", detail=f"Recalled {len(memories)} item(s).")]}

        def plan(state: AgentGraphState) -> AgentGraphState:
            execution_plan = self._planner(agent, state["request"].message)
            return {
                "plan": execution_plan,
                "result": state["request"].message,
                "steps": [*state["steps"], RunStep(name="plan", detail=execution_plan.reason)],
            }

        def request_confirmation(state: AgentGraphState) -> AgentGraphState:
            tool = state["plan"].tool
            return {
                "answer": f"Confirmation required for tool '{tool.name}'.",
                "status": "confirmation_required",
                "steps": [*state["steps"], RunStep(name="confirmation", detail=f"Confirmation required for tool '{tool.name}'.")],
            }

        def act(state: AgentGraphState) -> AgentGraphState:
            tool_name = state["plan"].tool_name
            result = self._tools.execute(tool_name, state["request"].message)
            return {"result": result, "steps": [*state["steps"], RunStep(name="act", detail=f"Executed tool '{tool_name}'.")]}

        def route_model(state: AgentGraphState) -> AgentGraphState:
            model_name = agent.model
            if agent.model_router:
                model_name = (
                    agent.model_router.complex_model
                    if len(state["result"]) >= agent.model_router.complexity_threshold
                    else agent.model_router.simple_model
                )
            return {"model": self._models.get(model_name, self._default_model)}

        def reflect(state: AgentGraphState) -> AgentGraphState:
            answer = self._reflector(agent, state["result"], state["memories"], state.get("model"))
            loop_count = state["loop_count"] + 1
            return {
                "answer": answer,
                "status": "completed",
                "loop_count": loop_count,
                "should_continue": self._continuation_policy(agent, loop_count, answer),
                "steps": [*state["steps"], RunStep(name="reflect", detail="Produced final response.")],
            }

        def output_guardrail(state: AgentGraphState) -> AgentGraphState:
            try:
                enforce_rules(state["answer"], agent.rules, RuleStage.OUTPUT)
            except RuleViolation as error:
                return {"answer": str(error), "status": "blocked"}
            return {}

        def persist_memory(state: AgentGraphState) -> AgentGraphState:
            request = state["request"]
            self._memory.remember_message(request.thread_id, request.user_id, request.message)
            return {}

        def after_input_guardrail(state: AgentGraphState) -> str:
            return END if state.get("status") == "blocked" else "memory"

        def after_plan(state: AgentGraphState) -> str:
            execution_plan = state["plan"]
            if not execution_plan.tool_name:
                return "model_router"
            if execution_plan.tool and execution_plan.tool.requires_confirmation and not self._is_confirmed(
                execution_plan.tool.name, state["request"].confirmed_tools
            ):
                return "confirmation"
            return "act"

        def after_output_guardrail(state: AgentGraphState) -> str:
            return "persist" if state["status"] == "completed" else END

        def after_reflect(state: AgentGraphState) -> str:
            if state["should_continue"] and state["loop_count"] < agent.max_steps:
                return "plan"
            return "output_guardrail"

        graph = StateGraph(AgentGraphState)
        graph.add_node("input_guardrail", input_guardrail)
        graph.add_node("memory", recall_memory)
        graph.add_node("plan", plan)
        graph.add_node("confirmation", request_confirmation)
        graph.add_node("act", act)
        graph.add_node("model_router", route_model)
        graph.add_node("reflect", reflect)
        graph.add_node("output_guardrail", output_guardrail)
        graph.add_node("persist", persist_memory)
        graph.add_edge(START, "input_guardrail")
        graph.add_conditional_edges("input_guardrail", after_input_guardrail)
        graph.add_edge("memory", "plan")
        graph.add_conditional_edges("plan", after_plan)
        graph.add_edge("confirmation", END)
        graph.add_edge("act", "model_router")
        graph.add_edge("model_router", "reflect")
        graph.add_conditional_edges("reflect", after_reflect)
        graph.add_conditional_edges("output_guardrail", after_output_guardrail)
        graph.add_edge("persist", END)
        return graph.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _is_confirmed(tool_name: str, confirmed_tools: list[str]) -> bool:
        return any(tool_name.casefold() == confirmed.casefold() for confirmed in confirmed_tools)