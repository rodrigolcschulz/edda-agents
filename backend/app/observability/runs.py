from collections.abc import Sequence
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.models.agent import AgentDefinition, RunRequest, RunResponse


class RunStore:
    """Persists product-level run summaries without replacing Langfuse traces."""

    def __init__(self, database_url: str | None = None) -> None:
        self._connection = psycopg.connect(database_url, autocommit=True) if database_url else None

    def setup(self) -> None:
        if not self._connection:
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id uuid PRIMARY KEY,
                    kind text NOT NULL,
                    agent_id text,
                    workflow_id text,
                    thread_id text NOT NULL,
                    user_id text,
                    tenant_id uuid,
                    status text NOT NULL,
                    model_name text,
                    input jsonb NOT NULL DEFAULT '{}'::jsonb,
                    output jsonb,
                    input_tokens integer NOT NULL DEFAULT 0,
                    output_tokens integer NOT NULL DEFAULT 0,
                    total_tokens integer NOT NULL DEFAULT 0,
                    estimated_cost numeric NOT NULL DEFAULT 0,
                    duration_ms integer,
                    trace_id text,
                    error_code text,
                    error_message text,
                    started_at timestamptz NOT NULL,
                    finished_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS run_generations (
                    id bigserial PRIMARY KEY,
                    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    node_id text,
                    agent_id text,
                    model_name text NOT NULL,
                    input_tokens integer NOT NULL DEFAULT 0,
                    output_tokens integer NOT NULL DEFAULT 0,
                    total_tokens integer NOT NULL DEFAULT 0,
                    estimated_cost numeric NOT NULL DEFAULT 0,
                    latency_ms integer,
                    provider text,
                    created_at timestamptz NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS run_steps (
                    id bigserial PRIMARY KEY,
                    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    node_id text,
                    kind text NOT NULL,
                    name text NOT NULL,
                    status text NOT NULL,
                    duration_ms integer,
                    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                    started_at timestamptz,
                    finished_at timestamptz
                );

                ALTER TABLE runs ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'agent';
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS workflow_id text;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS model_name text;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS input_tokens integer NOT NULL DEFAULT 0;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS output_tokens integer NOT NULL DEFAULT 0;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS total_tokens integer NOT NULL DEFAULT 0;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS estimated_cost numeric NOT NULL DEFAULT 0;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS duration_ms integer;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS error_code text;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS error_message text;
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

                CREATE INDEX IF NOT EXISTS runs_agent_started_idx ON runs (agent_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS runs_status_started_idx ON runs (status, started_at DESC);
                CREATE INDEX IF NOT EXISTS run_generations_run_idx ON run_generations (run_id);
                CREATE INDEX IF NOT EXISTS run_steps_run_idx ON run_steps (run_id);

                ALTER TABLE runs ALTER COLUMN tenant_id DROP NOT NULL;
                ALTER TABLE runs ALTER COLUMN input SET DEFAULT '{}'::jsonb;
                """
            )

    def start(self, agent: AgentDefinition, request: RunRequest, run_id: str, trace_id: str) -> None:
        if not self._connection:
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runs (
                    id, kind, agent_id, thread_id, user_id, status, model_name, trace_id, started_at
                )
                VALUES (%s::uuid, 'agent', %s, %s, %s, 'running', %s, %s, now())
                """,
                (run_id, agent.id, request.thread_id, request.user_id, agent.model, trace_id),
            )

    def finish(
        self,
        response: RunResponse,
        agent: AgentDefinition,
        duration_ms: float,
        steps: Sequence[dict[str, Any]],
    ) -> None:
        if not self._connection:
            return
        finished_at = datetime.now().astimezone()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE runs
                SET status = %s,
                    model_name = %s,
                    input_tokens = %s,
                    output_tokens = %s,
                    total_tokens = %s,
                    duration_ms = %s,
                    finished_at = %s
                WHERE id = %s
                """,
                (
                    response.status,
                    response.model_name or agent.model,
                    response.input_tokens,
                    response.output_tokens,
                    response.total_tokens,
                    round(duration_ms),
                    finished_at,
                    response.run_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO run_generations (
                    run_id, agent_id, model_name, input_tokens, output_tokens, total_tokens, latency_ms, provider
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    response.run_id,
                    agent.id,
                    response.model_name or agent.model,
                    response.input_tokens,
                    response.output_tokens,
                    response.total_tokens,
                    round(duration_ms),
                    (response.model_name or agent.model).split(":", 1)[0],
                ),
            )
            for step in steps:
                cursor.execute(
                    """
                    INSERT INTO run_steps (run_id, kind, name, status, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (response.run_id, self._step_kind(step["name"]), step["name"], response.status, Jsonb(step)),
                )

    def fail(self, run_id: str, error: Exception, duration_ms: float) -> None:
        if not self._connection:
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE runs
                SET status = 'failed',
                    error_code = %s,
                    error_message = %s,
                    duration_ms = %s,
                    finished_at = now()
                WHERE id = %s
                """,
                (type(error).__name__, str(error)[:1000], round(duration_ms), run_id),
            )

    def close(self) -> None:
        if self._connection:
            self._connection.close()

    @staticmethod
    def _step_kind(name: str) -> str:
        if name in {"memory", "retrieval", "tool", "act", "guardrail", "confirmation"}:
            return "tool" if name == "act" else name
        if name in {"plan", "reflect"}:
            return "generation"
        return "transform"
