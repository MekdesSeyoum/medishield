-- MediShield — PostgreSQL schema
-- Applied automatically on first container start via docker-entrypoint-initdb.d

CREATE TABLE IF NOT EXISTS cases (
    case_id         UUID PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    file_name       TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    file_key        TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    orchestrator_output JSONB,
    classifier_output   JSONB,
    kyc_output          JSONB,
    claims_output       JSONB,
    policy_output       JSONB,
    fraud_output        JSONB,
    audit_log           JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_cases_status     ON cases (status);
CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases (created_at DESC);
