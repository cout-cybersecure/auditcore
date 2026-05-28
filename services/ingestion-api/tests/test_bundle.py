"""Tests for bundle parsing — uses Python tarfile to fabricate bundles."""
from __future__ import annotations

import io
import json
import tarfile
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from auditcore_ingestion import bundle


def _make_bundle(items: list[dict], manifest_extra: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        manifest_items = []
        for item in items:
            item_id = item["id"]
            file_path = f"items/{item_id}.raw"
            raw = item.pop("raw", b"")
            ti = tarfile.TarInfo(file_path)
            ti.size = len(raw)
            tf.addfile(ti, io.BytesIO(raw))
            manifest_items.append({**item, "file": file_path})

        manifest = {
            "schema_version": "1",
            "collector_version": "0.1.0",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scope": {"hostname": "host-a", "host_uuid": "deadbeef"},
            "items": manifest_items,
        }
        if manifest_extra:
            manifest.update(manifest_extra)

        man_bytes = json.dumps(manifest).encode()
        ti = tarfile.TarInfo("manifest.json")
        ti.size = len(man_bytes)
        tf.addfile(ti, io.BytesIO(man_bytes))
    return buf.getvalue()


def test_parses_well_formed_bundle():
    item_id = str(uuid4())
    data = _make_bundle([{
        "id": item_id,
        "source_tool": "lscpu",
        "source_tool_version": "util-linux 2.39.3",
        "category": "hardware",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "raw": b"Architecture: x86_64\nCPU(s): 8\n",
    }])

    b = bundle.parse_bundle(data)
    assert len(b.items) == 1
    assert b.items[0].source_tool == "lscpu"
    assert b.items[0].raw_bytes.startswith(b"Architecture:")
    assert b.scope["hostname"] == "host-a"


def test_rejects_non_targz():
    with pytest.raises(bundle.BundleError, match="not a valid tar.gz"):
        bundle.parse_bundle(b"not a tarball at all")


def test_rejects_missing_manifest():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo("items/something.raw")
        ti.size = 4
        tf.addfile(ti, io.BytesIO(b"data"))
    with pytest.raises(bundle.BundleError, match="missing manifest.json"):
        bundle.parse_bundle(buf.getvalue())


def test_rejects_path_traversal():
    item_id = str(uuid4())
    data = _make_bundle([{
        "id": item_id,
        "source_tool": "lscpu",
        "source_tool_version": "x",
        "category": "hardware",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "raw": b"x",
    }])
    # Mutate the manifest to reference a traversal path. We rebuild rather than
    # mutating bytes because the manifest is inside the tar.
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        manifest = json.loads(tf.extractfile("manifest.json").read())
        manifest["items"][0]["file"] = "../etc/passwd"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo("../etc/passwd")
        ti.size = 4
        tf.addfile(ti, io.BytesIO(b"data"))
        man_bytes = json.dumps(manifest).encode()
        ti = tarfile.TarInfo("manifest.json")
        ti.size = len(man_bytes)
        tf.addfile(ti, io.BytesIO(man_bytes))

    with pytest.raises(bundle.BundleError, match="unsafe bundle path"):
        bundle.parse_bundle(buf.getvalue())
