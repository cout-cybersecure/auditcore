//! Parser for `lsblk -J -O` (JSON output, all columns).

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct LsblkParser;

impl Parser for LsblkParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        // lsblk -J emits {"blockdevices": [...]}; preserve as-is and add metadata.
        let mut doc: Value = serde_json::from_slice(raw).unwrap_or(json!({}));
        if let Value::Object(ref mut m) = doc {
            m.insert("tool_version".into(), Value::String(version.to_string()));
        }

        // Build a flat summary for downstream agents.
        let mut total_disks = 0u32;
        let mut total_bytes: u128 = 0;
        let mut rotational_disks = 0u32;
        if let Some(devs) = doc.get("blockdevices").and_then(|v| v.as_array()) {
            for d in devs {
                if d.get("type").and_then(|v| v.as_str()) == Some("disk") {
                    total_disks += 1;
                    if let Some(sz) = d.get("size").and_then(|v| v.as_u64()) {
                        total_bytes += sz as u128;
                    } else if let Some(sz_str) = d.get("size").and_then(|v| v.as_str()) {
                        if let Ok(n) = sz_str.parse::<u128>() {
                            total_bytes += n;
                        }
                    }
                    if d.get("rota").and_then(|v| v.as_u64()) == Some(1) {
                        rotational_disks += 1;
                    }
                }
            }
        }

        if let Value::Object(ref mut m) = doc {
            m.insert(
                "summary".into(),
                json!({
                    "disks": total_disks,
                    "rotational_disks": rotational_disks,
                    "total_bytes": total_bytes.to_string(),
                }),
            );
        }

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({
                "disk_count": total_disks,
                "rotational_disks": rotational_disks,
                "total_storage_bytes": total_bytes.to_string(),
            }),
        };

        Ok(ParseResult {
            parsed: doc,
            confidence: if total_disks > 0 { 0.9 } else { 0.5 },
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_minimal_lsblk_json() {
        let raw = br#"{"blockdevices":[
            {"name":"nvme0n1","type":"disk","size":512000000000,"rota":0},
            {"name":"sda","type":"disk","size":"1000000000000","rota":1}
        ]}"#;
        let r = LsblkParser
            .parse(raw, "2.39.3", &json!({"hostname":"h"}))
            .unwrap();
        assert_eq!(r.parsed["summary"]["disks"], 2);
        assert_eq!(r.parsed["summary"]["rotational_disks"], 1);
        assert!(r.confidence > 0.8);
    }
}
