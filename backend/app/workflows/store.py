from collections.abc import MutableMapping

import psycopg
from psycopg.types.json import Jsonb

from app.models.workflow import WorkflowDefinition


class WorkflowDefinitionStore:
    def __init__(self, database_url: str | None = None) -> None:
        self._connection = psycopg.connect(database_url, autocommit=True) if database_url else None
        self._workflows: MutableMapping[str, tuple[int, WorkflowDefinition]] = {}

    def setup(self) -> None:
        if self._connection:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_definitions (
                        id text PRIMARY KEY,
                        version integer NOT NULL,
                        definition jsonb NOT NULL,
                        updated_at timestamptz NOT NULL DEFAULT now()
                    );
                    CREATE INDEX IF NOT EXISTS workflow_definitions_updated_idx
                    ON workflow_definitions (updated_at DESC);
                    """
                )

    def save(self, workflow: WorkflowDefinition) -> int:
        if not self._connection:
            version = self._workflows.get(workflow.id, (0, workflow))[0] + 1
            self._workflows[workflow.id] = (version, workflow.model_copy(update={"version": version}))
            return version

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO workflow_definitions (id, version, definition)
                VALUES (%s, 1, %s)
                ON CONFLICT (id) DO UPDATE
                SET version = workflow_definitions.version + 1,
                    definition = EXCLUDED.definition,
                    updated_at = now()
                RETURNING version
                """,
                (workflow.id, Jsonb(workflow.model_dump(mode="json"))),
            )
            version = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE workflow_definitions SET definition = %s WHERE id = %s",
                (Jsonb(workflow.model_copy(update={"version": version}).model_dump(mode="json")), workflow.id),
            )
        return version

    def get(self, workflow_id: str) -> tuple[int, WorkflowDefinition] | None:
        if not self._connection:
            return self._workflows.get(workflow_id)

        with self._connection.cursor() as cursor:
            cursor.execute("SELECT version, definition FROM workflow_definitions WHERE id = %s", (workflow_id,))
            row = cursor.fetchone()
        if not row:
            return None
        return row[0], WorkflowDefinition.model_validate(row[1])

    def list(self) -> list[tuple[str, str, int]]:
        if not self._connection:
            return [(workflow_id, workflow.name, version) for workflow_id, (version, workflow) in self._workflows.items()]

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, definition ->> 'name', version FROM workflow_definitions ORDER BY updated_at DESC"
            )
            return cursor.fetchall()

    def delete(self, workflow_id: str) -> bool:
        if not self._connection:
            return self._workflows.pop(workflow_id, None) is not None

        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM workflow_definitions WHERE id = %s", (workflow_id,))
            return cursor.rowcount > 0

    def close(self) -> None:
        if self._connection:
            self._connection.close()