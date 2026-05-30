package bundle

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestBuildProducesValidBundle(t *testing.T) {
	scope := Scope{Hostname: "host-a", HostUUID: "abc-123", OS: "linux"}
	items := []Item{
		{
			ID:                uuid.New(),
			SourceTool:        "lscpu",
			SourceToolVersion: "util-linux 2.39",
			Category:          "hardware",
			CollectedAt:       time.Now().UTC(),
			Raw:               []byte("Architecture: x86_64\nCPU(s): 16\n"),
		},
	}

	data, err := Build(scope, items)
	if err != nil {
		t.Fatalf("Build failed: %v", err)
	}

	gz, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("output is not gzip: %v", err)
	}
	tr := tar.NewReader(gz)

	var sawManifest, sawItem bool
	var manifestBytes []byte
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatalf("tar read error: %v", err)
		}
		switch {
		case hdr.Name == "manifest.json":
			sawManifest = true
			manifestBytes, _ = io.ReadAll(tr)
		case hdr.Name == items[0].File:
			sawItem = true
			body, _ := io.ReadAll(tr)
			if !bytes.Contains(body, []byte("Architecture")) {
				t.Errorf("item body not preserved: %q", body)
			}
		}
	}
	if !sawManifest {
		t.Error("bundle missing manifest.json")
	}
	if !sawItem {
		t.Error("bundle missing item raw file")
	}

	var manifest map[string]any
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		t.Fatalf("manifest is not valid JSON: %v", err)
	}
	if manifest["schema_version"] != SchemaVersion {
		t.Errorf("schema_version = %v, want %s", manifest["schema_version"], SchemaVersion)
	}
	if scopeMap, ok := manifest["scope"].(map[string]any); !ok || scopeMap["hostname"] != "host-a" {
		t.Errorf("scope not preserved in manifest: %v", manifest["scope"])
	}
}

func TestBuildAssignsItemIDAndPath(t *testing.T) {
	items := []Item{{SourceTool: "uname", Category: "inventory", Raw: []byte("Linux")}}
	if _, err := Build(Scope{Hostname: "h"}, items); err != nil {
		t.Fatalf("Build failed: %v", err)
	}
	if items[0].ID == uuid.Nil {
		t.Error("Build did not assign an ID to an item missing one")
	}
	if items[0].File == "" {
		t.Error("Build did not set the item file path")
	}
}
