//! AuditCore normalizer worker.
//!
//! Polls Postgres for un-normalized evidence_items, fetches raw bytes from
//! object storage, runs the per-tool parser, writes parsed JSONB back, and
//! upserts derived assets. Uses Postgres LISTEN/NOTIFY for low-latency
//! wake-up and a polling interval as a fallback.

mod config;
mod db;
mod normalize;
mod parsers;
mod storage;
mod worker;

use clap::Parser;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[derive(Parser, Debug)]
#[command(name = "auditcore-normalizer", version)]
struct Args {
    #[arg(long, env = "AUDITCORE_DB_DSN",
          default_value = "postgresql://auditcore:dev-only-change-me@localhost:5432/auditcore")]
    db_dsn: String,

    #[arg(long, env = "AUDITCORE_S3_ENDPOINT",
          default_value = "http://localhost:9000")]
    s3_endpoint: String,

    #[arg(long, env = "AUDITCORE_S3_ACCESS_KEY", default_value = "auditcore")]
    s3_access_key: String,

    #[arg(long, env = "AUDITCORE_S3_SECRET_KEY", default_value = "dev-only-change-me")]
    s3_secret_key: String,

    /// Default tenant id for single-tenant Phase 1 deployments.
    #[arg(long, env = "AUDITCORE_DEFAULT_TENANT_ID",
          default_value = "00000000-0000-0000-0000-000000000001")]
    default_tenant_id: String,

    /// Poll interval seconds; falls back when no NOTIFY arrives.
    #[arg(long, env = "AUDITCORE_POLL_INTERVAL_SECS", default_value = "30")]
    poll_interval_secs: u64,

    /// Max concurrent parser tasks.
    #[arg(long, env = "AUDITCORE_PARSE_CONCURRENCY", default_value = "8")]
    parse_concurrency: usize,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();

    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| EnvFilter::new("auditcore_normalizer=info,sqlx=warn")))
        .init();

    info!(
        s3_endpoint = %args.s3_endpoint,
        poll_secs = args.poll_interval_secs,
        concurrency = args.parse_concurrency,
        "starting normalizer worker"
    );

    let cfg = config::Config {
        db_dsn: args.db_dsn,
        s3_endpoint: args.s3_endpoint,
        s3_access_key: args.s3_access_key,
        s3_secret_key: args.s3_secret_key,
        default_tenant_id: args.default_tenant_id.parse()?,
        poll_interval_secs: args.poll_interval_secs,
        parse_concurrency: args.parse_concurrency,
    };

    worker::run(cfg).await
}
