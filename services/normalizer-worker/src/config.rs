use uuid::Uuid;

#[derive(Clone, Debug)]
pub struct Config {
    pub db_dsn: String,
    pub s3_endpoint: String,
    pub s3_access_key: String,
    pub s3_secret_key: String,
    pub default_tenant_id: Uuid,
    pub poll_interval_secs: u64,
    pub parse_concurrency: usize,
}
