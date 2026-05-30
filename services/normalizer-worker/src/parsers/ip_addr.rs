//! Parser for `ip -j addr` (JSON array of network interfaces).

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct IpAddrParser;

impl Parser for IpAddrParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let ifaces: Value = serde_json::from_slice(raw).unwrap_or(json!([]));

        let mut summary: Vec<Value> = Vec::new();
        let mut iface_count = 0u32;
        let mut non_loopback = 0u32;

        if let Some(arr) = ifaces.as_array() {
            for i in arr {
                iface_count += 1;
                let name = i.get("ifname").and_then(|v| v.as_str()).unwrap_or("");
                let is_loopback = i
                    .get("link_type")
                    .and_then(|v| v.as_str())
                    .map(|s| s == "loopback")
                    .unwrap_or(false);
                if !is_loopback {
                    non_loopback += 1;
                }

                let addrs: Vec<Value> = i
                    .get("addr_info")
                    .and_then(|v| v.as_array())
                    .map(|a| {
                        a.iter()
                            .map(|ai| {
                                json!({
                                    "family": ai.get("family"),
                                    "local":  ai.get("local"),
                                    "prefixlen": ai.get("prefixlen"),
                                })
                            })
                            .collect()
                    })
                    .unwrap_or_default();

                summary.push(json!({
                    "ifname": name,
                    "mac": i.get("address"),
                    "mtu": i.get("mtu"),
                    "operstate": i.get("operstate"),
                    "link_type": i.get("link_type"),
                    "addresses": addrs,
                }));
            }
        }

        let parsed = json!({
            "tool_version": version,
            "interfaces": summary,
            "summary": { "interface_count": iface_count, "non_loopback": non_loopback },
        });

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({
                "network_interface_count": iface_count,
                "non_loopback_interfaces": non_loopback,
            }),
        };

        Ok(ParseResult {
            parsed,
            confidence: if iface_count > 0 { 0.95 } else { 0.4 },
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"[
      {"ifindex":1,"ifname":"lo","link_type":"loopback","mtu":65536,"operstate":"UNKNOWN",
       "address":"00:00:00:00:00:00",
       "addr_info":[{"family":"inet","local":"127.0.0.1","prefixlen":8}]},
      {"ifindex":2,"ifname":"eth0","link_type":"ether","mtu":1500,"operstate":"UP",
       "address":"aa:bb:cc:dd:ee:ff",
       "addr_info":[{"family":"inet","local":"10.0.0.5","prefixlen":24}]}
    ]"#;

    #[test]
    fn parses_interfaces() {
        let r = IpAddrParser
            .parse(SAMPLE.as_bytes(), "iproute2", &json!({"hostname": "h"}))
            .unwrap();
        assert_eq!(r.parsed["summary"]["interface_count"], 2);
        assert_eq!(r.parsed["summary"]["non_loopback"], 1);
        assert_eq!(r.parsed["interfaces"][1]["ifname"], "eth0");
        assert_eq!(r.parsed["interfaces"][1]["mac"], "aa:bb:cc:dd:ee:ff");
        assert!(r.confidence > 0.9);
    }
}
