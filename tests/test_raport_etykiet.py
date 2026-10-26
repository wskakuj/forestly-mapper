"""Tests for matching unresolved UUIDs to A1 labels without a MAP write."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core import opisy_na_mape as onm
from app.core import raport_etykiet as inspector


class LabelProblemReportTests(unittest.TestCase):
    def sample(self, path):
        lines = [
            ";# Plik danych systemu GEO-MAP",
            ";# EXT 4000 0 0 200 200",
            "*5310 255 24 0",
            ":ID[TEST-A]",
            ":A1[3g]",
            ":A2[SO55|0.55]",
            "L 2 0.000 0.000 0.0000000 1.0000000 5",
            "L 3 0.000 0.000 0.0000000 1.0000000 5",
            "P 1 0 0", "P 1 100 0", "P 1 100 100",
            "P 1 0 100", "P 0 0 0", "",
        ]
        path.write_bytes(onm.tekst_na_maz("\r\n".join(lines)))

    def report(self, path, source):
        path.write_text(json.dumps({
            "plik_wejsciowy": str(source), "skala": 4000,
            "liczba_napisow": 2, "wysokosc_mm": 2.5,
            "zmiany": [],
            "raport_silnika": {"nierozwiazane": [{
                "typ": "napis_napis", "elementy": ["TEST-A:L2", "TEST-A:L3"]}]},
        }), encoding="utf-8")

    def test_matches_named_label_without_touching_files(self):
        with TemporaryDirectory() as d:
            source, report = Path(d) / "sample.MAP", Path(d) / "report.json"
            self.sample(source)
            self.report(report, source)
            before_map, before_report = source.read_bytes(), report.read_bytes()
            result = inspector.pokaz_problemowe(source, report, ["3g", "3r"])
            self.assertEqual(len(result["wyniki"]), 1)
            self.assertEqual(result["wyniki"][0]["litera"], "3g")
            self.assertEqual(result["wyniki"][0]["problemy"], {"napis_napis": 1})
            self.assertEqual(result["nieznalezione"], ["3r"])
            self.assertEqual(before_map, source.read_bytes())
            self.assertEqual(before_report, report.read_bytes())

    def test_rejects_wrong_map(self):
        with TemporaryDirectory() as d:
            source, report = Path(d) / "sample.MAP", Path(d) / "report.json"
            self.sample(source)
            self.report(report, Path(d) / "other.MAP")
            with self.assertRaises(ValueError):
                inspector.pokaz_problemowe(source, report, ["3g"])


if __name__ == "__main__":
    unittest.main()
