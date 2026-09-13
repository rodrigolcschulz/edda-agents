from app.models.workflow import WorkflowDefinition, WorkflowNode
from app.workflows.store import WorkflowDefinitionStore


def make_workflow(workflow_id: str = "sales") -> WorkflowDefinition:
    return WorkflowDefinition(
        id=workflow_id,
        name="Sales workflow",
        nodes=[WorkflowNode(id="agent", kind="agent", agent_id="project-manager")],
        entry_node="agent",
        output_node="agent",
    )


def test_workflow_store_versions_lists_loads_and_deletes() -> None:
    store = WorkflowDefinitionStore()
    workflow = make_workflow()

    assert store.save(workflow) == 1
    assert store.save(workflow) == 2
    assert store.list() == [("sales", "Sales workflow", 2)]

    saved = store.get("sales")
    assert saved is not None
    assert saved[0] == 2
    assert saved[1].id == "sales"
    assert store.delete("sales") is True
    assert store.get("sales") is None
    assert store.delete("sales") is False