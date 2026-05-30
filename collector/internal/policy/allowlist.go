// Package policy enforces the read-only command allowlist.
//
// In Phase 1 the allowlist is compiled in. Phase 3 ships an OPA bundle
// signed alongside the binary and loaded at startup.
package policy

import "fmt"

// AllowedCommand describes one safe-to-run tool invocation.
type AllowedCommand struct {
	Tool     string   // canonical tool name used in evidence
	Path     string   // executable name on PATH; resolved at runtime
	Args     []string // exact argv passed to the tool
	Category string   // matches EvidenceItem.category
}

// Phase 1 allowlist. Read-only Linux inventory and hardware facts.
// Every entry must be safe to run on a production host as a non-root user.
//
// `hwprobe` is the AuditCore-native C++ probe that emits a single JSON
// document covering NUMA, caches, PCI tree, and (when available) thermals
// and NVIDIA GPU inventory. It is searched on PATH and falls back to
// ./bin/hwprobe via the runner when not installed system-wide.
var Phase1 = []AllowedCommand{
	{Tool: "lscpu",   Path: "lscpu",   Args: []string{},              Category: "hardware"},
	{Tool: "lsblk",   Path: "lsblk",   Args: []string{"-J", "-O"},    Category: "hardware"},
	{Tool: "lspci",   Path: "lspci",   Args: []string{"-vmm"},        Category: "hardware"},
	{Tool: "uname",   Path: "uname",   Args: []string{"-a"},          Category: "inventory"},
	{Tool: "hwprobe", Path: "hwprobe", Args: []string{},              Category: "hardware"},
	// Network interfaces (addresses, MAC, MTU) — described by the hardware agent.
	{Tool: "ip",      Path: "ip",      Args: []string{"-j", "addr"},  Category: "hardware"},
	// Listening sockets (exposed services) — described by the security agent.
	{Tool: "ss",      Path: "ss",      Args: []string{"-tuln"},       Category: "security"},
}

// Lookup returns the allowlist entry for the named tool, or an error if
// the tool is not allowlisted.
func Lookup(tool string) (AllowedCommand, error) {
	for _, c := range Phase1 {
		if c.Tool == tool {
			return c, nil
		}
	}
	return AllowedCommand{}, fmt.Errorf("tool %q is not in the allowlist", tool)
}
