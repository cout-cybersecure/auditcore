//! Parser for `uname -a`.

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct UnameParser;

impl Parser for UnameParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let text = String::from_utf8_lossy(raw).trim().to_string();
        // Fields: <kernel-name> <nodename> <kernel-release> <kernel-version...> <machine> <os>
        let toks: Vec<&str> = text.split_whitespace().collect();
        let parsed = json!({
            "tool_version": version,
            "raw": text,
            "kernel_name":    toks.first().copied().unwrap_or(""),
            "nodename":       toks.get(1).copied().unwrap_or(""),
            "kernel_release": toks.get(2).copied().unwrap_or(""),
            "os":             toks.last().copied().unwrap_or(""),
        });

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({
                "kernel_name": parsed["kernel_name"],
                "kernel_release": parsed["kernel_release"],
                "os": parsed["os"],
            }),
        };

        Ok(ParseResult {
            parsed,
            confidence: if toks.len() >= 5 { 0.95 } else { 0.5 },
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_uname_a() {
        let raw =
            b"Linux box 6.17.0-29-generic #29-Ubuntu SMP PREEMPT_DYNAMIC ... x86_64 GNU/Linux\n";
        let r = UnameParser
            .parse(raw, "x", &json!({"hostname":"box"}))
            .unwrap();
        assert_eq!(r.parsed["kernel_name"], "Linux");
        assert_eq!(r.parsed["kernel_release"], "6.17.0-29-generic");
        assert!(r.confidence > 0.9);
    }
}
