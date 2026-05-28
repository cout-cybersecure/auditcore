//! Parser for the AuditCore C++ `hwprobe` binary, which emits a single
//! structured JSON document covering NUMA topology, caches, GPU/NIC
//! summaries, and (optionally) thermals.

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct HwprobeParser;

impl Parser for HwprobeParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let mut doc: Value = serde_json::from_slice(raw).unwrap_or(json!({}));
        if let Value::Object(ref mut m) = doc {
            m.insert("tool_version".into(), Value::String(version.to_string()));
        }

        let (hostname, host_id) = host_from_scope(scope);

        // Pull out a small flat set of attributes for the host asset.
        let attrs = json!({
            "numa_nodes":     doc.get("numa_nodes"),
            "package_count":  doc.get("packages"),
            "core_count":     doc.get("cores"),
            "pu_count":       doc.get("pus"),
            "l3_cache_bytes": doc.get("l3_cache_bytes"),
            "machine_model":  doc.get("machine_model"),
            "bios_vendor":    doc.get("bios_vendor"),
        });

        let confidence = if doc.get("numa_nodes").is_some() { 0.97 } else { 0.6 };

        Ok(ParseResult {
            parsed: doc,
            confidence,
            severity_hint: None,
            asset_hint: Some(AssetHint {
                asset_type: "host".to_string(),
                natural_key: format!("host:{host_id}"),
                name: hostname,
                attributes: attrs,
            }),
            redactions: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_topology_attributes() {
        let raw = br#"{"numa_nodes":2,"packages":1,"cores":8,"pus":16,"l3_cache_bytes":16777216}"#;
        let r = HwprobeParser.parse(raw, "0.1.0", &json!({"hostname":"h"})).unwrap();
        let attrs = &r.asset_hint.unwrap().attributes;
        assert_eq!(attrs["numa_nodes"], 2);
        assert_eq!(attrs["core_count"], 8);
        assert!(r.confidence > 0.9);
    }
}
