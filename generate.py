#!/usr/bin/env python3
"""Reproducible HYG v4.1 -> IAU ERFA reference position fixtures.

No dependencies are imported until generation: --help and selection tests work
without pyerfa. Input is the unchanged HYG v4.1 CSV from Astral Observatory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

MAS_TO_RAD = math.pi / (180.0 * 3600.0 * 1000.0)
EPOCHS = (1800, 1850, 1900, 1950, 2000, 2050, 2100, 2150, 2200)
OBSERVED_YEARS = (2000, 2010, 2020, 2025)
# Longitude is east-positive; geodetic WGS84. No atmosphere, no polar motion.
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
    pmra_cosdec_mas_yr: float
    pmdec_mas_yr: float
    distance_pc: float
    radial_velocity_km_s: float
    magnitude: float | None

    @property
    def motion(self) -> float:
        return math.hypot(self.pmra_cosdec_mas_yr, self.pmdec_mas_yr)


def parse_finite(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def parse_star(row: dict[str, str]) -> Star | None:
    """Require complete kinematic data; HYG has no per-star uncertainty fields."""
    if not (row.get("id") and row.get("hip")):
        return None
    fields = {k: parse_finite(row.get(k)) for k in
              ("ra", "dec", "pmra", "pmdec", "dist", "rv", "mag")}
    if any(fields[k] is None for k in ("ra", "dec", "pmra", "pmdec", "dist", "rv")):
        return None
    ra, dec, dist = fields["ra"], fields["dec"], fields["dist"]
    # Avoid cos(dec) numerical singularity in conversion to ERFA dRA/dt.
    if not (0.0 <= ra < 24.0 and -85.0 < dec < 85.0 and 0.0 < dist < 100000.0):
        return None
    # Extremely large values are more likely missing/corrupt than usable.
    if abs(fields["rv"]) > 1500 or math.hypot(fields["pmra"], fields["pmdec"]) > 20000:
        return None
    return Star(row["id"], row["hip"], row.get("proper", "") or "",
                ra, dec, fields["pmra"], fields["pmdec"], dist, fields["rv"], fields["mag"])


def load_candidates(source: Path) -> list[Star]:
    stars: list[Star] = []
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"id", "hip", "proper", "ra", "dec", "pmra", "pmdec", "dist", "rv", "mag"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Expected original HYG v4.1 CSV, missing: {sorted(required-set(reader.fieldnames or []))}")
        for row in reader:
            star = parse_star(row)
            if star is not None:
                stars.append(star)
    # Catalogue order and stable source identifiers determine all tie breaks.
    stars.sort(key=lambda s: (int(s.hyg_id), int(s.hip_id)))
    return stars


def select_stars(candidates: list[Star], count: int) -> list[Star]:
    if count < 1:
        raise ValueError("count must be >= 1")
    # Avoid duplicate HIP entries representing unresolved/multiple components.
    by_hip: dict[str, Star] = {}
    for star in sorted(candidates, key=lambda x: (int(x.hyg_id), int(x.hip_id))):
        by_hip.setdefault(star.hip_id, star)
    stars = sorted(by_hip.values(), key=lambda x: int(x.hyg_id))
    if len(stars) < count:
        raise ValueError(f"Only {len(stars)} distinct HIP stars have complete usable astrometry; requested {count}")

    chosen: dict[str, Star] = {}
    def add(s: Star):
        if len(chosen) < count:
            chosen.setdefault(s.hip_id, s)

    # Deliberately include nearby / high proper-motion / bright sources.
    for rank in (
        sorted(stars, key=lambda s: (-s.motion, int(s.hyg_id))),
        sorted(stars, key=lambda s: (s.distance_pc, int(s.hyg_id))),
        sorted(stars, key=lambda s: (s.magnitude if s.magnitude is not None else 99., int(s.hyg_id))),
    ):
        for s in rank[: min(20, max(1, count // 12))]:
            add(s)

    # Spread remaining cases over RA and declination bands.
    buckets: dict[tuple[int, int], list[Star]] = defaultdict(list)
    for s in stars:
        ra_bin = min(11, int(s.ra_hours / 2.0))
        dec_bin = min(5, int((s.dec_deg + 90.0) / 30.0))
        buckets[(ra_bin, dec_bin)].append(s)
    keys = sorted(buckets)
    for i in range(max(map(len, buckets.values()))):
        for key in keys:
            if i < len(buckets[key]):
                add(buckets[key][i])
            if len(chosen) >= count:
                break
        if len(chosen) >= count:
            break
    return sorted(chosen.values(), key=lambda s: int(s.hyg_id))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fmt(x: float) -> str:
    return f"{x:.12f}"


def source_values(star: Star):
    return [star.hyg_id, star.hip_id, star.name, fmt(star.ra_hours),
            fmt(star.dec_deg), fmt(star.pmra_cosdec_mas_yr), fmt(star.pmdec_mas_yr),
            fmt(star.distance_pc), fmt(star.radial_velocity_km_s),
            "" if star.magnitude is None else fmt(star.magnitude)]

SOURCE_COLUMNS = ["hyg_id", "hip_id", "name", "j2000_ra_hours", "j2000_dec_deg",
                  "pmra_cosdec_mas_yr", "pmdec_mas_yr", "distance_pc", "rv_km_s", "mag"]


def erfa_args(star: Star) -> tuple[float, float, float, float, float, float]:
    dec = math.radians(star.dec_deg)
    # HYG/Hipparcos pmRA is along the great circle: mu_alpha * cos(delta).
    # ERFA expects dRA/dt, i.e. WITHOUT cos(delta).
    return (math.radians(star.ra_hours * 15.0), dec,
            star.pmra_cosdec_mas_yr * MAS_TO_RAD / math.cos(dec),
            star.pmdec_mas_yr * MAS_TO_RAD,
            1.0 / star.distance_pc, star.radial_velocity_km_s)


def write_csv(path: Path, header: list[str], rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def run(source: Path, output: Path, count: int, force: bool = False):
    try:
        import erfa  # PyERFA provides ERFA, derived from IAU SOFA.
    except ImportError as e:
        raise SystemExit("Install the reference library first: python -m pip install -r requirements.txt") from e
    if not source.is_file():
        raise SystemExit(f"Missing original HYG v4.1 source file: {source}")
    output.mkdir(parents=True, exist_ok=True)
    destinations = [output / p for p in
                    ("selected_stars.csv", "cirs_positions.csv", "observed_altaz.csv", "manifest.json")]
    if not force and any(p.exists() for p in destinations):
        raise SystemExit("Reference output already exists. Use a different directory or --force to regenerate.")
    candidates = load_candidates(source)
    selected = select_stars(candidates, count)
    write_csv(destinations[0], SOURCE_COLUMNS, (source_values(s) for s in selected))

    def cirs_rows():
        for year in EPOCHS:
            # IAU ERFA atci13 wants TDB. Noon calendar TDB; no leap-second/UT1 assumptions.
            jd1, jd2 = erfa.cal2jd(year, 1, 1)
            jd2 += 0.5
            for star in selected:
                ri, di, _eo = erfa.atci13(*erfa_args(star), jd1, jd2)
                yield [star.hyg_id, star.hip_id, f"{year}-01-01T12:00:00", "TDB",
                       fmt(jd1), fmt(jd2), fmt(math.degrees(ri) % 360), fmt(math.degrees(di))]
    write_csv(destinations[1], ["hyg_id", "hip_id", "date", "time_scale", "jd_part1", "jd_part2",
                                "cirs_ra_deg", "cirs_dec_deg"], cirs_rows())

    def altaz_rows():
        for year in OBSERVED_YEARS:
            # Atco13 uses UTC for these dates, UT1-UTC=0 seconds, polar motion zero.
            # Atmosphere: pressure=0 (no refraction), so these are geometrical directions.
            utc1, utc2 = erfa.dtf2d("UTC", year, 1, 1, 12, 0, 0.0)
            for site, latitude, longitude, height in SITES:
                for star in selected:
                    aob, zob, _hob, _dob, _rob, _eo = erfa.atco13(
                        *erfa_args(star), utc1, utc2, 0.0,
                        math.radians(longitude), math.radians(latitude), height,
                        0.0, 0.0, 0.0, 10.0, 0.5, 0.55)
                    yield [star.hyg_id, star.hip_id, f"{year}-01-01T12:00:00", "UTC",
                           site, fmt(latitude), fmt(longitude), fmt(height),
                           fmt(math.degrees(aob) % 360), fmt(90.0-math.degrees(zob))]
    write_csv(destinations[2], ["hyg_id", "hip_id", "date", "time_scale", "site",
                                "latitude_deg", "longitude_deg_east", "height_m",
                                "az_deg_north_east", "alt_deg"], altaz_rows())

    manifest = {
        "schema": "astral-reference-v1",
        "source": "HYG v4.1 original CSV, CC BY-SA 4.0",
        "source_sha256": sha256(source),
        "generator_sha256": sha256(Path(__file__)),
        "library": "PyERFA / ERFA (derived from IAU SOFA)",
        "pyerfa_version": erfa.__version__,
        "models": {"cirs": "ERFA atci13 (ICRS J2000 -> CIRS; dates TDB)",
                   "altaz": "ERFA atco13 (ICRS J2000 -> observed alt/az; dates UTC)"},
        "selection": {"stars": len(selected), "complete_pm_distance_rv": True,
                      "requires_hip": True, "unique_hip_ids": True,
                      "per_star_uncertainties_available": False,
                      "note": "Complete records and sky coverage do not establish measurement accuracy."},
        "cirs_dates_tdb": [f"{y}-01-01T12:00:00" for y in EPOCHS],
        "observed_dates_utc": [f"{y}-01-01T12:00:00" for y in OBSERVED_YEARS],
        "sites": [{"name": name, "lat_deg": lat, "lon_deg_east": lon, "height_m": height}
                  for name, lat, lon, height in SITES],
        "assumptions": {
            "catalogue_epoch": "HYG equinox and epoch J2000.0; treated as ICRS J2000 input",
            "pmra": "HYG pmRA interpreted as mu_alpha*cos(delta), divided by cos(delta) for ERFA",
            "parallax": "arcseconds = 1/distance_pc",
            "rv": "HYG radial velocity in km/s (+ receding)",
            "cirs": "Geocentric apparent RA/Dec; excludes observer location and Earth rotation",
            "altaz": "UT1-UTC=0 s, xp=yp=0 rad, pressure=0 hPa; idealized, not historical/future Earth orientation",
            "refraction": "disabled", "atmosphere": "no pressure/refraction",
        },
        "counts": {"cirs_rows": len(selected) * len(EPOCHS),
                   "altaz_rows": len(selected) * len(OBSERVED_YEARS) * len(SITES)},
        "file_sha256": {p.name: sha256(p) for p in destinations[:3]},
    }
    destinations[3].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Selected {len(selected)} stars from {len(candidates)} complete candidate rows")
    print(f"Wrote {manifest['counts']['cirs_rows']} CIRS and {manifest['counts']['altaz_rows']} AltAz reference rows to {output}")
    print("Run: python verify.py", output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="Original unchanged hygdata_v41.csv")
    parser.add_argument("--out", type=Path, default=Path("references"))
    parser.add_argument("--count", type=int, default=400)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(args.catalog, args.out, args.count, args.force)


if __name__ == "__main__":
    main()
