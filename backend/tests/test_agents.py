from app.agents.store import AgentDraftStore
from app.models.agent import AgentDefinition


def test_agent_drafts_are_versioned_and_reloaded() -> None:
    store = AgentDraftStore()
    agent = AgentDefinition(
        id="atlas-support",
        name="Atlas Support",
        system_prompt="Help users.",
    )

    assert store.save(agent) == 1
    agent.name = "Atlas Support Updated"
    assert store.save(agent) == 2

    saved = store.get(agent.id)
    assert saved is not None
    version, saved_agent = saved
    assert version == 2
    assert saved_agent.name == "Atlas Support Updated"


def test_agent_drafts_list_keeps_different_agents() -> None:
    store = AgentDraftStore()
    first = AgentDefinition(id="data-architect", name="Arquiteto de Dados e Software", system_prompt="Architect.")
    second = AgentDefinition(id="project-manager", name="Gerente de Projetos", system_prompt="Plan.")

    store.save(first)
    store.save(second)

    assert {(agent_id, name) for agent_id, name, _ in store.list()} == {
        ("data-architect", "Arquiteto de Dados e Software"),
        ("project-manager", "Gerente de Projetos"),
    }


def test_agent_draft_can_be_deleted_by_id() -> None:
    store = AgentDraftStore()
    store.save(AgentDefinition(id="duplicate-a", name="Duplicate", system_prompt="A"))
    store.save(AgentDefinition(id="duplicate-b", name="Duplicate", system_prompt="B"))

    assert store.delete("duplicate-a") is True
    assert store.get("duplicate-a") is None
    assert store.get("duplicate-b") is not None
    assert store.delete("missing") is False
