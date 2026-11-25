# Astral Reference Generator

Independent Python tool for generating fixed star-position reference files for Astral Observatory. It uses the original HYG v4.1 catalogue and PyERFA, based on the IAU SOFA astronomical routines. It does not reuse calculations from the Java project.

## Run

Requires Python 3.11 or later and internet access for the initial setup.

```bash
python3 run.py
```

On Windows, use `py -3 run.py`.

The script finds the local HYG catalogue next to this repo, or downloads it from Astral Observatory; creates a virtual environment; installs the pinned PyERFA dependency; runs tests; generates reference positions; and verifies checksums. Results are saved under `references/`.

**By default, the generator includes every usable non-Sun star with valid J2000 coordinates.** It does not stop at 400 stars, and it does not require a Hipparcos ID. Missing proper motion, distance or radial velocity is flagged in the output. If a measurement is missing, ERFA uses an explicit zero-motion/zero-parallax/zero-radial-velocity computational assumption, and the result is labeled `assumed` rather than `complete`. Only stars labeled `complete` are candidates for strict numerical-accuracy comparisons.

For a smaller test run:

```bash
python3 run.py --count 400
```

Existing verified output is not overwritten by a normal run. To replace it (including an earlier 400-star dataset), explicitly use:

```bash
python3 run.py --force
```

You can also pass a local catalogue using `--catalog /path/to/hygdata_v41.csv`. The script generates into a separate staging folder, checks the results, then publishes them. Failed generation won't replace existing files.

## Generated files

| File | Contents |
| --- | --- |
| `selected_stars.csv` | Original HYG measurements, identifiers and data-quality flags |
| `cirs_positions.csv` | Nine geocentric apparent CIRS positions per star, from 1800 to 2200 |
| `observed_altaz.csv` | Twelve observer-dependent positions per star for Sofia, Greenwich and Sydney over four dates |
| `manifest.json` | Source and generator hashes, PyERFA version, assumptions, quality counts, output hashes and row counts |

With 119,625 usable non-Sun stars, the expected output would be **1,076,625 CIRS rows** and **1,435,500 AltAz rows**, plus the selected-star table. The exact counts are reported by the generator; stars with invalid input coordinates are skipped. Generation may take some time and use hundreds of megabytes of disk space. Keep these fixed files on the offline coding desktop rather than relying on an internet connection.

## Coordinate conventions

- HYG RA/Dec are J2000 coordinates; RA in hours, Dec in degrees.
- HYG proper motions are read in milliarcseconds/year. The generator interprets `pmra` as mu_RA multiplied by cos(dec) and converts it to the coordinate derivative ERFA expects.
- A valid HYG distance in parsecs is converted to parallax in arcseconds as 1/distance. HYG distances of 100,000 pc or more are treated as unknown.
- The CIRS file uses ERFA `atci13` and **TDB** dates. These are apparent geocentric positions, not catalogue J2000 coordinates.
- The AltAz file uses ERFA `atco13` and **UTC** dates, with idealized UT1−UTC=0, polar motion=0 and no atmospheric refraction.
- Every row contains `quality` and `assumed_fields`. Filter for `quality=complete` when evaluating strict accuracy. Use a spherical angular separation rather than subtracting RA directly.

**Scientific limit:** These outputs are repeatable calculations, not certified ground-truth observations. HYG does not provide complete per-star uncertainty estimates, and ERFA's Earth ephemeris is most thoroughly characterized over 1900–2100. The 1800/2200 results are extended-model reference comparisons, not guarantees of physical accuracy below one arcsecond.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 verify.py references
```

## Source and licence

- [HYG Star Database v4.1](https://github.com/astronexus/HYG-Database) (Astronexus), CC BY-SA 4.0. Generated reference tables derived from HYG retain attribution and applicable share-alike conditions.
- [PyERFA](https://github.com/liberfa/pyerfa) / [IAU SOFA](https://www.iausofa.org/about-us), astronomy routines installed separately, not bundled.
- Generator source code: MIT (see `LICENSE`).
