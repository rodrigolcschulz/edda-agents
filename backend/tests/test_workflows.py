from app.graph.runtime import AgentRuntime
from app.graph.hello import ModelResponse
from app.graph.workflow import WorkflowRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition
from app.models.workflow import WorkflowDefinition, WorkflowEdge, WorkflowNode
from app.tools.registry import ToolRegistry


def test_runs_project_manager_then_data_architect() -> None:
    agents = {
        "project-manager": AgentDefinition(
            id="project-manager",
            name="Gerente de Projetos",
            system_prompt="Create a structured project backlog.",
        ),
        "data-architect": AgentDefinition(
            id="data-architect",
            name="Arquiteto de Dados",
            system_prompt="Create a technical ETL architecture from the project plan.",
        ),
    }
    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        model=lambda prompt: f"model output: {prompt}",
    )
    workflow_runtime = WorkflowRuntime(runtime, agents.__getitem__)
    workflow = WorkflowDefinition(
        id="sales-etl-planning",
        name="Planejamento do ETL de vendas",
        nodes=[
            WorkflowNode(id="project-plan", kind="agent", agent_id="project-manager"),
            WorkflowNode(
                id="architecture",
                kind="agent",
                agent_id="data-architect",
                input_mapping={"project_plan": "project-plan", "source_problem": "input"},
            ),
        ],
        edges=[WorkflowEdge(source_node_id="project-plan", target_node_id="architecture")],
        entry_node="project-plan",
        output_node="architecture",
    )

    result = workflow_runtime.run(
        workflow,
        {
            "problem": "Construir um pipeline diário de vendas a partir de CSVs.",
            "architecture_context": "Validar, deduplicar, enriquecer e carregar vendas aprovadas.",
        },
        user_id="user-1",
    )

    assert result.run.status == "completed"
    assert [node_run.node_id for node_run in result.run.node_runs] == ["project-plan", "architecture"]
    assert result.output.source_node_id == "architecture"
    assert "project_plan" in result.output.content
    assert "model output" in result.output.content
    assert len(result.run.artifacts) == 2
    assert result.run.workflow_version == 1
    assert result.run.trace_id
    assert result.run.total_tokens == 0
    assert result.run.estimated_cost == 0
    assert result.run.duration_ms >= 0
    assert all(node_run.duration_ms >= 0 for node_run in result.run.node_runs)


def test_aggregates_tokens_and_costs_by_workflow_and_node() -> None:
    agents = {
        "first": AgentDefinition(id="first", name="First", system_prompt="Help.", model="gpt-4o-mini"),
        "second": AgentDefinition(id="second", name="Second", system_prompt="Help.", model="gpt-4o-mini"),
    }
    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        models={"gpt-4o-mini": lambda _prompt: ModelResponse(content="answer", usage={"input": 10, "output": 4})},
    )
    workflow = WorkflowDefinition(
        id="usage",
        name="Usage",
        nodes=[
            WorkflowNode(id="first", kind="agent", agent_id="first"),
            WorkflowNode(id="second", kind="agent", agent_id="second"),
        ],
        edges=[WorkflowEdge(source_node_id="first", target_node_id="second")],
        entry_node="first",
        output_node="second",
    )

    result = WorkflowRuntime(runtime, agents.__getitem__).run(workflow, {"problem": "hello"})

    assert result.run.input_tokens == 20
    assert result.run.output_tokens == 8
    assert result.run.total_tokens == 28
    assert result.run.estimated_cost == 0.0000078
    assert result.run.models_used == ["gpt-4o-mini"]
    assert [node_run.total_tokens for node_run in result.run.node_runs] == [14, 14]


def test_rejects_non_linear_workflow() -> None:
    workflow = WorkflowDefinition(
        id="invalid",
        name="Invalid",
        nodes=[
            WorkflowNode(id="first", kind="agent", agent_id="agent"),
            WorkflowNode(id="second", kind="agent", agent_id="agent"),
            WorkflowNode(id="third", kind="agent", agent_id="agent"),
        ],
        edges=[
            WorkflowEdge(source_node_id="first", target_node_id="second"),
            WorkflowEdge(source_node_id="first", target_node_id="third"),
        ],
        entry_node="first",
        output_node="third",
    )

    try:
        WorkflowRuntime._linear_order(workflow)
    except ValueError as error:
        assert "linear" in str(error)
    else:
        raise AssertionError("Expected non-linear workflow to be rejected")
