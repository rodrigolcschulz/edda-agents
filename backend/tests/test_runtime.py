from app.graph.runtime import AgentRuntime
from app.graph.hello import OllamaModel, build_hello_graph
from app.observability.langfuse import LangfuseClient
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, AgentRule, ModelRouterDefinition, RuleStage, RunRequest, ToolDefinition
from app.tools.registry import ToolRegistry
from app.tools.sandbox import DockerToolSandbox, SandboxedTool


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


def test_runtime_can_use_an_injected_model_for_reflection() -> None:
    agent = AgentDefinition(id="support", name="Support", system_prompt="Help the user.")
    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        model=lambda prompt: f"model response: {prompt}",
    )

    response = runtime.run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="Explain memory"),
    )

    assert response.answer == "model response: System: Help the user.\nUser request: Explain memory"


def test_runtime_routes_models_from_agent_definition() -> None:
    agent = AgentDefinition(
        id="routed",
        name="Routed",
        system_prompt="Help the user.",
        model_router=ModelRouterDefinition(
            simple_model="cheap",
            complex_model="strong",
            complexity_threshold=10,
        ),
    )
    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        models={
            "cheap": lambda prompt: f"cheap: {prompt}",
            "strong": lambda prompt: f"strong: {prompt}",
        },
    )

    simple_response = runtime.run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="Hello"),
    )
    complex_response = runtime.run(
        agent,
        RunRequest(thread_id="thread-2", user_id="user-1", message="Explain this complex request"),
    )

    assert simple_response.answer.startswith("cheap:")
    assert complex_response.answer.startswith("strong:")


def test_runtime_loops_until_reflection_resolves_or_max_steps() -> None:
    agent = AgentDefinition(
        id="looping",
        name="Looping",
        system_prompt="Help the user.",
        tools=[ToolDefinition(name="echo", description="Returns a result")],
        max_steps=2,
    )
    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        continuation_policy=lambda _agent, loop_count, _answer: loop_count < 3,
    )
    runtime._tools.register("echo", lambda argument: f"result for {argument}")

    response = runtime.run(
        agent,
        RunRequest(thread_id="thread-1", user_id="user-1", message="Use echo for this request"),
    )

    assert response.status == "completed"
    assert [step.name for step in response.steps] == ["memory", "plan", "act", "reflect", "plan", "act", "reflect"]


def test_docker_tool_sandbox_disables_network_and_limits_resources(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return type("Completed", (), {"stdout": "sandboxed result\n"})()

    monkeypatch.setattr("app.tools.sandbox.subprocess.run", fake_run)

    result = DockerToolSandbox().execute(
        SandboxedTool(image="tool-image", command=("tool", "echo")),
        "untrusted input",
    )

    assert result == "sandboxed result"
    assert captured["command"] == (
        "docker", "run", "--rm", "--interactive", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "128m",
        "--cpus", "0.5", "--user", "65534:65534", "tool-image", "tool", "echo",
    )
    assert captured["kwargs"] == {
        "input": '{"argument": "untrusted input"}',
        "text": True,
        "capture_output": True,
        "check": True,
        "timeout": 10.0,
    }


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


def test_langgraph_records_generation_when_langfuse_is_configured(monkeypatch) -> None:
    captured: list[dict[str, str]] = []
    tracer = LangfuseClient(public_key="public", secret_key="secret")
    monkeypatch.setattr(
        tracer,
        "record_generation",
        lambda **fields: captured.append(fields) or "generation-id",
    )

    result = build_hello_graph(model=lambda message: "answer", tracer=tracer).invoke({"message": "hello"})

    assert result["response"] == "answer"
    assert captured[0]["name"] == "hello-llm"
    assert captured[0]["input_text"] == "hello"
