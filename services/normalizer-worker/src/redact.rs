//! Secret redaction — the normalizer-side stage of AuditCore's two-stage
//! redaction. Runs over parsed evidence BEFORE it is persisted or ever sent to
//! a model. Each detected secret is replaced with a stable token
//! `REDACTED:<rule>:<hash>` so the same secret yields the same token (analysis
//! can still correlate on it) without ever exposing the value.
//!
//! This is a safety net, not a guarantee: redaction is best-effort pattern
//! matching. The collector performs the first stage; raw evidence in object
//! storage is access-controlled separately.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::sync::LazyLock;

use regex::Regex;
use serde_json::Value;

struct Rule {
    id: &'static str,
    re: Regex,
}

static RULES: LazyLock<Vec<Rule>> = LazyLock::new(|| {
    let p = |id, pat: &str| Rule {
        id,
        re: Regex::new(pat).unwrap(),
    };
    vec![
        // AWS access key id.
        p("aws_access_key_id", r"AKIA[0-9A-Z]{16}"),
        // AWS secret access key in an assignment context.
        p(
            "aws_secret_access_key",
            r"(?i)aws_secret_access_key\s*[=:]\s*[A-Za-z0-9/+]{40}",
        ),
        // PEM private key block (header alone is enough to flag).
        p(
            "private_key_pem",
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        ),
        // JWT (three base64url segments).
        p(
            "jwt",
            r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}",
        ),
        // Bearer token.
        p("bearer_token", r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
        // GitHub personal access token.
        p("github_pat", r"ghp_[A-Za-z0-9]{36}"),
        // Slack token.
        p("slack_token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
        // password=... / passwd:... assignments (value up to whitespace/quote).
        p(
            "password_assignment",
            r#"(?i)(?:password|passwd|pwd)\s*[=:]\s*[^\s"']{6,}"#,
        ),
        // Generic high-entropy token in an api_key/secret/token assignment.
        p(
            "generic_secret_assignment",
            r#"(?i)(?:api[_-]?key|secret|token)\s*[=:]\s*[A-Za-z0-9/+_\-]{16,}"#,
        ),
    ]
});

/// Redact a single string. Returns the redacted string and the rule ids applied.
fn redact_str(input: &str) -> (String, Vec<&'static str>) {
    let mut out = input.to_string();
    let mut applied: Vec<&'static str> = Vec::new();
    for rule in RULES.iter() {
        if rule.re.is_match(&out) {
            out = rule
                .re
                .replace_all(&out, |caps: &regex::Captures| {
                    format!("REDACTED:{}:{}", rule.id, stable_hash(&caps[0]))
                })
                .into_owned();
            applied.push(rule.id);
        }
    }
    (out, applied)
}

/// Walk a JSON value, redacting every string leaf in place. Returns the sorted,
/// de-duplicated set of rule ids that fired anywhere in the tree.
pub fn redact_value(value: &mut Value) -> Vec<String> {
    let mut applied: Vec<&'static str> = Vec::new();
    walk(value, &mut applied);
    applied.sort_unstable();
    applied.dedup();
    applied.into_iter().map(String::from).collect()
}

fn walk(value: &mut Value, applied: &mut Vec<&'static str>) {
    match value {
        Value::String(s) => {
            let (red, ids) = redact_str(s);
            if !ids.is_empty() {
                *s = red;
                applied.extend(ids);
            }
        }
        Value::Array(arr) => arr.iter_mut().for_each(|v| walk(v, applied)),
        Value::Object(map) => map.iter_mut().for_each(|(_, v)| walk(v, applied)),
        _ => {}
    }
}

fn stable_hash(s: &str) -> String {
    // Deterministic, non-cryptographic — only a correlation handle, never the value.
    let mut h = DefaultHasher::new();
    s.hash(&mut h);
    format!("{:08x}", h.finish() & 0xffff_ffff)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn redacts_aws_key_and_records_rule() {
        let (out, ids) = redact_str("key is AKIAIOSFODNN7EXAMPLE here");
        assert!(!out.contains("AKIAIOSFODNN7EXAMPLE"));
        assert!(out.contains("REDACTED:aws_access_key_id:"));
        assert_eq!(ids, vec!["aws_access_key_id"]);
    }

    #[test]
    fn redacts_private_key_header() {
        let (out, ids) = redact_str("-----BEGIN OPENSSH PRIVATE KEY-----");
        assert!(out.contains("REDACTED:private_key_pem:"));
        assert_eq!(ids, vec!["private_key_pem"]);
    }

    #[test]
    fn same_secret_yields_same_token() {
        let (a, _) = redact_str("AKIAIOSFODNN7EXAMPLE");
        let (b, _) = redact_str("AKIAIOSFODNN7EXAMPLE");
        assert_eq!(a, b);
    }

    #[test]
    fn walks_nested_json() {
        let mut v = json!({
            "config": {"token": "ghp_012345678901234567890123456789012345"},
            "list": ["password=hunter2supersecret", "harmless"]
        });
        let ids = redact_value(&mut v);
        assert!(ids.contains(&"github_pat".to_string()));
        assert!(ids.contains(&"password_assignment".to_string()));
        assert!(!serde_json::to_string(&v)
            .unwrap()
            .contains("ghp_0123456789"));
        assert_eq!(v["list"][1], "harmless");
    }

    #[test]
    fn clean_input_reports_nothing() {
        let mut v = json!({"cpus": 16, "model": "Xeon Gold 6226R"});
        assert!(redact_value(&mut v).is_empty());
    }
}
