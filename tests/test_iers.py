import tempfile
import unittest
from pathlib import Path
from prepare_iers import prepare, verify

class IERSTests(unittest.TestCase):
    def test_build_verify_and_detect_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c04 = root/'input.csv'
            c04.write_bytes(b'DATE,MJD,UT1-UTC,X,Y\n'+b'2025-11-25,61000,0.1,0.2,0.3\n'*5000)
            finals = root/'input.all'
            finals.write_bytes((b'261125 61000.00 I '+b'0'*90+b'\n')*5000)
            out = root/'iers-data'
            packaged = prepare(out,c04,finals)
            self.assertTrue(packaged.is_file())
            self.assertEqual(verify(out)['schema'],'iers-bundle-v1')
            self.assertEqual(prepare(out),packaged)
            (out/'finals2000A.all').write_text('bad')
            with self.assertRaises(ValueError): verify(out)
