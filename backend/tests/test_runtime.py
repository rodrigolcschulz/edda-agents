import json
import time
from pathlib import Path

from app.graph.runtime import AgentRuntime
from app.graph.hello import OpenAIModel, OllamaModel, build_hello_graph
from app.observability.langfuse import AgentEvaluator, EvalCase, LangfuseClient, load_eval_cases
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
    assert response.run_id
    assert response.trace_id
    assert response.model_name == "local-deterministic"
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


def test_runtime_accumulates_model_usage_across_reflection_cycles() -> None:
    agent = AgentDefinition(id="usage", name="Usage", system_prompt="Help.", max_steps=2)
    calls = 0

    def model(prompt: str):
        nonlocal calls
        calls += 1
        from app.graph.hello import ModelResponse

        return ModelResponse(content=f"answer {calls}", usage={"input": 10, "output": 4})

    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        model=model,
        continuation_policy=lambda _agent, loop_count, _answer: loop_count < 2,
    )

    response = runtime.run(agent, RunRequest(thread_id="usage", user_id="user-1", message="hello"))

    assert response.status == "completed"
    assert response.input_tokens == 20
    assert response.output_tokens == 8
    assert response.total_tokens == 28


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


def test_runtime_uses_retrieval_context_when_enabled() -> None:
    memory = InMemoryStore()
    memory.ingest_document("support-policy", "Refunds are processed in 5-7 business days.")
    runtime = AgentRuntime(tools=ToolRegistry(), memory=memory, model=lambda prompt: prompt)
    agent = AgentDefinition(
        id="rag",
        name="RAG",
        system_prompt="Use the support docs when relevant.",
        retrieval_enabled=True,
        retrieval_top_k=3,
    )

    response = runtime.run(
        agent,
        RunRequest(thread_id="thread-rag", user_id="user-1", message="When will my refund be processed?"),
    )

    assert "Refunds are processed in 5-7 business days." in response.answer


def test_long_term_memory_expires_and_searches_by_similarity() -> None:
    memory = InMemoryStore()
    memory.ingest_document("shipping", "Orders are shipped in 2-3 business days.")
    memory.remember_fact("user-1", "My favorite color is blue.")
    memory.remember_fact("user-1", "I live in São Paulo.", ttl_seconds=0.05)

    assert memory.search_documents("How long does shipping take?", limit=1)[0].text == "Orders are shipped in 2-3 business days."
    assert any("favorite color" in fact.lower() for fact in memory.search_facts("user-1", "What colors do I like?"))

    time.sleep(0.1)
    assert memory.search_facts("user-1", "Where do I live?") == []


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


def test_ollama_model_exposes_token_usage(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"message":{"content":"local answer"},"prompt_eval_count":11,"eval_count":7}'

    monkeypatch.setattr("app.graph.hello.urlopen", lambda *args, **kwargs: FakeResponse())

    response = OllamaModel(model="qwen3:14b").generate("hello")

    assert response.content == "local answer"
    assert response.usage == {"input": 11, "output": 7}


def test_openai_model_parses_chat_response_and_usage(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "simple answer"}}],
                    "usage": {"prompt_tokens": 13, "completion_tokens": 5},
                }
            ).encode()

    def fake_urlopen(request, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("app.graph.hello.urlopen", fake_urlopen)
    response = OpenAIModel(model="gpt-4o-mini", api_key="test-key").generate("hello")

    assert response.content == "simple answer"
    assert response.usage == {"input": 13, "output": 5}
    assert captured["kwargs"] == {"timeout": 120.0}
    assert captured["request"].full_url == "https://api.openai.com/v1/chat/completions"
    assert captured["request"].get_header("Authorization") == "Bearer test-key"


def test_langfuse_generation_includes_usage_and_duration(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, **kwargs):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("app.observability.langfuse.urlopen", fake_urlopen)
    tracer = LangfuseClient(host="http://langfuse", public_key="public", secret_key="secret")

    assert tracer.record_generation(
        name="agent-runtime",
        input_text="question",
        output_text="answer",
        model="qwen3:14b",
        duration_ms=25,
        usage={"input": 11, "output": 7},
    )
    body = captured["payload"]["batch"][0]["body"]
    assert body["usage"] == {"input": 11, "output": 7, "total": 18}
    assert body["costDetails"] == {"total": 0}
    assert body["startTime"] != body["endTime"]


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


def test_runtime_records_langfuse_trace_for_each_run(monkeypatch) -> None:
    captured: list[dict[str, str]] = []
    tracer = LangfuseClient(public_key="public", secret_key="secret")
    monkeypatch.setattr(
        tracer,
        "record_generation",
        lambda **fields: captured.append(fields) or "generation-id",
    )
    runtime = AgentRuntime(tools=ToolRegistry(), memory=InMemoryStore(), model=lambda prompt: f"final: {prompt}", tracer=tracer)

    response = runtime.run(
        AgentDefinition(id="trace", name="Trace", system_prompt="Be brief."),
        RunRequest(thread_id="t-1", user_id="u-1", message="hello"),
    )

    assert response.status == "completed"
    assert captured and captured[0]["name"] == "agent-runtime"
    assert "hello" in captured[0]["input_text"]
    assert captured[0]["trace_id"] == response.trace_id
    assert captured[0]["metadata"]["run_id"] == response.run_id
    assert captured[0]["metadata"]["agent_id"] == "trace"
    assert captured[0]["model"] == "local-deterministic"
    assert captured[0]["duration_ms"] >= 0


def test_agent_evaluator_scores_matches_and_reports_pass_rate() -> None:
    cases = [
        EvalCase(name="simple", input_text="hello", expected_output="hi"),
        EvalCase(name="complex", input_text="goodbye", expected_output="bye"),
    ]

    evaluator = AgentEvaluator(lambda prompt: "hi" if prompt == "hello" else "bye")
    results = evaluator.evaluate(cases)

    assert [item.passed for item in results] == [True, True]
    assert results[0].score == 1.0
    assert evaluator.pass_rate(results) == 1.0


def test_support_evaluation_dataset_is_versioned_and_loadable() -> None:
    dataset_path = Path(__file__).parents[1] / "evals" / "datasets" / "support.json"

    cases = load_eval_cases(dataset_path)

    assert len(cases) == 3
    assert cases[0].metadata["match"] == "contains"
    assert cases[1].metadata["category"] == "safety"
