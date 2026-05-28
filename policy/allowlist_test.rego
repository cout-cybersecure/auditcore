package auditcore.collector

# Allowed: exact match.
test_allows_lscpu if {
    decision.allowed
        with input as {"tool": "lscpu", "path": "lscpu", "args": []}
}

test_allows_lsblk_with_correct_args if {
    decision.allowed
        with input as {"tool": "lsblk", "path": "lsblk", "args": ["-J", "-O"]}
}

# Wrong args -> deny.
test_denies_lscpu_with_extra_args if {
    not decision.allowed
        with input as {"tool": "lscpu", "path": "lscpu", "args": ["--bogus"]}
}

# Unknown tool -> deny.
test_denies_unknown_tool if {
    not decision.allowed
        with input as {"tool": "rm", "path": "rm", "args": ["-rf", "/"]}
}

# Path mismatch -> deny (foils symlink-rename attacks).
test_denies_path_mismatch if {
    not decision.allowed
        with input as {"tool": "lscpu", "path": "/tmp/fake/lscpu", "args": []}
}
