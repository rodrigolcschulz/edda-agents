from collections.abc import MutableMapping

import psycopg
from psycopg.types.json import Jsonb

from app.models.agent import AgentDefinition


class AgentDraftStore:
    def __init__(self, database_url: str | None = None) -> None:
        self._connection = psycopg.connect(database_url, autocommit=True) if database_url else None
        self._drafts: MutableMapping[str, tuple[int, AgentDefinition]] = {}

    def setup(self) -> None:
        if self._connection:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_drafts (
                        id text PRIMARY KEY,
                        version integer NOT NULL,
                        definition jsonb NOT NULL,
                        updated_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )

    def save(self, agent: AgentDefinition) -> int:
        if not self._connection:
            version = self._drafts.get(agent.id, (0, agent))[0] + 1
            self._drafts[agent.id] = (version, agent)
            return version

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_drafts (id, version, definition)
                VALUES (%s, 1, %s)
                ON CONFLICT (id) DO UPDATE
                SET version = agent_drafts.version + 1,
                    definition = EXCLUDED.definition,
                    updated_at = now()
                RETURNING version
                """,
                (agent.id, Jsonb(agent.model_dump(mode="json"))),
            )
            return cursor.fetchone()[0]

    def get(self, agent_id: str) -> tuple[int, AgentDefinition] | None:
        if not self._connection:
            return self._drafts.get(agent_id)

        with self._connection.cursor() as cursor:
            cursor.execute("SELECT version, definition FROM agent_drafts WHERE id = %s", (agent_id,))
            row = cursor.fetchone()
        if not row:
            return None
        return row[0], AgentDefinition.model_validate(row[1])

    def list(self) -> list[tuple[str, str, int]]:
        if not self._connection:
            return [
                (agent_id, agent.name, version)
                for agent_id, (version, agent) in self._drafts.items()
            ]

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, definition ->> 'name', version FROM agent_drafts ORDER BY updated_at DESC"
            )
            return cursor.fetchall()

    def delete(self, agent_id: str) -> bool:
        if not self._connection:
            return self._drafts.pop(agent_id, None) is not None

        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_drafts WHERE id = %s", (agent_id,))
            return cursor.rowcount > 0

    def close(self) -> None:
        if self._connection:
            self._connection.close()
