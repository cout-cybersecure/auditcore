use anyhow::Result;
use aws_sdk_s3::Client as S3Client;
use sqlx::PgPool;
use std::sync::Arc;
use tracing::{debug, info, warn};
use uuid::Uuid;

use crate::config::Config;
use crate::db::{self, PendingEvidence};
use crate::parsers::Registry;
use crate::storage;

pub async fn normalize_one(
    pool: &PgPool,
    s3: &S3Client,
    registry: &Registry,
    cfg: &Config,
    ev: PendingEvidence,
) -> Result<()> {
    let parser = match registry.get(&ev.source_tool) {
        Some(p) => p,
        None => {
            debug!(tool = %ev.source_tool, evidence_id = %ev.id, "no parser registered; skipping");
            return Ok(());
        }
    };

    let raw = storage::fetch_object(s3, &ev.raw_ref).await?;
    let scope = db::fetch_run_scope(pool, ev.run_id).await?;

    let mut result = parser.parse(&raw, &ev.source_tool_version, &scope)?;

    // Redact secrets from the parsed evidence before it is persisted or ever
    // reaches a model. This is the normalizer-side stage of two-stage redaction.
    let redactions = crate::redact::redact_value(&mut result.parsed);
    if !redactions.is_empty() {
        tracing::warn!(
            evidence_id = %ev.id, tool = %ev.source_tool,
            rules = ?redactions, "redacted secrets from parsed evidence"
        );
    }

    let asset_id = if let Some(hint) = result.asset_hint.as_ref() {
        Some(db::upsert_asset(pool, cfg.default_tenant_id, ev.run_id, hint).await?)
    } else {
        None
    };

    db::write_parsed(
        pool,
        ev.id,
        asset_id,
        &result.parsed,
        result.confidence,
        &redactions,
    )
    .await?;

    db::audit(
        pool,
        cfg.default_tenant_id,
        "normalizer-worker",
        "evidence.normalize",
        "evidence_item",
        &ev.id.to_string(),
        serde_json::json!({
            "tool": ev.source_tool,
            "confidence": result.confidence,
        }),
    )
    .await?;

    info!(
        evidence_id = %ev.id,
        tool = %ev.source_tool,
        run_id = %ev.run_id,
        confidence = result.confidence,
        "normalized"
    );
    Ok(())
}

/// Drain all pending evidence for an optional run scope. Concurrency-bounded.
pub async fn drain_pending(
    pool: Arc<PgPool>,
    s3: Arc<S3Client>,
    registry: Arc<Registry>,
    cfg: Arc<Config>,
    run_id: Option<Uuid>,
) -> Result<usize> {
    use futures::stream::{self, StreamExt};

    let batch = db::fetch_pending(&pool, run_id, 500).await?;
    if batch.is_empty() {
        return Ok(0);
    }
    let count = batch.len();
    info!(count, ?run_id, "draining pending evidence");

    let concurrency = cfg.parse_concurrency.max(1);

    let results: Vec<Result<()>> = stream::iter(batch.into_iter().map(|ev| {
        let pool = Arc::clone(&pool);
        let s3 = Arc::clone(&s3);
        let reg = Arc::clone(&registry);
        let cfg = Arc::clone(&cfg);
        async move { normalize_one(&pool, &s3, &reg, &cfg, ev).await }
    }))
    .buffer_unordered(concurrency)
    .collect()
    .await;

    let mut failed = 0;
    for r in &results {
        if let Err(e) = r {
            warn!(error = %e, "failed to normalize an evidence item");
            failed += 1;
        }
    }
    info!(processed = count, failed, "drain complete");
    Ok(count)
}
