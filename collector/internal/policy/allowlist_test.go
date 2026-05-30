package policy

import "testing"

func TestLookupKnownTool(t *testing.T) {
	c, err := Lookup("lscpu")
	if err != nil {
		t.Fatalf("expected lscpu to be allowlisted, got error: %v", err)
	}
	if c.Tool != "lscpu" || c.Category != "hardware" {
		t.Fatalf("unexpected entry: %+v", c)
	}
}

func TestLookupUnknownToolRefused(t *testing.T) {
	if _, err := Lookup("rm"); err == nil {
		t.Fatal("expected 'rm' to be refused, but Lookup returned nil error")
	}
}

func TestEveryEntryIsWellFormed(t *testing.T) {
	seen := map[string]bool{}
	for _, c := range Phase1 {
		if c.Tool == "" || c.Path == "" || c.Category == "" {
			t.Errorf("entry has empty field: %+v", c)
		}
		if seen[c.Tool] {
			t.Errorf("duplicate tool in allowlist: %s", c.Tool)
		}
		seen[c.Tool] = true
	}
}

func TestExpectedToolsPresent(t *testing.T) {
	// The collector profile the normalizer + agents are built around.
	want := []string{"lscpu", "lsblk", "lspci", "uname", "hwprobe", "ip", "ss", "findmnt"}
	for _, tool := range want {
		if _, err := Lookup(tool); err != nil {
			t.Errorf("expected tool %q in allowlist: %v", tool, err)
		}
	}
}
