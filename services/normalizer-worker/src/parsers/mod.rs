//! Per-tool parsers.
//!
//! A parser converts raw tool output bytes into a structured `parsed`
//! JSON value plus optional asset attribution. Parsers MUST be
//! deterministic and side-effect free.

mod findmnt;
mod hwprobe;
mod ip_addr;
mod lsblk;
mod lscpu;
mod lspci;
mod ss;
mod uname;

use anyhow::Result;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

pub struct ParseResult {
    pub parsed: Value,
    pub confidence: f32,
    pub asset_hint: Option<AssetHint>,
    #[allow(dead_code)] // populated by future redaction-aware parsers
    pub redactions: Vec<String>,
}

pub struct AssetHint {
    pub asset_type: String, // matches enum asset_type
    pub natural_key: String,
    pub name: String,
    pub attributes: Value,
}

pub trait Parser: Send + Sync {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult>;
}

pub struct Registry {
    map: HashMap<&'static str, Arc<dyn Parser>>,
}

impl Registry {
    pub fn new() -> Self {
        let mut map: HashMap<&'static str, Arc<dyn Parser>> = HashMap::new();
        map.insert("lscpu", Arc::new(lscpu::LscpuParser));
        map.insert("lsblk", Arc::new(lsblk::LsblkParser));
        map.insert("lspci", Arc::new(lspci::LspciParser));
        map.insert("uname", Arc::new(uname::UnameParser));
        map.insert("hwprobe", Arc::new(hwprobe::HwprobeParser));
        map.insert("ip", Arc::new(ip_addr::IpAddrParser));
        map.insert("ss", Arc::new(ss::SsParser));
        map.insert("findmnt", Arc::new(findmnt::FindmntParser));
        Self { map }
    }

    pub fn get(&self, tool: &str) -> Option<Arc<dyn Parser>> {
        self.map.get(tool).cloned()
    }
}

/// Extracts hostname + stable host id from the run scope.
fn host_from_scope(scope: &Value) -> (String, String) {
    let hostname = scope
        .get("hostname")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown-host")
        .to_string();
    let host_id = scope
        .get("host_uuid")
        .and_then(|v| v.as_str())
        .unwrap_or(&hostname)
        .to_string();
    (hostname, host_id)
}
