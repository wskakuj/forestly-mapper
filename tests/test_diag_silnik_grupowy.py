"""Read-only regression for the group solver MAP diagnostics."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core import diag_silnik_grupowy as diag
from app.core import opisy_na_mape as onm


class ReadOnlyMapTests(unittest.TestCase):
    def sample(self, path):
        lines = [
            ";# Plik danych systemu GEO-MAP",
            ";# EXT 4000 0 0 100 100",
            "*5310 255 24 0",
            ":ID[TEST-UUID]",
            ":A1[a]",
            ":A2[SO55|0.55]",
            "L 2 0.000 0.000 0.0000000 1.0000000 5",
            "L 3 0.000 0.000 0.0000000 1.0000000 5",
            "P 1 0 0", "P 1 100 0", "P 1 100 100",
            "P 1 0 100", "P 0 0 0", "",
        ]
        path.write_bytes(onm.tekst_na_maz("\r\n".join(lines)))

    def test_diagnostics_never_writes_source_map(self):
        with TemporaryDirectory() as root:
            src = Path(root) / "test.MAP"
            self.sample(src)
            before = src.read_bytes()
            result = diag.diagnozuj(src, skala=4000)
            self.assertEqual(before, src.read_bytes())
            self.assertEqual(result["liczba_napisow"], 2)
            self.assertEqual(result["liczba_poligonow"], 1)
            self.assertIn("po", result)

    def test_json_report_is_separate_from_map(self):
        with TemporaryDirectory() as root:
            src = Path(root) / "test.MAP"
            dst = Path(root) / "wynik.json"
            self.sample(src)
            before = src.read_bytes()
            self.assertEqual(diag.main([str(src), "--json", str(dst)]), 0)
            self.assertEqual(before, src.read_bytes())
            self.assertEqual(json.loads(dst.read_text(encoding="utf-8"))[
                "liczba_napisow"], 2)

    def test_rejects_map_as_report_target(self):
        with TemporaryDirectory() as root:
            src = Path(root) / "test.MAP"
            self.sample(src)
            before = src.read_bytes()
            with self.assertRaises(SystemExit):
                diag.main([str(src), "--json", str(src)])
            self.assertEqual(src.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
