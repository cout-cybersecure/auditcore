//! Parser for `lspci -vmm` (machine-readable record-per-blank-line format).

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct LspciParser;

impl Parser for LspciParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let text = String::from_utf8_lossy(raw);
        let mut devices: Vec<Value> = Vec::new();
        let mut current = serde_json::Map::new();

        for line in text.lines() {
            if line.trim().is_empty() {
                if !current.is_empty() {
                    devices.push(Value::Object(std::mem::take(&mut current)));
                }
                continue;
            }
            if let Some((k, v)) = line.split_once(':') {
                current.insert(k.trim().to_string(), Value::String(v.trim().to_string()));
            }
        }
        if !current.is_empty() {
            devices.push(Value::Object(current));
        }

        // Heuristics for richer asset attributes.
        let mut gpu_count = 0u32;
        let mut nic_count = 0u32;
        let mut nvme_count = 0u32;
        for d in &devices {
            let class = d.get("Class").and_then(|v| v.as_str()).unwrap_or("");
            if class.contains("VGA") || class.contains("3D") || class.contains("Display") {
                gpu_count += 1;
            } else if class.contains("Ethernet") || class.contains("Network") {
                nic_count += 1;
            } else if class.contains("Non-Volatile") {
                nvme_count += 1;
            }
        }

        let parsed = json!({
            "tool_version": version,
            "devices": devices,
            "summary": {
                "device_count": devices.len(),
                "gpus": gpu_count,
                "nics": nic_count,
                "nvme_controllers": nvme_count,
            },
        });

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({
                "pci_device_count": devices.len(),
                "pci_gpus": gpu_count,
                "pci_nics": nic_count,
                "pci_nvme": nvme_count,
            }),
        };

        Ok(ParseResult {
            parsed,
            confidence: if devices.is_empty() { 0.4 } else { 0.9 },
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_records_by_blank_line() {
        let raw = b"\
Slot:   00:00.0
Class:  Host bridge
Vendor: Intel Corporation

Slot:   00:02.0
Class:  VGA compatible controller
Vendor: Intel Corporation
";
        let r = LspciParser
            .parse(raw, "3.10", &json!({"hostname":"h"}))
            .unwrap();
        assert_eq!(r.parsed["summary"]["device_count"], 2);
        assert_eq!(r.parsed["summary"]["gpus"], 1);
    }
}
