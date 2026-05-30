use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

const INT_FIELDS: &[&str] = &[
    "CPU(s)", "Socket(s)", "Core(s) per socket", "Thread(s) per core", "NUMA node(s)",
];

pub struct LscpuParser;

impl Parser for LscpuParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let text = String::from_utf8_lossy(raw);
        let mut parsed = serde_json::Map::new();
        parsed.insert("tool_version".into(), Value::String(version.to_string()));

        for line in text.lines() {
            let Some((k, v)) = line.split_once(':') else { continue };
            let k = k.trim();
            let v = v.trim();
            if INT_FIELDS.contains(&k) {
                if let Ok(n) = v.parse::<i64>() {
                    parsed.insert(k.to_string(), Value::Number(n.into()));
                    continue;
                }
            }
            parsed.insert(k.to_string(), Value::String(v.to_string()));
        }

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({
                "cpu_model":        parsed.get("Model name"),
                "cpu_vendor":       parsed.get("Vendor ID"),
                "cpus":             parsed.get("CPU(s)"),
                "sockets":          parsed.get("Socket(s)"),
                "cores_per_socket": parsed.get("Core(s) per socket"),
                "threads_per_core": parsed.get("Thread(s) per core"),
                "numa_nodes":       parsed.get("NUMA node(s)"),
                "architecture":     parsed.get("Architecture"),
            }),
        };

        let confidence = if parsed.contains_key("Model name") { 0.95 } else { 0.6 };

        Ok(ParseResult {
            parsed: Value::Object(parsed),
            confidence,
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "\
Architecture:                         x86_64
CPU(s):                               16
Vendor ID:                            GenuineIntel
Model name:                           Intel(R) Xeon(R) Gold 6226R CPU @ 2.90GHz
Thread(s) per core:                   2
Core(s) per socket:                   8
Socket(s):                            1
NUMA node(s):                         1
";

    #[test]
    fn parses_topology() {
        let r = LscpuParser
            .parse(SAMPLE.as_bytes(), "util-linux 2.39.3",
                   &json!({"hostname": "host-a"}))
            .unwrap();
        assert_eq!(r.parsed["CPU(s)"], 16);
        assert_eq!(r.parsed["Socket(s)"], 1);
        assert_eq!(r.parsed["Core(s) per socket"], 8);
        assert!(r.confidence > 0.9);
        let hint = r.asset_hint.unwrap();
        assert_eq!(hint.asset_type, "host");
        assert_eq!(hint.name, "host-a");
        assert_eq!(hint.natural_key, "host:host-a");
        assert_eq!(hint.attributes["cpus"], 16);
    }

    #[test]
    fn low_confidence_without_model() {
        let r = LscpuParser
            .parse(b"Architecture: aarch64\nCPU(s): 4\n", "x", &json!({}))
            .unwrap();
        assert!(r.confidence < 0.9);
    }
}
