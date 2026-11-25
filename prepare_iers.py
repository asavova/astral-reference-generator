#!/usr/bin/env python3
"""Prepare official IERS EOP observations and forecasts for an offline application."""
import argparse
import hashlib
import ssl
import subprocess
import sys
import urllib.error
import json
import shutil
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URLS = {
    'eopc04_20u24.1962-now.csv': 'https://datacenter.iers.org/products/eop/long-term/c04_20u24/csv/eopc04_20u24.1962-now.csv',
    'finals2000A.all': 'https://maia.usno.navy.mil/ser7/finals2000A.all',
}
FINAL_FALLBACK = 'https://datacenter.iers.org/data/9/finals2000A.all'
SOURCE_NOTE = '''# IERS Earth-orientation data — offline copy

These are unchanged source files from IERS/USNO, not calculated star positions.

- eopc04_20u24.1962-now.csv: official daily C04 Earth-orientation observations, from 1962; includes polar motion and UT1-UTC. See the actual CSV header for units.
- finals2000A.all: official USNO/IERS rapid data and short-term forecasts; predicted entries must not be mistaken for observations.
- manifest.json: source URLs, download timestamp and SHA-256 checksums.

No measured IERS values are provided for 1800–1961 or the distant future to 2200. Use a labelled mathematical model outside observed coverage. Before 1972, UTC also differs from modern leap-second UTC.

Sources: https://datacenter.iers.org/eop.php and https://maia.usno.navy.mil/products/bulletin-a.htm . Credit IERS and USNO when distributing. No endorsement is implied.
'''


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def validate_source(path, filename):
    if path.stat().st_size < 100000:
        raise ValueError(f'{filename} is suspiciously small: {path.stat().st_size} bytes')
    with path.open('rb') as f:
        head = f.read(10000)
    if b'<html' in head.lower() or b'<!doctype' in head.lower():
        raise ValueError(f'{filename} is HTML, not data')
    if filename.endswith('.csv') and not (b'MJD' in head.upper() and b'UT1' in head.upper()):
        raise ValueError('Unexpected C04 CSV header (no MJD and UT1 columns)')
    if filename == 'finals2000A.all' and not any(
        len(line) > 80 and b'.' in line and any(48 <= c <= 57 for c in line[:15])
        for line in head.splitlines()
    ):
        raise ValueError('Unexpected finals2000A fixed-width format')


def verify(folder):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'iers-bundle-v1':
        raise ValueError('Unexpected manifest format')
    for name, record in manifest['files'].items():
        if not (folder/name).is_file() or sha256(folder/name) != record['sha256']:
            raise ValueError(f'Missing or modified data file: {name}')
    return manifest


def download(url, path):
    request = urllib.request.Request(url, headers={'User-Agent': 'astral-reference-generator/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, path.open('wb') as output:
            shutil.copyfileobj(response, output)
    except urllib.error.URLError as error:
        reason = getattr(error, 'reason', None)
        certificate_error = isinstance(reason, ssl.SSLCertVerificationError) or (
            'CERTIFICATE_VERIFY_FAILED' in str(error)
        )
        if not (certificate_error and sys.platform == 'win32'):
            raise
        # Windows curl normally uses the Windows certificate store (Schannel).
        # Keep HTTPS certificate verification enabled. Never use curl -k.
        print('Python could not verify the HTTPS certificate; retrying with Windows curl.', flush=True)
        path.unlink(missing_ok=True)
        subprocess.run(
            ['curl.exe', '--fail', '--location', '--show-error',
             '--silent', '--output', str(path), url],
            check=True,
        )


def make_archive(folder, archive):
    tmp = archive.with_suffix('.tar.gz.part')
    try:
        with tarfile.open(tmp, 'w:gz') as tar:
            for file in sorted(folder.iterdir()):
                if file.is_file():
                    tar.add(file, arcname=f'iers-data/{file.name}')
        tmp.replace(archive)
    finally:
        tmp.unlink(missing_ok=True)


def prepare(folder, c04_file=None, finals_file=None, force=False):
    folder = Path(folder).expanduser().resolve()
    archive = folder.with_name(folder.name + '.tar.gz')
    if folder.exists() and not force:
        verify(folder)
        if not archive.is_file():
            make_archive(folder, archive)
        print(f'Existing IERS data verified: {archive}')
        return archive
    folder.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='iers-build-', dir=folder.parent) as temp:
        stage = Path(temp)/'iers-data'
        stage.mkdir()
        entries = {}
        for name, official_url in URLS.items():
            out = stage/name
            supplied = c04_file if name.endswith('.csv') else finals_file
            if supplied is not None:
                supplied = Path(supplied)
                shutil.copyfile(supplied, out)
                retrieved_from = str(supplied.resolve())
            else:
                urls = [official_url] + ([FINAL_FALLBACK] if name.endswith('.all') else [])
                for index, url in enumerate(urls):
                    try:
                        print(f'Downloading {name} from {url}', flush=True)
                        download(url, out)
                        retrieved_from = url
                        break
                    except Exception as error:
                        out.unlink(missing_ok=True)
                        if index == len(urls)-1:
                            raise RuntimeError(
                                f'Could not retrieve {name}. For SSL errors, download the official '
                                'files using your browser and provide them with --c04-file and '
                                '--finals-file. Do not disable certificate verification.'
                            ) from error
            validate_source(out, name)
            entries[name] = {'official_url':official_url, 'retrieved_from':retrieved_from,
                             'sha256':sha256(out), 'bytes':out.stat().st_size}
        (stage/'DATA_SOURCE.md').write_text(SOURCE_NOTE, encoding='utf-8')
        entries['DATA_SOURCE.md'] = {'sha256':sha256(stage/'DATA_SOURCE.md')}
        metadata = {'schema':'iers-bundle-v1',
                    'downloaded_utc':datetime.now(timezone.utc).isoformat(),
                    'files':entries, 'coverage':'Observed C04 from 1962; Bulletin A short-term predictions only; no observed values for 1800–1961 or 2200'}
        (stage/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n',encoding='utf-8')
        verify(stage)
        backup = folder.with_name(folder.name+'.previous')
        if backup.exists():
            raise RuntimeError(f'Previous backup exists: {backup}')
        if folder.exists():
            folder.rename(backup)
        try:
            stage.rename(folder)
            make_archive(folder, archive)
        except Exception:
            if backup.exists():
                if folder.exists(): shutil.rmtree(folder)
                backup.rename(folder)
            raise
        if backup.exists(): shutil.rmtree(backup)
    print(f'IERS data bundle ready: {archive}')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'iers-data')
    parser.add_argument('--c04-file',type=Path,help='Use a previously downloaded C04 CSV')
    parser.add_argument('--finals-file',type=Path,help='Use a previously downloaded finals2000A.all')
    parser.add_argument('--force',action='store_true',help='Replace existing data after validating new copy')
    a=parser.parse_args()
    prepare(a.out,a.c04_file,a.finals_file,a.force)


if __name__ == '__main__': main()
