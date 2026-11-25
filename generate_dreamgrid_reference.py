#!/usr/bin/env python3
"""Package DreamGrid's local interpretation reference for an offline workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dreamgrid-data" / "interpretations.json"
DEFAULT_OUT = ROOT / "dreamgrid-reference"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate(data: dict) -> None:
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported schema version")
    if data.get("graph_policy", {}).get("may_create_edges") is not False:
        raise ValueError("Interpretations must never create graph connections")
    if data.get("graph_policy", {}).get("may_change_edge_scores") is not False:
        raise ValueError("Interpretations must not change edge scores")
    if data.get("provenance", {}).get("license") != "MIT":
        raise ValueError("Expected MIT-licensed original sample")
    symbols = data.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("Missing symbols")
    seen = set()
    for item in symbols:
        key = item.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in seen:
            raise ValueError(f"Invalid or duplicate symbol: {key!r}")
        seen.add(key)
        interpretations = item.get("interpretations")
        if not isinstance(interpretations, list) or not interpretations:
            raise ValueError(f"Missing interpretations for {key}")
        for entry in interpretations:
            if not entry.get("text") or not isinstance(entry.get("when"), dict):
                raise ValueError(f"Invalid interpretation for {key}")
            statuses = entry["when"].get("status", [])
            if not statuses or any(x not in data["status_vocabulary"] for x in statuses):
                raise ValueError(f"Invalid status guard for {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output folder for Taiga upload")
    parser.add_argument("--force", action="store_true", help="Replace an existing generated folder")
    args = parser.parse_args()

    out = args.out.expanduser().resolve()
    if out == ROOT.resolve() or out == SOURCE.parent.resolve() or out == SOURCE.resolve():
        parser.error("Refusing to replace source files or the repository")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    validate(data)

    # Normalized data and a reproducible manifest. No network or dependencies.
    contents = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    note = (
        "# DreamGrid interpretation reference\n\n"
        "Original illustrative English interpretations for testing a rule-based interface.\n"
        "Created for DreamGrid; no external interpretation dictionary text was copied.\n"
        "Licensed under MIT, as in the repository's root LICENSE.\n\n"
        "These interpretations are suggestions, not established meanings or diagnoses.\n"
        "Use this data to explain *existing* evidence-based links only. Never create or\n"
        "score graph edges from interpretations. Absent or uncertain evidence should\n"
        "not trigger the normal presence interpretations.\n\n"
        "Source: dreamgrid-data/interpretations.json\n"
        "Generator: generate_dreamgrid_reference.py\n"
        "Package format: v1\n"
    ).encode("utf-8")
    manifest = {
        "schema_version": 1,
        "source": "original-project-reference",
        "license": "MIT",
        "symbol_count": len(data["symbols"]),
        "interpretation_count": sum(len(s["interpretations"]) for s in data["symbols"]),
        "files": {
            "interpretations.json": sha256(contents),
            "SOURCE.md": sha256(note),
        },
    }
    file_map = {
        "interpretations.json": contents,
        "SOURCE.md": note,
        "manifest.json": (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
    }
    if out.exists() and not args.force:
        current = {name: (out / name).read_bytes() if (out / name).is_file() else None
                   for name in file_map}
        if current == file_map:
            print(f"Verified unchanged: {out}")
            return
        parser.error(f"Output exists: {out}. Use --force to replace it.")

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dreamgrid-stage-", dir=out.parent) as temp:
        stage = Path(temp) / "package"
        stage.mkdir()
        for name, content in file_map.items():
            (stage / name).write_bytes(content)
        for name, content in file_map.items():
            if (stage / name).read_bytes() != content:
                raise RuntimeError(f"Verification failed for {name}")
        if out.exists():
            # Only the selected generated output is replaced; astronomy files are untouched.
            shutil.rmtree(out)
        stage.rename(out)
    print(f"Generated {len(data['symbols'])} symbols in {out}")
    print("Upload the generated folder, including SOURCE.md and manifest.json.")


if __name__ == "__main__":
    main()
