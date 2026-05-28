use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use sqlx::postgres::PgListener;
use tokio::{select, signal, time};
use tracing::{info, warn};
use uuid::Uuid;

use crate::config::Config;
use crate::db;
use crate::normalize;
use crate::parsers::Registry;
use crate::storage;

const NOTIFY_CHANNEL: &str = "auditcore_evidence_ready";

pub async fn run(cfg: Config) -> Result<()> {
    let pool = Arc::new(db::connect(&cfg).await?);
    let s3 = Arc::new(storage::make_client(&cfg));
    let registry = Arc::new(Registry::new());
    let cfg = Arc::new(cfg);

    // Drain anything already pending at startup (covers crash recovery).
    normalize::drain_pending(
        Arc::clone(&pool),
        Arc::clone(&s3),
        Arc::clone(&registry),
        Arc::clone(&cfg),
        None,
    )
    .await
    .ok();

    let mut listener = PgListener::connect(&cfg.db_dsn).await?;
    listener.listen(NOTIFY_CHANNEL).await?;
    info!(channel = NOTIFY_CHANNEL, "subscribed to Postgres NOTIFY");

    let mut tick = time::interval(Duration::from_secs(cfg.poll_interval_secs));
    tick.set_missed_tick_behavior(time::MissedTickBehavior::Skip);

    loop {
        select! {
            _ = signal::ctrl_c() => {
                info!("shutdown signal received");
                return Ok(());
            }
            notif = listener.recv() => {
                match notif {
                    Ok(n) => {
                        let payload = n.payload();
                        let run_id = Uuid::parse_str(payload).ok();
                        if run_id.is_none() {
                            warn!(payload, "NOTIFY payload was not a UUID; draining globally");
                        }
                        let _ = normalize::drain_pending(
                            Arc::clone(&pool),
                            Arc::clone(&s3),
                            Arc::clone(&registry),
                            Arc::clone(&cfg),
                            run_id,
                        ).await;
                    }
                    Err(e) => {
                        warn!(error = %e, "NOTIFY listener error; reconnecting in 5s");
                        time::sleep(Duration::from_secs(5)).await;
                        if let Ok(mut l) = PgListener::connect(&cfg.db_dsn).await {
                            if l.listen(NOTIFY_CHANNEL).await.is_ok() {
                                listener = l;
                            }
                        }
                    }
                }
            }
            _ = tick.tick() => {
                let _ = normalize::drain_pending(
                    Arc::clone(&pool),
                    Arc::clone(&s3),
                    Arc::clone(&registry),
                    Arc::clone(&cfg),
                    None,
                ).await;
            }
        }
    }
}
