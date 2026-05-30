package auditcore.collector

# Canonical read-only command allowlist. Mirror of collector/internal/policy
# Phase1. A drift check in CI keeps these two in sync.
#
# Each entry is { tool, path, args, category }. Argument matching is exact
# (set equality); pass-through user args are NOT permitted in Phase 1.

allowlist := [
    {"tool": "lscpu",   "path": "lscpu",   "args": [],            "category": "hardware"},
    {"tool": "lsblk",   "path": "lsblk",   "args": ["-J", "-O"],  "category": "hardware"},
    {"tool": "lspci",   "path": "lspci",   "args": ["-vmm"],      "category": "hardware"},
    {"tool": "uname",   "path": "uname",   "args": ["-a"],        "category": "inventory"},
    {"tool": "hwprobe", "path": "hwprobe", "args": [],            "category": "hardware"},
    {"tool": "ip",      "path": "ip",      "args": ["-j", "addr"], "category": "hardware"},
    {"tool": "ss",      "path": "ss",      "args": ["-tuln"],     "category": "security"},
    {"tool": "findmnt", "path": "findmnt", "args": ["-J"],        "category": "hardware"},
]

# Decision: { allowed: bool, reason?: string }
default decision := {"allowed": false, "reason": "tool not in allowlist"}

decision := {"allowed": true} if {
    some entry in allowlist
    entry.tool == input.tool
    entry.path == input.path
    sort(entry.args) == sort(input.args)
}

# Convenience predicate.
allow if decision.allowed
