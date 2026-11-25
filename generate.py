#!/usr/bin/env python3
"""Generate fixed HYG v4.1 star-position references with IAU SOFA-derived ERFA.

By default include every non-Sun catalogue star with usable J2000 coordinates.
Missing astrometric measurements are explicitly flagged, never represented as
known zeros in the exported source table. ERFA receives zero only as a documented
computational assumption for unavailable measurements.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

MAS_TO_RAD = math.pi / (180.0 * 3600.0 * 1000.0)
EPOCHS = (1800, 1850, 1900, 1950, 2000, 2050, 2100, 2150, 2200)
OBSERVED_YEARS = (2000, 2010, 2020, 2025)
CHUNK_SIZE = 4096
# East-positive longitude and geodetic WGS84 positions. No refraction.
SITES = (
    ("sofia", 42.6977, 23.3219, 550.0),
    ("greenwich", 51.4769, 0.0, 46.0),
    ("sydney", -33.8688, 151.2093, 58.0),
)


@dataclass(frozen=True)
class Star:
    hyg_id: str
    hip_id: str
    name: str
    ra_hours: float
    dec_deg: float
    pmra_cosdec_mas_yr: float | None
    pmdec_mas_yr: float | None
    distance_pc: float | None
    radial_velocity_km_s: float | None
    magnitude: float | None

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(name for name, value in (
            ("pmra", self.pmra_cosdec_mas_yr),
            ("pmdec", self.pmdec_mas_yr),
            ("dist", self.distance_pc),
            ("rv", self.radial_velocity_km_s),
        ) if value is None)

    @property
    def quality(self) -> str:
        return "complete" if not self.missing_fields else "assumed"

    @property
    def motion(self) -> float:
        return math.hypot(self.pmra_cosdec_mas_yr or 0.0,
                          self.pmdec_mas_yr or 0.0)


def parse_finite(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def parse_star(row: dict[str, str]) -> Star | None:
    """Read a usable catalogue direction; retain missing measurements as None."""
    hyg_id = (row.get("id") or "").strip()
    if not hyg_id.isdecimal() or hyg_id == "0":  # HYG ID 0 is the Sun.
        return None
    ra = parse_finite(row.get("ra"))
    dec = parse_finite(row.get("dec"))
    if ra is None or dec is None or not (0.0 <= ra < 24.0 and -90.0 < dec < 90.0):
        # Exact celestial poles have undefined right-ascension proper motion.
        return None
    pmra = parse_finite(row.get("pmra"))
    pmdec = parse_finite(row.get("pmdec"))
    dist = parse_finite(row.get("dist"))
    rv = parse_finite(row.get("rv"))
    # HYG uses >=100000 pc for missing/dubious parallax.
    if dist is None or not (0.0 < dist < 100000.0):
        dist = None
    if pmra is not None and abs(pmra) > 20000:
        pmra = None
    if pmdec is not None and abs(pmdec) > 20000:
        pmdec = None
    if rv is not None and abs(rv) > 1500:
        rv = None
    return Star(hyg_id, (row.get("hip") or "").strip(),
                row.get("proper") or "", ra, dec, pmra, pmdec,
                dist, rv, parse_finite(row.get("mag")))


def load_candidates(source: Path) -> list[Star]:
    stars = []
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"id", "hip", "proper", "ra", "dec", "pmra", "pmdec",
                    "dist", "rv", "mag"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Expected original HYG v4.1 CSV; missing columns: {sorted(missing)}")
        for row in reader:
            star = parse_star(row)
            if star is not None:
                stars.append(star)
    if not stars:
        raise ValueError("No usable HYG stars found")
    stars.sort(key=lambda s: int(s.hyg_id))
    if len({s.hyg_id for s in stars}) != len(stars):
        raise ValueError("Duplicate HYG star IDs in input")
    return stars


def select_stars(candidates: list[Star], count: int | None = None) -> list[Star]:
    """None selects every star. Numeric counts select a varied, stable sample."""
    stars = sorted(candidates, key=lambda s: int(s.hyg_id))
    if len({s.hyg_id for s in stars}) != len(stars):
        raise ValueError("Duplicate HYG IDs")
    if count is None:
        return stars
    if count < 1 or count > len(stars):
        raise ValueError(f"Requested {count} stars, but only {len(stars)} are usable")
    chosen: dict[str, Star] = {}

    def add(star: Star):
        if len(chosen) < count:
            chosen.setdefault(star.hyg_id, star)

    # Prefer a range of well-measured, nearby, fast-moving and bright stars.
    complete = [s for s in stars if s.quality == "complete"]
    for ranked in (
        sorted(complete, key=lambda s: (-s.motion, int(s.hyg_id))),
        sorted(complete, key=lambda s: (s.distance_pc, int(s.hyg_id))),
        sorted(complete, key=lambda s: (
            s.magnitude if s.magnitude is not None else math.inf,
            int(s.hyg_id))),
    ):
        for star in ranked[: min(30, max(1, count // 12))]:
            add(star)

    buckets: dict[tuple[int, int], list[Star]] = defaultdict(list)
    for star in stars:
        ra_bin = min(11, int(star.ra_hours / 2.0))
        dec_bin = min(5, max(0, int((star.dec_deg + 90.0) / 30.0)))
        buckets[(ra_bin, dec_bin)].append(star)
    keys = sorted(buckets)
    for i in range(max(map(len, buckets.values()))):
        for key in keys:
            if i < len(buckets[key]):
                add(buckets[key][i])
            if len(chosen) == count:
                return sorted(chosen.values(), key=lambda s: int(s.hyg_id))
    return sorted(chosen.values(), key=lambda s: int(s.hyg_id))


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def fmt(value: float) -> str:
    return f"{value:.12f}"


def maybe_fmt(value: float | None) -> str:
    return "" if value is None else fmt(value)


SOURCE_COLUMNS = [
    "hyg_id", "hip_id", "name", "j2000_ra_hours", "j2000_dec_deg",
    "pmra_cosdec_mas_yr", "pmdec_mas_yr", "distance_pc",
    "rv_km_s", "mag", "quality", "assumed_fields",
]


def source_values(star: Star) -> list[str]:
    return [
        star.hyg_id, star.hip_id, star.name, fmt(star.ra_hours),
        fmt(star.dec_deg), maybe_fmt(star.pmra_cosdec_mas_yr),
        maybe_fmt(star.pmdec_mas_yr), maybe_fmt(star.distance_pc),
        maybe_fmt(star.radial_velocity_km_s), maybe_fmt(star.magnitude),
        star.quality, ";".join(star.missing_fields),
    ]


def erfa_args(star: Star) -> tuple[float, float, float, float, float, float]:
    dec = math.radians(star.dec_deg)
    # HYG pmRA is interpreted as mu_RA*cos(dec), ERFA expects dRA/dt.
    # For unavailable quantities, ERFA gets 0, but the exported rows are
    # marked "assumed" and are not suitable for strict precision claims.
    return (
        math.radians(star.ra_hours * 15.0), dec,
        (star.pmra_cosdec_mas_yr or 0.0) * MAS_TO_RAD / math.cos(dec),
        (star.pmdec_mas_yr or 0.0) * MAS_TO_RAD,
        0.0 if star.distance_pc is None else 1.0 / star.distance_pc,
        star.radial_velocity_km_s or 0.0,
    )


def write_csv(path: Path, header: list[str], rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def parse_count(value: str) -> int | None:
    if value.lower() == "all":
        return None
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use 'all' or a positive integer") from exc
    if count < 1:
        raise argparse.ArgumentTypeError("Count must be at least 1")
    return count


def run(source: Path, output: Path, count: int | None = None,
        force: bool = False) -> None:
    try:
        import erfa
        import numpy as np
    except ImportError as exc:
        raise SystemExit("Install dependencies: python -m pip install -r requirements.txt") from exc
    if not source.is_file():
        raise SystemExit(f"Missing original HYG catalogue: {source}")

    output.mkdir(parents=True, exist_ok=True)
    destinations = [
        output / "selected_stars.csv", output / "cirs_positions.csv",
        output / "observed_altaz.csv", output / "manifest.json",
    ]
    if not force and any(path.exists() for path in destinations):
        raise SystemExit("References already exist. Use another folder or --force.")

    candidates = load_candidates(source)
    selected = select_stars(candidates, count)
    print(f"Generating reference positions for {len(selected):,} stars "
          f"({sum(s.quality == 'complete' for s in selected):,} with complete measurements)")
    write_csv(destinations[0], SOURCE_COLUMNS,
              (source_values(star) for star in selected))

    # PyERFA functions are NumPy-vectorized. Process in small batches to keep
    # memory bounded even for more than a million output records.
    args = np.asarray([erfa_args(s) for s in selected], dtype=np.float64)

    def chunks():
        for start in range(0, len(selected), CHUNK_SIZE):
            end = min(start + CHUNK_SIZE, len(selected))
            block = args[start:end]
            yield selected[start:end], [block[:, i] for i in range(6)]

    def cirs_rows():
        for year in EPOCHS:
            jd1, jd2 = erfa.cal2jd(year, 1, 1)
            jd2 += 0.5
            print(f"CIRS: {year}", flush=True)
            for group, inputs in chunks():
                ri, di, _eo = erfa.atci13(*inputs, jd1, jd2)
                for star, ra, dec in zip(group, ri, di):
                    yield [
                        star.hyg_id, star.hip_id, f"{year}-01-01T12:00:00",
                        "TDB", fmt(jd1), fmt(jd2),
                        fmt(math.degrees(ra) % 360.0), fmt(math.degrees(dec)),
                        star.quality, ";".join(star.missing_fields),
                    ]

    write_csv(destinations[1], [
        "hyg_id", "hip_id", "date", "time_scale", "jd_part1", "jd_part2",
        "cirs_ra_deg", "cirs_dec_deg", "quality", "assumed_fields",
    ], cirs_rows())

    def altaz_rows():
        for year in OBSERVED_YEARS:
            # Use UTC and explicitly idealized UT1-UTC=0 and polar motion=0.
            utc1, utc2 = erfa.dtf2d("UTC", year, 1, 1, 12, 0, 0.0)
            for site, latitude, longitude, height in SITES:
                print(f"AltAz: {site}, {year}", flush=True)
                for group, inputs in chunks():
                    az, zd, _ha, _dec, _ra, _eo = erfa.atco13(
                        *inputs, utc1, utc2, 0.0,
                        math.radians(longitude), math.radians(latitude), height,
                        0.0, 0.0, 0.0, 10.0, 0.5, 0.55,
                    )
                    for star, a, z in zip(group, az, zd):
                        yield [
                            star.hyg_id, star.hip_id, f"{year}-01-01T12:00:00",
                            "UTC", site, fmt(latitude), fmt(longitude),
                            fmt(height), fmt(math.degrees(a) % 360.0),
                            fmt(90.0 - math.degrees(z)),
                            star.quality, ";".join(star.missing_fields),
                        ]

    write_csv(destinations[2], [
        "hyg_id", "hip_id", "date", "time_scale", "site", "latitude_deg",
        "longitude_deg_east", "height_m", "az_deg_north_east", "alt_deg",
        "quality", "assumed_fields",
    ], altaz_rows())

    quality = Counter(s.quality for s in selected)
    missing = Counter(field for s in selected for field in s.missing_fields)
    manifest = {
        "schema": "astral-reference-v1",
        "source": "HYG v4.1 original CSV, CC BY-SA 4.0",
        "source_sha256": sha256(source),
        "generator_sha256": sha256(Path(__file__)),
        "library": "PyERFA / ERFA (derived from IAU SOFA)",
        "pyerfa_version": erfa.__version__,
        "models": {
            "cirs": "ERFA atci13 (ICRS J2000 -> CIRS; dates TDB)",
            "altaz": "ERFA atco13 (ICRS J2000 -> observed AltAz; dates UTC)",
        },
        "selection": {
            "mode": "all" if count is None else "sample",
            "stars": len(selected),
            "candidate_stars": len(candidates),
            "quality_counts": dict(quality),
            "missing_measurement_counts": dict(missing),
            "precision_evaluation": "Filter quality=complete. HYG still has measurement uncertainty.",
            "unique_hyg_ids": True,
            "per_star_uncertainties_available": False,
        },
        "cirs_dates_tdb": [f"{y}-01-01T12:00:00" for y in EPOCHS],
        "observed_dates_utc": [f"{y}-01-01T12:00:00" for y in OBSERVED_YEARS],
        "sites": [
            {"name": name, "lat_deg": lat, "lon_deg_east": lon, "height_m": height}
            for name, lat, lon, height in SITES
        ],
        "assumptions": {
            "catalogue_epoch": "HYG J2000.0; treated as ICRS J2000 input",
            "pmra": "HYG pmRA interpreted as mu_RA*cos(dec); divided by cos(dec) for ERFA",
            "missing_measurements": (
                "Missing pmra/pmdec/rv are passed to ERFA as 0; "
                "missing distance is passed as 0 parallax. "
                "Source CSV leaves unknowns blank, and each result is marked assumed."
            ),
            "hyg_distance_sentinel": "dist >= 100000 pc treated as unknown",
            "rv_units": "km/s (+ receding)",
            "cirs": "Geocentric apparent RA/Dec, excludes observer and Earth rotation",
            "altaz": "UT1-UTC=0 s, xp=yp=0 rad, pressure=0 hPa; idealized Earth orientation",
            "refraction": "disabled",
        },
        "counts": {
            "cirs_rows": len(selected) * len(EPOCHS),
            "altaz_rows": len(selected) * len(OBSERVED_YEARS) * len(SITES),
        },
        "file_sha256": {p.name: sha256(p) for p in destinations[:3]},
    }
    destinations[3].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {manifest['counts']['cirs_rows']:,} CIRS and "
          f"{manifest['counts']['altaz_rows']:,} AltAz reference rows.")
    print(f"Verified reference files can be checked with: python verify.py {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True,
                        help="Original unchanged hygdata_v41.csv")
    parser.add_argument("--out", type=Path, default=Path("references"))
    parser.add_argument("--count", type=parse_count, default=None,
                        metavar="all|N", help="Default: all usable HYG stars")
    parser.add_argument("--force", action="store_true")
    options = parser.parse_args()
    run(options.catalog, options.out, options.count, options.force)


if __name__ == "__main__":
    main()
