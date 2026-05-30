//! Parser for `ss -tuln` (listening TCP/UDP sockets, no process info).
//!
//! Columns: Netid State Recv-Q Send-Q Local-Address:Port Peer-Address:Port

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct SsParser;

impl Parser for SsParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let text = String::from_utf8_lossy(raw);
        let mut sockets: Vec<Value> = Vec::new();

        for (idx, line) in text.lines().enumerate() {
            if idx == 0 && line.trim_start().starts_with("Netid") {
                continue; // header
            }
            let cols: Vec<&str> = line.split_whitespace().collect();
            if cols.len() < 5 {
                continue;
            }
            let netid = cols[0];
            let state = cols[1];
            let local = cols[4];
            let (addr, port) = split_host_port(local);
            sockets.push(json!({
                "protocol": netid,
                "state": state,
                "local_address": addr,
                "port": port,
            }));
        }

        // Distinct listening ports for a compact host attribute.
        let mut ports: Vec<String> = sockets
            .iter()
            .filter_map(|s| s.get("port").and_then(|p| p.as_str()).map(str::to_string))
            .collect();
        ports.sort();
        ports.dedup();

        let parsed = json!({
            "tool_version": version,
            "listening_sockets": sockets,
            "summary": {
                "socket_count": sockets.len(),
                "distinct_ports": ports,
            },
        });

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({ "listening_socket_count": sockets.len() }),
        };

        Ok(ParseResult {
            parsed,
            confidence: 0.9,
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

/// Splits "1.2.3.4:443" / "[::]:443" / "*:443" into (address, port).
fn split_host_port(s: &str) -> (String, String) {
    match s.rfind(':') {
        Some(i) => (s[..i].to_string(), s[i + 1..].to_string()),
        None => (s.to_string(), String::new()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "\
Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port
tcp   LISTEN 0      128          0.0.0.0:22        0.0.0.0:*
tcp   LISTEN 0      128             [::]:443          [::]:*
udp   UNCONN 0      0            127.0.0.1:323       0.0.0.0:*
";

    #[test]
    fn parses_listening_sockets() {
        let r = SsParser
            .parse(SAMPLE.as_bytes(), "iproute2", &json!({"hostname": "h"}))
            .unwrap();
        assert_eq!(r.parsed["summary"]["socket_count"], 3);
        assert_eq!(r.parsed["listening_sockets"][0]["port"], "22");
        assert_eq!(r.parsed["listening_sockets"][0]["protocol"], "tcp");
        let ports = r.parsed["summary"]["distinct_ports"].as_array().unwrap();
        assert!(ports.iter().any(|p| p == "443"));
    }

    #[test]
    fn handles_ipv6_brackets() {
        let (addr, port) = split_host_port("[::]:443");
        assert_eq!(addr, "[::]");
        assert_eq!(port, "443");
    }
}
