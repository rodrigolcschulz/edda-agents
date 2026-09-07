from app.graph.runtime import AgentRuntime
from app.graph.hello import OllamaModel, build_hello_graph
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


def test_requires_confirmation_before_sensitive_tool_execution() -> None:
    calls: list[str] = []
    tools = ToolRegistry()
    tools.register("delete", lambda argument: calls.append(argument) or "deleted")
    runtime = AgentRuntime(tools=tools, memory=InMemoryStore())
    agent = AgentDefinition(
        id="admin",
        name="Admin",
        system_prompt="Manage resources.",
        tools=[ToolDefinition(name="delete", description="Deletes a resource", requires_confirmation=True)],
    )

    response = runtime.run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="Please delete this", confirmed_tools=[]),
    )

    assert response.status == "confirmation_required"
    assert response.answer == "Confirmation required for tool 'delete'."
    assert calls == []


def test_thread_memory_isolated_between_users() -> None:
    runtime = make_runtime()
    agent = AgentDefinition(id="memory", name="Memory", system_prompt="Remember context.")

    runtime.run(agent, RunRequest(thread_id="shared", user_id="user-1", message="Private note"))
    response = runtime.run(agent, RunRequest(thread_id="shared", user_id="user-2", message="Hello"))

    assert response.memories_used == []


def test_langgraph_hello_runs_one_llm_node() -> None:
    graph = build_hello_graph(model=lambda message: f"model answer for: {message}")

    result = graph.invoke({"message": "hello"})

    assert result["response"] == "model answer for: hello"


def test_ollama_model_parses_chat_response(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"message":{"content":"local answer"}}'

    monkeypatch.setattr("app.graph.hello.urlopen", lambda *args, **kwargs: FakeResponse())

    assert OllamaModel(model="qwen3:14b")("hello") == "local answer"
