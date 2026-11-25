# DreamGrid reference data

Small, original interpretation examples for the offline DreamGrid coding task.
These are **hypothetical readings**, not validated psychological conclusions.
They are not copied from an external dictionary or licensed dataset.

Run from the root of this repository:

```bash
python3 generate_dreamgrid_reference.py
```

This creates a separate `dreamgrid-reference/` directory containing
`interpretations.json`, `SOURCE.md` and `manifest.json`. Copy that folder
to Taiga. Re-running with the same data verifies it; `--force` regenerates it.

The canonical source is `dreamgrid-data/interpretations.json` (MIT, same as
this repo). Its context guards are a **proposed schema**, not a working DreamGrid
integration. The dictionary may explain links, but **must not create or score
connections**. The rule engine still has to establish events, negation,
relations and sequence from the actual dream text.

No internet, ML model, or third-party Python package is required. The astronomy
generator (`run.py`) and its `references/` output are separate and unchanged.
