use anyhow::Result;
use chrono::{DateTime, Utc};
use serde_json::Value;
use sqlx::postgres::{PgPool, PgPoolOptions};
use uuid::Uuid;

use crate::config::Config;
use crate::parsers::AssetHint;

#[derive(Debug, sqlx::FromRow)]
pub struct PendingEvidence {
    pub id: Uuid,
    pub run_id: Uuid,
    pub source_tool: String,
    pub source_tool_version: String,
    pub raw_ref: String,
}

pub async fn connect(cfg: &Config) -> Result<PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(8)
        .acquire_timeout(std::time::Duration::from_secs(10))
        .connect(&cfg.db_dsn)
        .await?;
    Ok(pool)
}

/// Fetch up to `limit` rows of un-normalized evidence. Optionally scoped to a run.
pub async fn fetch_pending(
    pool: &PgPool,
    run_id: Option<Uuid>,
    limit: i64,
) -> Result<Vec<PendingEvidence>> {
    let rows = if let Some(run) = run_id {
        sqlx::query_as::<_, PendingEvidence>(
            r#"
            SELECT id, run_id, source_tool, source_tool_version, raw_ref
              FROM evidence_items
             WHERE parsed IS NULL AND run_id = $1
             ORDER BY created_at
             LIMIT $2
            "#,
        )
        .bind(run)
        .bind(limit)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query_as::<_, PendingEvidence>(
            r#"
            SELECT id, run_id, source_tool, source_tool_version, raw_ref
              FROM evidence_items
             WHERE parsed IS NULL
             ORDER BY created_at
             LIMIT $1
            "#,
        )
        .bind(limit)
        .fetch_all(pool)
        .await?
    };
    Ok(rows)
}

pub async fn fetch_run_scope(pool: &PgPool, run_id: Uuid) -> Result<Value> {
    let row: (Value,) = sqlx::query_as("SELECT scope FROM runs WHERE id = $1")
        .bind(run_id)
        .fetch_one(pool)
        .await?;
    Ok(row.0)
}

/// Upsert asset by (tenant_id, natural_key). Merges attributes JSON.
pub async fn upsert_asset(
    pool: &PgPool,
    tenant_id: Uuid,
    run_id: Uuid,
    hint: &AssetHint,
) -> Result<Uuid> {
    let row: (Uuid,) = sqlx::query_as(
        r#"
        INSERT INTO assets (tenant_id, run_id, type, natural_key, name, attributes)
        VALUES ($1, $2, $3::asset_type, $4, $5, $6)
        ON CONFLICT (tenant_id, natural_key) DO UPDATE
           SET last_seen  = now(),
               attributes = assets.attributes || EXCLUDED.attributes
        RETURNING id
        "#,
    )
    .bind(tenant_id)
    .bind(run_id)
    .bind(&hint.asset_type)
    .bind(&hint.natural_key)
    .bind(&hint.name)
    .bind(&hint.attributes)
    .fetch_one(pool)
    .await?;
    Ok(row.0)
}

pub async fn write_parsed(
    pool: &PgPool,
    evidence_id: Uuid,
    asset_id: Option<Uuid>,
    parsed: &Value,
    confidence: f32,
) -> Result<()> {
    sqlx::query(
        r#"
        UPDATE evidence_items
           SET parsed = $1,
               asset_id = COALESCE($2, asset_id),
               confidence = $3
         WHERE id = $4
        "#,
    )
    .bind(parsed)
    .bind(asset_id)
    .bind(confidence)
    .bind(evidence_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn audit(
    pool: &PgPool,
    tenant_id: Uuid,
    actor: &str,
    action: &str,
    resource_type: &str,
    resource_id: &str,
    metadata: Value,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO audit_log
            (tenant_id, actor, action, resource_type, resource_id, metadata)
        VALUES ($1, $2, $3, $4, $5, $6)
        "#,
    )
    .bind(tenant_id)
    .bind(actor)
    .bind(action)
    .bind(resource_type)
    .bind(resource_id)
    .bind(metadata)
    .execute(pool)
    .await?;
    Ok(())
}

#[allow(dead_code)]
pub fn _force_use_datetime(_: DateTime<Utc>) {} // keeps chrono import live for future schema needs
