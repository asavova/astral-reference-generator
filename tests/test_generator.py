import argparse
import csv
import hashlib
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

from generate import Star, erfa_args, parse_count, parse_star, run, select_stars
from verify import verify


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "id": "5", "hip": "123", "proper": "Example",
            "ra": "2.0", "dec": "60.0", "pmra": "100",
            "pmdec": "-50", "dist": "10", "rv": "20", "mag": "3.5",
        }

    def test_hyg_pmra_convention_for_erfa(self):
        star = parse_star(self.row)
        self.assertIsNotNone(star)
        ra, dec, pmra, pmdec, parallax, rv = erfa_args(star)
        self.assertAlmostEqual(ra, math.pi / 6)
        self.assertAlmostEqual(dec, math.pi / 3)
        self.assertAlmostEqual(pmra, 200 * math.pi / (180 * 3600 * 1000))
        self.assertAlmostEqual(parallax, 0.1)
        self.assertEqual(rv, 20.0)

    def test_missing_measurements_are_preserved_and_flagged(self):
        row = {
            **self.row, "hip": "", "pmra": "", "pmdec": "",
            "dist": "100000", "rv": "",
        }
        star = parse_star(row)
        self.assertIsNotNone(star)
        self.assertEqual(star.quality, "assumed")
        self.assertEqual(star.missing_fields, ("pmra", "pmdec", "dist", "rv"))
        self.assertEqual(star.hip_id, "")
        self.assertIsNone(star.distance_pc)
        self.assertEqual(erfa_args(star)[2:], (0.0, 0.0, 0.0, 0.0))

    def test_reject_sun_and_invalid_coordinates(self):
        for field, value in (("id", "0"), ("ra", ""), ("dec", "90"),
                             ("dec", "-90"), ("ra", "24")):
            self.assertIsNone(parse_star({**self.row, field: value}),
                              (field, value))

    def test_all_stars_and_deterministic_selection(self):
        stars = [
            Star(str(i), "" if i % 3 == 0 else str(i), "",
                 (i * 7 % 240) / 10, i % 160 - 80,
                 i * 0.5 if i % 2 == 0 else None,
                 i * 0.1, 10 + i, 5 if i % 3 else None, 3)
            for i in range(1, 150)
        ]
        a = select_stars(stars)
        self.assertEqual(len(a), 149)
        self.assertEqual(a, select_stars(list(reversed(stars))))
        subset = select_stars(stars, 70)
        self.assertEqual(subset, select_stars(list(reversed(stars)), 70))
        self.assertEqual(len(subset), 70)
        self.assertEqual(len({star.hyg_id for star in subset}), 70)
        with self.assertRaises(ValueError):
            select_stars(stars, 150)

    def test_count_parsing(self):
        self.assertIsNone(parse_count("all"))
        self.assertIsNone(parse_count("ALL"))
        self.assertEqual(parse_count("400"), 400)
        for value in ("0", "-5", "nonsense"):
            with self.assertRaises(argparse.ArgumentTypeError):
                parse_count(value)

    def test_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ["selected_stars.csv", "cirs_positions.csv", "observed_altaz.csv"]
            for name in names:
                (root / name).write_text("id\n1\n", encoding="utf-8")
            data = {
                "schema": "astral-reference-v1",
                "file_sha256": {
                    name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                    for name in names
                },
                "counts": {"cirs_rows": 1, "altaz_rows": 1},
                "selection": {"stars": 1},
            }
            (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
            verify(root)
            (root / "cirs_positions.csv").write_text("id\n2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(root)

    @unittest.skipUnless(importlib.util.find_spec("erfa"), "PyERFA not installed")
    def test_small_real_erfa_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "hygdata_v41.csv"
            with source.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow([
                    "id", "hip", "proper", "ra", "dec",
                    "pmra", "pmdec", "dist", "rv", "mag",
                ])
                writer.writerow(["0", "", "Sun", 0, 0, 0, 0, 0, 0, -26])
                writer.writerow(["1", "32349", "Sirius", 6.7522, -16.7161,
                                 -546.01, -1223.07, 2.637, -5.5, -1.46])
                writer.writerow(["2", "", "Unnamed", 2.0, 15.0, "", "",
                                 100000, "", ""])
            output = root / "references"
            run(source, output)
            verify(output)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["selection"]["stars"], 2)
            self.assertEqual(manifest["selection"]["quality_counts"],
                             {"assumed": 1, "complete": 1})
            self.assertEqual(manifest["counts"]["cirs_rows"], 18)
            self.assertEqual(manifest["counts"]["altaz_rows"], 24)
            with (output / "cirs_positions.csv").open(newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["quality"], "complete")
            self.assertEqual(rows[1]["quality"], "assumed")
            self.assertEqual(rows[1]["assumed_fields"], "pmra;pmdec;dist;rv")


if __name__ == "__main__":
    unittest.main()
