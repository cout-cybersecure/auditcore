// Package bundle builds the evidence bundle tarball.
//
// Format:
//
//	manifest.json
//	items/<item_id>.raw
package bundle

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

const SchemaVersion = "1"
const CollectorVersion = "0.1.0"

// Item is one tool's raw output bound for ingestion.
type Item struct {
	ID                uuid.UUID `json:"id"`
	SourceTool        string    `json:"source_tool"`
	SourceToolVersion string    `json:"source_tool_version"`
	Category          string    `json:"category"`
	CollectedAt       time.Time `json:"collected_at"`
	File              string    `json:"file"`
	Raw               []byte    `json:"-"`
}

// Scope describes the environment the bundle was collected from.
type Scope struct {
	Hostname string `json:"hostname"`
	HostUUID string `json:"host_uuid"`
	OS       string `json:"os,omitempty"`
}

type manifest struct {
	SchemaVersion    string `json:"schema_version"`
	CollectorVersion string `json:"collector_version"`
	CollectedAt      string `json:"collected_at"`
	Scope            Scope  `json:"scope"`
	Items            []Item `json:"items"`
}

// Build assembles the items into a gzipped tar bundle.
func Build(scope Scope, items []Item) ([]byte, error) {
	now := time.Now().UTC()

	// Set the file path for each item.
	for i := range items {
		if items[i].ID == uuid.Nil {
			items[i].ID = uuid.New()
		}
		items[i].File = fmt.Sprintf("items/%s.raw", items[i].ID)
	}

	man := manifest{
		SchemaVersion:    SchemaVersion,
		CollectorVersion: CollectorVersion,
		CollectedAt:      now.Format(time.RFC3339),
		Scope:            scope,
		Items:            items,
	}

	manBytes, err := json.MarshalIndent(man, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("marshal manifest: %w", err)
	}

	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)

	if err := writeFile(tw, "manifest.json", manBytes, now); err != nil {
		return nil, err
	}
	for _, it := range items {
		if err := writeFile(tw, it.File, it.Raw, it.CollectedAt); err != nil {
			return nil, err
		}
	}

	if err := tw.Close(); err != nil {
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func writeFile(tw *tar.Writer, name string, data []byte, mtime time.Time) error {
	hdr := &tar.Header{
		Name:    name,
		Mode:    0o644,
		Size:    int64(len(data)),
		ModTime: mtime,
	}
	if err := tw.WriteHeader(hdr); err != nil {
		return fmt.Errorf("tar header %q: %w", name, err)
	}
	if _, err := tw.Write(data); err != nil {
		return fmt.Errorf("tar write %q: %w", name, err)
	}
	return nil
}
