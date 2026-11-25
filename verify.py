#!/usr/bin/env python3
"""Verify fixed reference fixtures without installing astronomy software."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(root: Path):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != "astral-reference-v1":
        raise ValueError("Wrong fixture schema")
    for name, checksum in manifest["file_sha256"].items():
        path = root / name
        if sha256(path) != checksum:
            raise ValueError(f"SHA-256 mismatch: {name}")
    for name, expected in (("cirs_positions.csv", manifest["counts"]["cirs_rows"]),
                           ("observed_altaz.csv", manifest["counts"]["altaz_rows"]),
                           ("selected_stars.csv", manifest["selection"]["stars"])):
        with (root / name).open(encoding="utf-8", newline="") as fh:
            n = sum(1 for _ in csv.DictReader(fh))
        if n != expected:
            raise ValueError(f"Row count mismatch in {name}: {n} != {expected}")
    print("Reference files verified: SHA-256 checksums and row counts match the manifest.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", nargs="?", type=Path, default=Path("references"))
    verify(p.parse_args().path)
