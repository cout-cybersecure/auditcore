use anyhow::{anyhow, Context, Result};
use aws_config::{BehaviorVersion, Region};
use aws_credential_types::Credentials;
use aws_sdk_s3::config::Builder;
use aws_sdk_s3::Client;

use crate::config::Config;

pub fn make_client(cfg: &Config) -> Client {
    let creds = Credentials::new(
        &cfg.s3_access_key,
        &cfg.s3_secret_key,
        None, None, "auditcore-static",
    );
    let s3_cfg = Builder::new()
        .behavior_version(BehaviorVersion::latest())
        .endpoint_url(&cfg.s3_endpoint)
        .region(Region::new("us-east-1"))     // MinIO ignores this; required by SDK
        .credentials_provider(creds)
        .force_path_style(true)               // required for MinIO
        .build();
    Client::from_conf(s3_cfg)
}

/// Splits an s3:// URI into (bucket, key).
pub fn parse_s3_uri(uri: &str) -> Result<(String, String)> {
    let rest = uri
        .strip_prefix("s3://")
        .ok_or_else(|| anyhow!("not an s3:// URI: {uri}"))?;
    let (bucket, key) = rest
        .split_once('/')
        .ok_or_else(|| anyhow!("s3 URI missing key: {uri}"))?;
    Ok((bucket.to_string(), key.to_string()))
}

pub async fn fetch_object(client: &Client, uri: &str) -> Result<Vec<u8>> {
    let (bucket, key) = parse_s3_uri(uri)?;
    let resp = client
        .get_object()
        .bucket(&bucket)
        .key(&key)
        .send()
        .await
        .with_context(|| format!("get_object {uri}"))?;
    let bytes = resp
        .body
        .collect()
        .await
        .with_context(|| format!("read body of {uri}"))?
        .into_bytes();
    Ok(bytes.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_s3_uri() {
        let (b, k) = parse_s3_uri("s3://bucket/runs/abc/items/xyz.raw").unwrap();
        assert_eq!(b, "bucket");
        assert_eq!(k, "runs/abc/items/xyz.raw");
    }

    #[test]
    fn rejects_non_s3() {
        assert!(parse_s3_uri("http://x/y").is_err());
    }
}
