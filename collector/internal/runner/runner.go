// Package runner executes allowlisted tools and captures raw output.
package runner

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/auditcore/collector/internal/policy"
)

// Result is the raw outcome of a single tool run.
type Result struct {
	Tool        string
	ToolVersion string
	Category    string
	StartedAt   time.Time
	Duration    time.Duration
	ExitCode    int
	Raw         []byte // stdout
	Stderr      []byte
}

// Run resolves the tool in the allowlist, executes it, and returns the result.
// Refuses to run anything not in the allowlist.
func Run(ctx context.Context, tool string, timeout time.Duration) (*Result, error) {
	cmd, err := policy.Lookup(tool)
	if err != nil {
		return nil, err
	}

	resolved, err := resolvePath(cmd.Path)
	if err != nil {
		return nil, &MissingToolError{Tool: tool, Underlying: err}
	}

	cctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	var stdout, stderr bytes.Buffer
	c := exec.CommandContext(cctx, resolved, cmd.Args...)
	c.Stdout = &stdout
	c.Stderr = &stderr

	start := time.Now()
	err = c.Run()
	dur := time.Since(start)

	exitCode := 0
	if err != nil {
		var ee *exec.ExitError
		if errors.As(err, &ee) {
			exitCode = ee.ExitCode()
		} else {
			return nil, err
		}
	}

	return &Result{
		Tool:        cmd.Tool,
		ToolVersion: detectVersion(resolved),
		Category:    cmd.Category,
		StartedAt:   start,
		Duration:    dur,
		ExitCode:    exitCode,
		Raw:         stdout.Bytes(),
		Stderr:      stderr.Bytes(),
	}, nil
}

// MissingToolError indicates the allowlisted tool is not present on the host.
type MissingToolError struct {
	Tool       string
	Underlying error
}

func (e *MissingToolError) Error() string {
	return "tool not present on host: " + e.Tool + " (" + e.Underlying.Error() + ")"
}

// detectVersion runs `<tool> --version` and returns the first line trimmed.
// Best-effort; returns "unknown" on failure.
func detectVersion(path string) string {
	c := exec.Command(path, "--version")
	out, err := c.CombinedOutput()
	if err != nil {
		return "unknown"
	}
	line := strings.SplitN(strings.TrimSpace(string(out)), "\n", 2)[0]
	return line
}

// resolvePath looks up an executable in $PATH and falls back to a sibling
// `bin/<name>` next to the running collector. This lets AuditCore-native
// tools (like hwprobe) ship alongside the collector without polluting PATH.
func resolvePath(name string) (string, error) {
	if p, err := exec.LookPath(name); err == nil {
		return p, nil
	}
	if self, err := os.Executable(); err == nil {
		candidate := filepath.Join(filepath.Dir(self), name)
		if fi, statErr := os.Stat(candidate); statErr == nil && !fi.IsDir() {
			return candidate, nil
		}
	}
	return "", &exec.Error{Name: name, Err: exec.ErrNotFound}
}
