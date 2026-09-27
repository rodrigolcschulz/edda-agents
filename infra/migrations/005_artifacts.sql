CREATE TABLE IF NOT EXISTS artifacts (
    id uuid PRIMARY KEY,
    kind text NOT NULL,
    bucket text NOT NULL,
    object_key text NOT NULL UNIQUE,
    filename text,
    content_type text NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_run_artifacts (
    workflow_run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    artifact_id uuid NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('input', 'output')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workflow_run_id, artifact_id, role)
);

CREATE INDEX IF NOT EXISTS workflow_run_artifacts_artifact_idx
ON workflow_run_artifacts (artifact_id);