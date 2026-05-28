// auditor-collect is the AuditCore client-side collector.
//
// Usage:
//
//	auditor-collect run --upload http://localhost:8000
//	auditor-collect run --output ./bundle.tar.gz       # offline mode
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/google/uuid"

	"github.com/auditcore/collector/internal/policy"
	"github.com/auditcore/collector/internal/runner"
	"github.com/auditcore/collector/pkg/bundle"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "run":
		if err := runCmd(os.Args[2:]); err != nil {
			log.Fatalf("collector: %v", err)
		}
	case "list-tools":
		for _, c := range policy.Phase1 {
			fmt.Printf("%-8s  %-20s  %s\n", c.Category, c.Tool, c.Path)
		}
	case "-h", "--help", "help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand: %s\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "Usage: auditor-collect <run|list-tools|help> [flags]")
}

func runCmd(args []string) error {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	upload := fs.String("upload", "", "ingestion-api base URL (mutually exclusive with --output)")
	output := fs.String("output", "", "write bundle to this path instead of uploading")
	tools := fs.String("tools", "", "comma-separated tool names to run (default: all allowlisted)")
	timeout := fs.Duration("timeout", 60*time.Second, "per-tool timeout")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *upload == "" && *output == "" {
		return errors.New("either --upload or --output is required")
	}
	if *upload != "" && *output != "" {
		return errors.New("--upload and --output are mutually exclusive")
	}

	selected := selectTools(*tools)
	if len(selected) == 0 {
		return errors.New("no tools selected")
	}

	hostname, _ := os.Hostname()
	scope := bundle.Scope{
		Hostname: hostname,
		HostUUID: stableHostUUID(hostname),
		OS:       "linux",
	}

	ctx := context.Background()
	var items []bundle.Item
	for _, t := range selected {
		log.Printf("running %s", t)
		res, err := runner.Run(ctx, t, *timeout)
		if err != nil {
			var miss *runner.MissingToolError
			if errors.As(err, &miss) {
				log.Printf("  skip: %v", err)
				continue
			}
			return fmt.Errorf("run %s: %w", t, err)
		}
		if res.ExitCode != 0 {
			log.Printf("  warn: %s exited %d (stderr=%q)", t, res.ExitCode, truncate(res.Stderr, 200))
		}
		items = append(items, bundle.Item{
			ID:                uuid.New(),
			SourceTool:        res.Tool,
			SourceToolVersion: res.ToolVersion,
			Category:          res.Category,
			CollectedAt:       res.StartedAt.UTC(),
			Raw:               res.Raw,
		})
	}

	if len(items) == 0 {
		return errors.New("no tools produced output; nothing to upload")
	}

	tarball, err := bundle.Build(scope, items)
	if err != nil {
		return fmt.Errorf("build bundle: %w", err)
	}
	log.Printf("bundle: %d items, %.1f KiB", len(items), float64(len(tarball))/1024.0)

	if *output != "" {
		if err := os.WriteFile(*output, tarball, 0o600); err != nil {
			return fmt.Errorf("write bundle: %w", err)
		}
		log.Printf("wrote %s", *output)
		return nil
	}

	c := bundle.NewClient(*upload)
	runID, err := c.CreateRun(map[string]any{
		"hostname":  scope.Hostname,
		"host_uuid": scope.HostUUID,
	})
	if err != nil {
		return fmt.Errorf("create run: %w", err)
	}
	log.Printf("created run %s", runID)

	if err := c.UploadBundle(runID, tarball); err != nil {
		return fmt.Errorf("upload bundle: %w", err)
	}
	log.Printf("uploaded bundle for run %s", runID)
	return nil
}

func selectTools(csv string) []string {
	if csv == "" {
		out := make([]string, 0, len(policy.Phase1))
		for _, c := range policy.Phase1 {
			out = append(out, c.Tool)
		}
		return out
	}
	var out []string
	for _, t := range splitCSV(csv) {
		if _, err := policy.Lookup(t); err != nil {
			log.Printf("ignoring non-allowlisted tool: %s", t)
			continue
		}
		out = append(out, t)
	}
	return out
}

func splitCSV(s string) []string {
	var out []string
	start := 0
	for i := 0; i <= len(s); i++ {
		if i == len(s) || s[i] == ',' {
			if i > start {
				out = append(out, s[start:i])
			}
			start = i + 1
		}
	}
	return out
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "…"
}

// stableHostUUID derives a deterministic UUID from hostname for v0.
// Phase 2 will read /etc/machine-id or DMI UUID.
func stableHostUUID(hostname string) string {
	return uuid.NewSHA1(uuid.NameSpaceDNS, []byte(hostname)).String()
}
