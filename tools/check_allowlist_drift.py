"""Fail if collector/internal/policy/allowlist.go and policy/allowlist.rego disagree.

We parse both files with light regex — neither is large enough to warrant a
real Go/Rego parser. Both files have hand-formatted, table-shaped definitions
that this script is designed against.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GO_FILE = REPO / "collector" / "internal" / "policy" / "allowlist.go"
REGO_FILE = REPO / "policy" / "allowlist.rego"


def parse_go() -> set[tuple[str, str, tuple[str, ...], str]]:
    text = GO_FILE.read_text()
    entries: set[tuple[str, str, tuple[str, ...], str]] = set()
    # Match: {Tool: "x", Path: "y", Args: []string{...}, Category: "z"}
    line_re = re.compile(
        r'\{Tool:\s*"([^"]+)",\s*Path:\s*"([^"]+)",\s*'
        r'Args:\s*\[\]string\{([^}]*)\},\s*'
        r'Category:\s*"([^"]+)"\}',
    )
    for tool, path, args_raw, cat in line_re.findall(text):
        args = tuple(re.findall(r'"([^"]*)"', args_raw))
        entries.add((tool, path, args, cat))
    return entries


def parse_rego() -> set[tuple[str, str, tuple[str, ...], str]]:
    text = REGO_FILE.read_text()
    entries: set[tuple[str, str, tuple[str, ...], str]] = set()
    line_re = re.compile(
        r'\{"tool":\s*"([^"]+)",\s*"path":\s*"([^"]+)",\s*'
        r'"args":\s*\[([^\]]*)\],\s*"category":\s*"([^"]+)"\}',
    )
    for tool, path, args_raw, cat in line_re.findall(text):
        args = tuple(re.findall(r'"([^"]*)"', args_raw))
        entries.add((tool, path, args, cat))
    return entries


def main() -> int:
    go = parse_go()
    rego = parse_rego()
    if go == rego:
        print(f"allowlist drift check ok ({len(go)} entries match)")
        return 0
    only_go = sorted(go - rego)
    only_rego = sorted(rego - go)
    print("ERROR: allowlist drift between Go and Rego:")
    for e in only_go:
        print(f"  only in Go:   {e}")
    for e in only_rego:
        print(f"  only in Rego: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
