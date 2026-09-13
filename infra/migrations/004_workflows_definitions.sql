CREATE TABLE IF NOT EXISTS workflow_definitions (
    id text PRIMARY KEY,
    version integer NOT NULL,
    definition jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_definitions_updated_idx
ON workflow_definitions (updated_at DESC);