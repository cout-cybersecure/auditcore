-- AuditCore Phase 1 schema.
-- Single-tenant for v0 via a fixed default tenant row.
-- Row-level security and multi-tenancy hardening land in Phase 3.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE run_status AS ENUM (
    'planning', 'collecting', 'normalizing', 'discovering',
    'reporting', 'complete', 'failed'
);

-- Discovery domains: what KIND of system functionality an observation
-- describes. Not a risk taxonomy.
CREATE TYPE domain AS ENUM (
    'security', 'performance', 'cloud', 'k8s', 'db',
    'hardware', 'network', 'software'
);

CREATE TYPE asset_type AS ENUM (
    'host', 'vm', 'container', 'pod', 'k8s_node', 'k8s_cluster',
    'cloud_account', 'cloud_resource', 'database', 'gpu',
    'network_device', 'load_balancer', 'storage_bucket'
);

-- ---------------------------------------------------------------------------
-- Tenancy
-- ---------------------------------------------------------------------------

CREATE TABLE tenants (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tenants (id, name)
VALUES ('00000000-0000-0000-0000-000000000001', 'default');

-- ---------------------------------------------------------------------------
-- Runs
-- ---------------------------------------------------------------------------

CREATE TABLE runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    parent_run_id   UUID REFERENCES runs(id),
    scope           JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection_plan JSONB,
    status          run_status NOT NULL DEFAULT 'planning',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    cost_cents      INT NOT NULL DEFAULT 0
);

CREATE INDEX runs_tenant_started_idx ON runs (tenant_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- Assets
-- ---------------------------------------------------------------------------

CREATE TABLE assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    run_id          UUID NOT NULL REFERENCES runs(id),
    type            asset_type NOT NULL,
    natural_key     TEXT NOT NULL,
    name            TEXT NOT NULL,
    environment     TEXT NOT NULL DEFAULT 'unknown',
    importance      INT NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    parent_asset_id UUID REFERENCES assets(id),
    tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, natural_key)
);

CREATE INDEX assets_run_idx ON assets (run_id);

-- ---------------------------------------------------------------------------
-- Evidence items
-- ---------------------------------------------------------------------------

CREATE TABLE evidence_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id),
    run_id              UUID NOT NULL REFERENCES runs(id),
    asset_id            UUID REFERENCES assets(id),
    source_tool         TEXT NOT NULL,
    source_tool_version TEXT NOT NULL,
    collected_at        TIMESTAMPTZ NOT NULL,
    category            TEXT NOT NULL,
    raw_ref             TEXT NOT NULL,                 -- object store URI
    parsed              JSONB,                          -- NULL until normalized
    confidence          REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    redactions          TEXT[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX evidence_run_category_idx ON evidence_items (run_id, category);
CREATE INDEX evidence_asset_idx        ON evidence_items (asset_id);
CREATE INDEX evidence_run_pending_idx  ON evidence_items (run_id)
    WHERE parsed IS NULL;

-- LISTEN/NOTIFY: ingestion-api inserts evidence rows; the Rust normalizer-worker
-- subscribes to this channel for low-latency wake-up (with poll fallback).
CREATE OR REPLACE FUNCTION notify_evidence_ready() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('auditcore_evidence_ready', NEW.run_id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER evidence_items_notify
AFTER INSERT ON evidence_items
FOR EACH ROW EXECUTE FUNCTION notify_evidence_ready();

-- ---------------------------------------------------------------------------
-- Observations
--
-- A precise, factual statement about discovered system functionality. Purely
-- descriptive: what exists and how it works. No severity, score, or
-- recommendation. Every observation cites at least one evidence item
-- (enforced by the array_length CHECK) — the integrity guarantee of a
-- discovery-and-description tool.
-- ---------------------------------------------------------------------------

CREATE TABLE observations (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenants(id),
    run_id             UUID NOT NULL REFERENCES runs(id),
    asset_id           UUID NOT NULL REFERENCES assets(id),
    domain             domain NOT NULL,
    topic              TEXT NOT NULL,          -- short label, e.g. "SSH authentication"
    summary            TEXT NOT NULL,          -- one-line factual statement
    detail             TEXT NOT NULL,          -- exhaustive precise description
    facts              JSONB NOT NULL DEFAULT '{}'::jsonb,  -- structured key/values
    related_asset_ids  UUID[] NOT NULL DEFAULT '{}',        -- functional relationships
    evidence_ids       UUID[] NOT NULL
                       CHECK (array_length(evidence_ids, 1) > 0),
    produced_by_agent  TEXT NOT NULL,
    model_used         TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX observations_run_domain_idx ON observations (run_id, domain);
CREATE INDEX observations_asset_idx      ON observations (asset_id);
CREATE INDEX observations_topic_idx      ON observations (run_id, topic);

-- ---------------------------------------------------------------------------
-- Report sections
--
-- The report agent assembles observations into a descriptive document. Each
-- section's body references the observations it draws from via
-- [[observation:UUID]] markers; embedded_observations lists those ids. The
-- orchestrator validates every referenced id against the run's observations
-- before persisting — a section may only cite facts that exist.
-- ---------------------------------------------------------------------------

CREATE TABLE report_sections (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants(id),
    run_id                UUID NOT NULL REFERENCES runs(id),
    audience              TEXT NOT NULL,        -- 'technical' | 'summary'
    "order"               INT NOT NULL,
    title                 TEXT NOT NULL,
    body_md               TEXT NOT NULL,
    embedded_observations UUID[] NOT NULL DEFAULT '{}',
    produced_by_agent     TEXT NOT NULL,
    model_used            TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX report_sections_run_idx
    ON report_sections (run_id, audience, "order");

-- ---------------------------------------------------------------------------
-- Audit log
-- ---------------------------------------------------------------------------

CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     UUID,
    actor         TEXT NOT NULL,
    action        TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id   TEXT,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX audit_log_tenant_time_idx ON audit_log (tenant_id, occurred_at DESC);
