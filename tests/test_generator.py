import tempfile
import unittest
from pathlib import Path
from generate import Star, erfa_args, parse_star, select_stars
from verify import verify


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.row = {"id": "5", "hip": "123", "proper": "Example", "ra": "2.0", "dec": "60.0",
                    "pmra": "100", "pmdec": "-50", "dist": "10", "rv": "20", "mag": "3.5"}

    def test_hyg_pmra_convention_for_erfa(self):
        s = parse_star(self.row)
        self.assertIsNotNone(s)
        ra, dec, pr, pd, px, rv = erfa_args(s)
        self.assertAlmostEqual(ra, 3.141592653589793 / 6)
        self.assertAlmostEqual(pr, 2 * 100 * (3.141592653589793 / (180*3600*1000)))
        self.assertAlmostEqual(px, .1)
        self.assertEqual(rv, 20.)

    def test_reject_missing_or_dubious_values(self):
        for field, value in (("hip", ""), ("dist", "100000"), ("rv", ""),
                             ("pmra", ""), ("dec", "90")):
            row = {**self.row, field: value}
            self.assertIsNone(parse_star(row), (field, value))

    def test_selection_deterministic_and_unique(self):
        stars = [Star(str(i), str(i), "", (i*7 % 240)/10, i % 160 - 80,
                      i * .5, i*.1, 10+i, 5, 3) for i in range(1, 150)]
        a = select_stars(stars, 70)
        self.assertEqual(a, select_stars(list(reversed(stars)), 70))
        self.assertEqual(len(a), 70)
        self.assertEqual(len({s.hip_id for s in a}), 70)

    def test_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "selected_stars.csv").write_text("id\n1\n", encoding="utf-8")
            (root / "cirs_positions.csv").write_text("id\n1\n", encoding="utf-8")
            (root / "observed_altaz.csv").write_text("id\n1\n", encoding="utf-8")
            import hashlib, json
            names = ["selected_stars.csv", "cirs_positions.csv", "observed_altaz.csv"]
            data = {"schema": "astral-reference-v1", "file_sha256": {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},
                    "counts": {"cirs_rows": 1, "altaz_rows": 1}, "selection": {"stars": 1}}
            (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
            verify(root)
            (root / "cirs_positions.csv").write_text("id\n2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(root)


if __name__ == "__main__":
    unittest.main()
