# Astral Reference Generator

An independent Python tool that generates fixed reference star positions for Astral Observatory. It reads the original HYG v4.1 catalogue and uses **PyERFA**, based on the IAU SOFA astronomical routines. It does not use the Java engine's calculations.

## Run

You need **Python 3.11 or newer** and an internet connection for the initial setup. Clone or download this repository, then run from its directory:

```bash
python3 run.py
```

On Windows, use `py -3 run.py` instead.

The script automatically:

1. Finds `../astral-observatory/data/hygdata_v41.csv` if you have the application repository beside this one; otherwise downloads that catalogue from the public Astral Observatory repository into `cache/`.
2. Creates a local `.venv` and installs the pinned PyERFA dependency.
3. Runs the generator tests.
4. Selects 400 stars with complete measurements, generates the reference positions and verifies their checksums and row counts.

The files are saved in `references/`. A second run verifies existing files **without overwriting them**, so they stay fixed across coding turns. To deliberately replace them, run `python3 run.py --force`. To supply the input explicitly, run `python3 run.py --catalog /path/to/hygdata_v41.csv`.

## Generated files

| File | Contents |
| --- | --- |
| `selected_stars.csv` | 400 selected HIP stars and the source astrometric measurements |
| `cirs_positions.csv` | 3,600 geocentric apparent CIRS positions for nine dates spanning 1800–2200 |
| `observed_altaz.csv` | 4,800 azimuth/altitude positions for Sofia, Greenwich and Sydney at four dates during 2000–2025 |
| `manifest.json` | Source and generator SHA-256, PyERFA version, assumptions, file checksums and row counts |

You can copy the **generated CSVs and manifest** to the offline coding desktop. Keep this generator separate from the Java project.

## What the reference positions mean

- The CIRS file uses PyERFA's `atci13` routine, with noon **TDB** dates. It is not a J2000 RA/Dec lookup table.
- The observed AltAz file uses `atco13`, **UTC** dates, a geodetic observing position, an idealized `UT1−UTC = 0`, zero polar motion and no atmospheric refraction. These assumptions must match the engine under test.
- HYG RA is in hours, Dec in degrees, proper motion in milliarcseconds/year, distances in parsecs and radial velocity in km/s. Missing or dubious measurements are excluded from the selected reference set, not treated as zero.
- Error comparisons should use the **angular separation** on the celestial sphere. Speed comparisons should time the full-catalogue calculation under consistent conditions.

These are reproducible calculations using astronomy standards software, **not certified measurements**. HYG does not provide per-star uncertainty estimates, and ERFA's built-in Earth ephemeris is most thoroughly characterized over 1900–2100. Reference comparisons at 1800 and 2200 are extended-model comparisons and do not establish observational accuracy to one arcsecond. HYG catalogue uncertainty likewise limits what can be claimed about every star across four centuries.

## Source and licence

- [HYG Star Database v4.1](https://github.com/astronexus/HYG-Database) (compiled by David Nash / Astronexus), **CC BY-SA 4.0**. Generated star reference datasets derived from HYG retain its attribution/share-alike obligations.
- [PyERFA](https://github.com/liberfa/pyerfa) / [IAU SOFA](https://www.iausofa.org/about-us), standard astronomy routines, installed separately; not bundled in this repository.
- Generator code: **MIT** (see `LICENSE`).
