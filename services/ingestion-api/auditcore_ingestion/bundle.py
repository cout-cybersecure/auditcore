"""Evidence bundle format + extraction.

A bundle is a tar.gz with:
    manifest.json
    items/<item_id>.raw
"""
from __future__ import annotations

import io
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


class BundleError(Exception):
    pass


@dataclass(frozen=True)
class BundleItem:
    id: UUID
    source_tool: str
    source_tool_version: str
    category: str
    collected_at: datetime
    file_path: str          # path inside the tar (e.g. "items/<id>.raw")
    raw_bytes: bytes        # raw tool output


@dataclass(frozen=True)
class Bundle:
    schema_version: str
    collector_version: str
    collected_at: datetime
    scope: dict[str, Any]
    items: list[BundleItem]


def parse_bundle(data: bytes) -> Bundle:
    """Parse a tar.gz bundle into typed items. Raises BundleError on malformed input."""
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except tarfile.TarError as e:
        raise BundleError(f"not a valid tar.gz: {e}") from e

    try:
        manifest_member = tf.getmember("manifest.json")
    except KeyError:
        raise BundleError("bundle missing manifest.json") from None

    manifest_file = tf.extractfile(manifest_member)
    if manifest_file is None:
        raise BundleError("manifest.json is not a regular file")
    try:
        manifest = json.loads(manifest_file.read())
    except json.JSONDecodeError as e:
        raise BundleError(f"manifest.json is not valid JSON: {e}") from e

    required_top = {"schema_version", "collector_version", "collected_at", "scope", "items"}
    missing = required_top - manifest.keys()
    if missing:
        raise BundleError(f"manifest missing keys: {sorted(missing)}")

    items: list[BundleItem] = []
    for raw in manifest["items"]:
        required_item = {
            "id", "source_tool", "source_tool_version",
            "category", "collected_at", "file",
        }
        if required_item - raw.keys():
            raise BundleError(f"item missing keys: {sorted(required_item - raw.keys())}")

        try:
            member = tf.getmember(raw["file"])
        except KeyError:
            raise BundleError(f"manifest references missing file: {raw['file']}") from None
        # Reject path traversal: members must be inside items/ and not absolute.
        if member.name.startswith("/") or ".." in member.name.split("/"):
            raise BundleError(f"unsafe bundle path: {member.name}")

        f = tf.extractfile(member)
        if f is None:
            raise BundleError(f"bundle path is not a regular file: {member.name}")

        items.append(
            BundleItem(
                id=UUID(raw["id"]),
                source_tool=raw["source_tool"],
                source_tool_version=raw["source_tool_version"],
                category=raw["category"],
                collected_at=datetime.fromisoformat(raw["collected_at"]),
                file_path=raw["file"],
                raw_bytes=f.read(),
            )
        )

    return Bundle(
        schema_version=str(manifest["schema_version"]),
        collector_version=str(manifest["collector_version"]),
        collected_at=datetime.fromisoformat(manifest["collected_at"]),
        scope=manifest["scope"],
        items=items,
    )
