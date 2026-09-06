from app.graph.runtime import AgentRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, AgentRule, RuleStage, RunRequest, ToolDefinition
from app.tools.registry import ToolRegistry


def make_runtime() -> AgentRuntime:
    tools = ToolRegistry()
    tools.register("echo", lambda argument: f"result for {argument}")
    return AgentRuntime(tools=tools, memory=InMemoryStore())


def test_runs_plan_act_reflect_cycle() -> None:
    agent = AgentDefinition(
        id="support",
        name="Support",
        system_prompt="Help the user.",
        tools=[ToolDefinition(name="echo", description="Returns a result")],
    )
    response = make_runtime().run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="Use echo for this request"),
    )

    assert response.status == "completed"
    assert response.answer == "Support: result for Use echo for this request"
    assert [step.name for step in response.steps] == ["memory", "plan", "act", "reflect"]


def test_input_rule_blocks_before_execution() -> None:
    agent = AgentDefinition(
        id="guarded",
        name="Guarded",
        system_prompt="Help safely.",
        rules=[AgentRule(name="no-secret", stage=RuleStage.INPUT, blocked_terms=["secret"])],
    )
    response = make_runtime().run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="My secret is exposed"),
    )

    assert response.status == "blocked"
    assert response.steps == []


def test_remembers_thread_context() -> None:
    agent = AgentDefinition(id="memory", name="Memory", system_prompt="Remember context.")
    runtime = make_runtime()

    runtime.run(agent, RunRequest(thread_id="thread-1", user_id="user-1", message="My name is Ana"))
    response = runtime.run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="What did I say?"),
    )

    assert response.memories_used == ["My name is Ana"]
