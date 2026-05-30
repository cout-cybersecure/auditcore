//! Parser for `findmnt -J` (mounted filesystems as a nested JSON tree).
//!
//! The tree is flattened into a list of mounts so downstream description is
//! simple; each mount keeps target/source/fstype/options.

use anyhow::Result;
use serde_json::{json, Value};

use super::{host_from_scope, AssetHint, ParseResult, Parser};

pub struct FindmntParser;

impl Parser for FindmntParser {
    fn parse(&self, raw: &[u8], version: &str, scope: &Value) -> Result<ParseResult> {
        let doc: Value = serde_json::from_slice(raw).unwrap_or(json!({}));
        let mut mounts: Vec<Value> = Vec::new();
        if let Some(fs) = doc.get("filesystems").and_then(|v| v.as_array()) {
            for node in fs {
                flatten(node, &mut mounts);
            }
        }

        // Distinct real fstypes (exclude pseudo filesystems for a compact view).
        let pseudo = [
            "sysfs",
            "proc",
            "cgroup",
            "cgroup2",
            "tmpfs",
            "devtmpfs",
            "devpts",
            "mqueue",
            "debugfs",
            "tracefs",
            "securityfs",
            "pstore",
            "bpf",
            "configfs",
            "fusectl",
            "hugetlbfs",
            "autofs",
            "binfmt_misc",
        ];
        let mut real_fstypes: Vec<String> = mounts
            .iter()
            .filter_map(|m| m.get("fstype").and_then(|v| v.as_str()))
            .filter(|t| !pseudo.contains(t))
            .map(str::to_string)
            .collect();
        real_fstypes.sort();
        real_fstypes.dedup();

        let parsed = json!({
            "tool_version": version,
            "mounts": mounts,
            "summary": {
                "mount_count": mounts.len(),
                "real_fstypes": real_fstypes,
            },
        });

        let (hostname, host_id) = host_from_scope(scope);
        let asset_hint = AssetHint {
            asset_type: "host".to_string(),
            natural_key: format!("host:{host_id}"),
            name: hostname,
            attributes: json!({ "mount_count": mounts.len() }),
        };

        Ok(ParseResult {
            parsed,
            confidence: if mounts.is_empty() { 0.4 } else { 0.9 },
            asset_hint: Some(asset_hint),
            redactions: vec![],
        })
    }
}

fn flatten(node: &Value, out: &mut Vec<Value>) {
    out.push(json!({
        "target": node.get("target"),
        "source": node.get("source"),
        "fstype": node.get("fstype"),
        "options": node.get("options"),
    }));
    if let Some(children) = node.get("children").and_then(|v| v.as_array()) {
        for c in children {
            flatten(c, out);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"{"filesystems":[
      {"target":"/","source":"/dev/nvme0n1p2","fstype":"ext4","options":"rw,relatime",
       "children":[
         {"target":"/boot","source":"/dev/nvme0n1p1","fstype":"vfat","options":"rw"},
         {"target":"/sys","source":"sysfs","fstype":"sysfs","options":"rw,nosuid"}
       ]}
    ]}"#;

    #[test]
    fn flattens_tree_and_summarizes_real_fstypes() {
        let r = FindmntParser
            .parse(SAMPLE.as_bytes(), "util-linux", &json!({"hostname": "h"}))
            .unwrap();
        assert_eq!(r.parsed["summary"]["mount_count"], 3);
        let fstypes = r.parsed["summary"]["real_fstypes"].as_array().unwrap();
        // ext4 and vfat are real; sysfs is excluded as pseudo.
        assert!(fstypes.iter().any(|t| t == "ext4"));
        assert!(fstypes.iter().any(|t| t == "vfat"));
        assert!(!fstypes.iter().any(|t| t == "sysfs"));
        assert_eq!(r.parsed["mounts"][0]["target"], "/");
        assert!(r.confidence > 0.8);
    }
}
