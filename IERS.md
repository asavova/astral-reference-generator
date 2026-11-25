# Preparing IERS data for the offline app

Run this on your own computer with internet access:

```bash
python3 prepare_iers.py
```

It fetches official **IERS EOP C04** observations from 1962 onward and **USNO/IERS finals2000A** data with limited short-term forecasts. It checks the file types, records SHA-256 hashes and source URLs, and creates:

- `iers-data/` — the two original data files, `DATA_SOURCE.md` and `manifest.json`
- `iers-data.tar.gz` — a data-only archive you can upload into Taiga

**Upload only the resulting archive, not this tool.** Claude can then implement Java loaders and bundle the data into Astral Observatory so it runs without internet access.

To intentionally refresh the dataset, run `python3 prepare_iers.py --force`. You can also supply existing local files via `--c04-file` and `--finals-file`.

IERS observations **do not** cover the entire 1800–2200 period. Historical dates before 1962 and distant future dates need a documented Earth-rotation model, with estimates clearly distinguished from observations. Bulletin A predicted rows are not measurements.

Official sources:

- https://datacenter.iers.org/products/eop/long-term/c04_20u24/csv/
- https://maia.usno.navy.mil/ser7/finals2000A.all

