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

    def test_resolves_a1_and_reports_targeted_scan(self):
        with TemporaryDirectory() as root:
            src = Path(root) / "test.MAP"
            self.sample(src)
            original = src.read_bytes()
            report = diag.diagnozuj(src, skala=4000, etykiety=["A"],
                                    limit_grup=1)
            self.assertEqual(report["wybrane_uuid"], ["TEST-UUID"])
            self.assertEqual(report["wybrane_etykiety"], ["a"])
            self.assertEqual(original, src.read_bytes())
            with self.assertRaisesRegex(ValueError, "Nie znaleziono"):
                diag.diagnozuj(src, skala=4000, etykiety=["3h"])

    def test_warns_about_multicontour_polygons(self):
        lines = [
            "*5310 255 24 0", ":ID[MULTI]", ":A1[test]",
            "P 1 0 0", "P 1 20 0", "P 1 20 20",
            "P 0 0 0",
            "P 1 25 0", "P 1 35 0", "P 1 35 20",
            "P 0 25 0",
        ]
        from app.core import uklad_opisow as uk
        objects = uk.wszystkie_poligony({"lines": lines})
        warnings = diag._wykryj_wiele_konturow(objects, lines)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["id"], "MULTI")
        self.assertEqual(warnings[0]["liczba_sekcji_p0"], 2)

    def test_open_line_does_not_block_inside_candidate(self):
        with TemporaryDirectory() as root:
            src = Path(root) / "test.MAP"
            self.sample(src)
            source = src.read_bytes()
            extension = ("\r\n*4214 16711680 22 0\r\n"
                         ":ID[OPEN-PATH]\r\n"
                         "P 1 -100 200\r\n"
                         "P 1 -100 -100\r\n"
                         "P 1 200 -100\r\n")
            src.write_bytes(source + extension.encode("ascii"))
            original = src.read_bytes()
            report = diag.diagnozuj(
                src, skala=4000, etykiety=["a"], sprawdz_warianty=True)
            candidate_counts = report["diagnostyka_wariantow"][0]["kandydaci"]
            self.assertGreater(candidate_counts["litera"]["wewnetrzne"], 0)
            self.assertEqual(original, src.read_bytes())

    def test_candidate_debug_report_does_not_write_to_map(self):
        with TemporaryDirectory() as root:
            src = Path(root) / "test.MAP"
            self.sample(src)
            original = src.read_bytes()
            result = diag.diagnozuj(
                src, skala=4000, etykiety=["a"], sprawdz_warianty=True)
            data = result["diagnostyka_wariantow"]
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["uuid"], "TEST-UUID")
            self.assertIn("wewnetrzne", data[0]["kandydaci"]["litera"])
            self.assertIn("zewnetrzne", data[0]["kandydaci"]["opis"])
            self.assertIn("plany_bez_kolizji_z_innymi_etykietami", data[0])
            self.assertEqual(original, src.read_bytes())

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
