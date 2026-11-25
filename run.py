#!/usr/bin/env python3
"""One command: find/download HYG, install PyERFA, generate and verify references."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_URL = (
    "https://raw.githubusercontent.com/asavova/astral-observatory/"
    "main/data/hygdata_v41.csv"
)


def get_catalog(explicit: Path | None) -> Path:
    if explicit is not None:
        source = explicit.expanduser().resolve()
        if not source.is_file():
            raise SystemExit(f"Catalogue file does not exist: {source}")
        return source

    for candidate in (
        ROOT.parent / "astral-observatory" / "data" / "hygdata_v41.csv",
        ROOT / "data" / "hygdata_v41.csv",
        ROOT / "cache" / "hygdata_v41.csv",
    ):
        if candidate.is_file():
            return candidate

    destination = ROOT / "cache" / "hygdata_v41.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".part")
    print("Downloading the original HYG v4.1 catalogue from Astral Observatory...")
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=90) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if temporary.stat().st_size < 30_000_000:
            raise RuntimeError("Catalogue download is unexpectedly small")
        with temporary.open(encoding="utf-8-sig", newline="") as fh:
            header = next(csv.reader(fh))
        required = {"id", "hip", "ra", "dec", "pmra", "pmdec", "dist", "rv"}
        if not required.issubset(header):
            raise RuntimeError("Downloaded file is not the original HYG v4.1 catalogue")
        temporary.replace(destination)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise SystemExit(
            f"Couldn't download the catalogue: {exc}\n"
            "Pass --catalog /path/to/hygdata_v41.csv or clone Astral Observatory beside this repo."
        ) from exc
    return destination


def python_in_venv(folder: Path) -> Path:
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, help="Use an existing HYG v4.1 CSV file")
    parser.add_argument("--out", type=Path, default=ROOT / "references",
                        help="Final reference directory")
    parser.add_argument("--count", default="all",
                        help="Generate for all usable stars (default) or select N stars")
    parser.add_argument("--force", action="store_true", help="Replace existing reference data")
    options = parser.parse_args()

    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    count = options.count.lower()
    if count != "all":
        try:
            if int(count) < 1:
                raise ValueError()
        except ValueError as exc:
            raise SystemExit("--count must be 'all' or a positive integer") from exc

    output = options.out.expanduser().resolve()
    manifest = output / "manifest.json"
    if manifest.exists() and not options.force:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        selection = data.get("selection", {})
        compatible = (count == "all" and selection.get("mode") == "all") or (
            count != "all" and selection.get("mode") == "sample"
            and selection.get("stars") == int(count))
        if not compatible:
            raise SystemExit(
                "Existing reference files were generated with a different star count. "
                "Use --force to generate the requested set."
            )
        print(f"Existing reference files found in {output}; checking without changing them.")
        subprocess.run([sys.executable, str(ROOT / "verify.py"), str(output)], check=True)
        print("Reference files match the saved checksums.")
        return

    source = get_catalog(options.catalog)
    print(f"Catalogue: {source}")
    env = ROOT / ".venv"
    interpreter = python_in_venv(env)
    if not interpreter.is_file():
        print("Creating Python virtual environment...")
        venv.EnvBuilder(with_pip=True).create(env)
    print("Installing pinned astronomy dependencies...")
    subprocess.run([str(interpreter), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", str(ROOT / "requirements.txt")], check=True)
    print("Running generator tests...")
    subprocess.run([str(interpreter), "-m", "unittest", "discover", "-s", "tests", "-v"],
                   cwd=ROOT, check=True)

    # Build into a new directory, verify the result, then publish it.
    # A failed calculation must not overwrite the fixed reference data.
    staging = output.with_name(output.name + ".incomplete")
    backup = output.with_name(output.name + ".previous")
    if staging.exists() or backup.exists():
        raise SystemExit(
            f"An earlier staging/backup directory exists. Check {staging} and {backup} "
            "before retrying; no reference files were overwritten."
        )
    if output.exists() and not options.force and any(output.iterdir()):
        raise SystemExit(
            f"{output} already contains files. Use --force to replace them."
        )

    staging.mkdir(parents=True)
    print("Generating independent reference positions...")
    command = [
        str(interpreter), str(ROOT / "generate.py"), "--catalog", str(source),
        "--out", str(staging), "--count", count,
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([str(interpreter), str(ROOT / "verify.py"), str(staging)], check=True)

    if output.exists():
        output.rename(backup)
    try:
        staging.rename(output)
    except Exception:
        if backup.exists() and not output.exists():
            backup.rename(output)
        raise
    if backup.exists():
        shutil.rmtree(backup)

    print(f"\nReference data is ready at: {output}")
    print("Keep these files unchanged across coding turns.")


if __name__ == "__main__":
    main()
