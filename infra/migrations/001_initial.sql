CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agents (
    id text NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    current_version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE agent_versions (
    agent_id text NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    version integer NOT NULL,
    definition jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent_id, version),
    FOREIGN KEY (tenant_id, agent_id) REFERENCES agents(tenant_id, id)
);

CREATE TABLE agent_drafts (
    id text PRIMARY KEY,
    version integer NOT NULL,
    definition jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE threads (
    id text NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id text NOT NULL,
    agent_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, agent_id) REFERENCES agents(tenant_id, id)
);

CREATE TABLE long_term_memory (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id text NOT NULL,
    agent_id text NOT NULL,
    fact text NOT NULL,
    embedding vector(768),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, agent_id) REFERENCES agents(tenant_id, id)
);

CREATE TABLE runs (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    agent_id text NOT NULL,
    thread_id text NOT NULL,
    user_id text NOT NULL,
    status text NOT NULL,
    input jsonb NOT NULL,
    output jsonb,
    trace_id text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    FOREIGN KEY (tenant_id, agent_id) REFERENCES agents(tenant_id, id),
    FOREIGN KEY (tenant_id, thread_id) REFERENCES threads(tenant_id, id)
);

CREATE INDEX long_term_memory_embedding_idx
    ON long_term_memory USING hnsw (embedding vector_cosine_ops);
CREATE INDEX long_term_memory_user_idx
    ON long_term_memory (tenant_id, user_id, agent_id);
CREATE INDEX runs_thread_idx
    ON runs (tenant_id, thread_id, started_at DESC);

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE long_term_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_agents ON agents
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_agent_versions ON agent_versions
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_threads ON threads
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_memory ON long_term_memory
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation_runs ON runs
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);