package bundle

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"time"
)

// Client talks to the ingestion-api.
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

// NewClient returns a Client with a 5-minute timeout suitable for bundle uploads.
func NewClient(baseURL string) *Client {
	return &Client{
		BaseURL: baseURL,
		HTTP:    &http.Client{Timeout: 5 * time.Minute},
	}
}

// CreateRun starts a new run on the server and returns its ID.
func (c *Client) CreateRun(scope map[string]any) (string, error) {
	body, _ := json.Marshal(map[string]any{"scope": scope})
	req, err := http.NewRequest(http.MethodPost, c.BaseURL+"/v1/runs", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("create run: %s: %s", resp.Status, string(b))
	}
	var out struct {
		RunID  string `json:"run_id"`
		Status string `json:"status"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", err
	}
	return out.RunID, nil
}

// UploadBundle posts the gzipped tarball as multipart/form-data.
func (c *Client) UploadBundle(runID string, tarball []byte) error {
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	w, err := mw.CreateFormFile("bundle_file", "bundle.tar.gz")
	if err != nil {
		return err
	}
	if _, err := w.Write(tarball); err != nil {
		return err
	}
	if err := mw.Close(); err != nil {
		return err
	}

	url := fmt.Sprintf("%s/v1/runs/%s/bundle", c.BaseURL, runID)
	req, err := http.NewRequest(http.MethodPost, url, &buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("upload bundle: %s: %s", resp.Status, string(b))
	}
	return nil
}
