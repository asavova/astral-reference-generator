#!/usr/bin/env python3
"""One-command runner: prepare dependencies, find/download HYG, generate and verify."""
from __future__ import annotations

import argparse
import csv
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
        with temporary.open(encoding="utf-8-sig", newline="") as file:
            header = next(csv.reader(file))
        if not {"id", "hip", "ra", "dec", "pmra", "pmdec", "dist", "rv"}.issubset(header):
            raise RuntimeError("Downloaded file is not an original HYG v4.1 catalogue")
        temporary.replace(destination)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise SystemExit(
            f"Couldn't download the catalogue: {exc}\n"
            "Download data/hygdata_v41.csv from the Astral Observatory repository, "
            "or run with --catalog /path/to/hygdata_v41.csv."
        ) from exc
    return destination


def python_in_venv(folder: Path) -> Path:
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, help="Use a local original HYG v4.1 CSV")
    parser.add_argument("--out", type=Path, default=ROOT / "references", help="Output directory")
    parser.add_argument("--count", type=int, default=400, help="Number of reference stars")
    parser.add_argument("--force", action="store_true", help="Replace existing reference files")
    args = parser.parse_args()

    output = args.out.expanduser().resolve()
    manifest = output / "manifest.json"
    if manifest.exists() and not args.force:
        print(f"Existing reference files found in {output}. Checking them without changing anything...")
        subprocess.run([sys.executable, str(ROOT / "verify.py"), str(output)], check=True)
        print("Use --force only if you intentionally want to regenerate the fixed reference files.")
        return

    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    source = get_catalog(args.catalog)
    print(f"Catalogue: {source}")

    env = ROOT / ".venv"
    interpreter = python_in_venv(env)
    if not interpreter.is_file():
        print("Creating local Python environment...")
        venv.EnvBuilder(with_pip=True).create(env)
    print("Installing pinned astronomy dependency...")
    subprocess.run([str(interpreter), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", str(ROOT / "requirements.txt")], check=True)
    print("Running generator tests...")
    subprocess.run([str(interpreter), "-m", "unittest", "discover", "-s", "tests", "-v"],
                   cwd=ROOT, check=True)
    print("Generating reference positions...")
    command = [str(interpreter), str(ROOT / "generate.py"), "--catalog", str(source),
               "--out", str(output), "--count", str(args.count)]
    if args.force:
        command.append("--force")
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([str(interpreter), str(ROOT / "verify.py"), str(output)], check=True)
    print(f"\nReference data is ready at: {output}")
    print("Keep these files unchanged for all Taiga coding turns.")


if __name__ == "__main__":
    main()
