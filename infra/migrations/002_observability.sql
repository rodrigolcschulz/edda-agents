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
ALTER TABLE runs ALTER COLUMN tenant_id DROP NOT NULL;
ALTER TABLE runs ALTER COLUMN input SET DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS runs_agent_started_idx ON runs (agent_id, started_at DESC);
CREATE INDEX IF NOT EXISTS runs_status_started_idx ON runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS run_generations_run_idx ON run_generations (run_id);
CREATE INDEX IF NOT EXISTS run_steps_run_idx ON run_steps (run_id);
