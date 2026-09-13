ALTER TABLE runs ADD COLUMN IF NOT EXISTS parent_run_id uuid;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS parent_trace_id text;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS workflow_version integer;

CREATE TABLE IF NOT EXISTS workflow_node_runs (
    workflow_run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    node_id text NOT NULL,
    kind text NOT NULL DEFAULT 'agent',
    agent_run_id uuid REFERENCES runs(id) ON DELETE CASCADE,
    tool_name text,
    status text NOT NULL,
    model_name text,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    total_tokens integer NOT NULL DEFAULT 0,
    estimated_cost numeric NOT NULL DEFAULT 0,
    duration_ms integer,
    trace_id text NOT NULL,
    input_artifact_ids text[] NOT NULL DEFAULT '{}',
    output_artifact_ids text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workflow_run_id, node_id)
);

CREATE INDEX IF NOT EXISTS runs_workflow_idx ON runs (workflow_id, started_at DESC);
CREATE INDEX IF NOT EXISTS workflow_node_runs_agent_idx ON workflow_node_runs (agent_run_id);

ALTER TABLE workflow_node_runs ALTER COLUMN agent_run_id DROP NOT NULL;
ALTER TABLE workflow_node_runs ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'agent';
ALTER TABLE workflow_node_runs ADD COLUMN IF NOT EXISTS tool_name text;
