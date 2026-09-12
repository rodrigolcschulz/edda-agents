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
