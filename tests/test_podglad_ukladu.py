"""Regresje podglądu SVG Forestly Mapper, bez nadpisania plików GEO-MAP."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core import diagnostyka_map as dm
from app.core import opisy_na_mape as onm
from app.core import podglad_ukladu as preview


class PreviewTests(unittest.TestCase):
    def source(self, directory, letter="3h"):
        source = Path(directory) / "sample.MAP"
        lines = [
            ";# Plik danych systemu GEO-MAP",
            ";# EXT 4000 0 0 250 250",
            "*5310 255 24 0",
            ":ID[TEST-UUID]", ":A1[" + letter + "]", ":A2[SO45|0.22]",
            "L 2 0.000 0.000 0.0000000 1.0000000 5",
            "L 3 0.000 0.000 0.0000000 1.0000000 5",
            "P 1 0 0", "P 1 200 0", "P 1 200 200", "P 1 0 200",
            "P 0 0 0",
            "*4214 5 1 0", ":ID[OPEN-PATH]",
            "P 1 -100 350", "P 1 -100 -100", "P 1 350 -100",
            "",
        ]
        source.write_bytes(onm.tekst_na_maz("\r\n".join(lines)))
        return source

    def report(self, directory, source, *, changes=(), name=None):
        file = Path(directory) / "report.json"
        mapa = onm.wczytaj_mape(source)
        elements, _ = dm.elementy_z_mapy(mapa, 4000)
        file.write_text(json.dumps({
            "plik_wejsciowy": name or str(source),
            "skala": 4000,
            "wysokosc_mm": 2.5,
            "liczba_napisow": len(elements),
            "zmiany": list(changes),
        }, ensure_ascii=False), encoding="utf-8")
        return file

    def test_two_panel_svg_is_read_only(self):
        with TemporaryDirectory() as d:
            src = self.source(d)
            report = self.report(d, src)
            before_map, before_json = src.read_bytes(), report.read_bytes()
            svg = preview.podglad_svg(src, report, ["3h"])
            self.assertIn("<svg ", svg)
            self.assertIn("PRZED: zrodlo MAP", svg)
            self.assertIn("PO: propozycja algorytmu", svg)
            self.assertIn("<clipPath", svg)
            self.assertIn("3h", svg)
            self.assertEqual(before_map, src.read_bytes())
            self.assertEqual(before_json, report.read_bytes())

    def test_multiline_description_readable_and_preserves_full_text(self):
        with TemporaryDirectory() as d:
            src = self.source(d)
            report = self.report(d,src)
            svg = preview.podglad_svg(src,report,["3h"])
            self.assertIn('data-full-text="SO45|0.22"',svg)
            self.assertIn(">SO45</tspan>",svg)
            self.assertIn(">0.22</tspan>",svg)
            self.assertNotIn(">SO45|0.22</text>",svg)
            self.assertGreaterEqual(svg.count("<tspan "),4)

    def test_preview_reports_unresolved_label_overlaps(self):
        with TemporaryDirectory() as d:
            source = self.source(d, letter="4a")
            report = self.report(d, source)
            svg = preview.podglad_svg(source, report, ["4a"])
            self.assertIn("NIEROZWIAZANE: 4a", svg)
            self.assertIn('font-weight="700"', svg)

    def test_includes_two_point_map_lines(self):
        source = {"lines": [
            "*5310 1 2 3", "P 1 0 0", "P 1 10 0", "P 0 0 0",
            "*4214 1 2 3", "P 1 2 3", "P 1 4 5",
        ]}
        geometry = list(preview._obiekty_liniowe(source))
        self.assertEqual(len(geometry), 2)
        self.assertEqual(geometry[1]["punkty"], [(2.0, 3.0), (4.0, 5.0)])
        self.assertEqual(preview._kontury(geometry[1]["linie"])[0][1], False)

    def test_open_line_is_not_closed_and_contours_remain_separate(self):
        contours = preview._kontury([
            "P 1 0 0", "P 1 10 0", "P 1 10 10", "P 0 0 0",
            "P 1 20 0", "P 1 30 0", "P 1 30 10", "P 0 20 0",
            "P 1 40 0", "P 1 50 0",
        ])
        self.assertEqual(len(contours), 3)
        self.assertEqual([c[1] for c in contours], [True, True, False])
        self.assertEqual(contours[-1][0], [(40.0, 0.0), (50.0, 0.0)])

    def test_real_multipart_4abc_preview_and_orphan_p0(self):
        """Regresja: '4a' i '4c' mają dwa kontury, nie jeden ani trzy."""
        with TemporaryDirectory() as d:
            source = Path(d) / "multiring.MAP"
            lines = [";# Plik danych systemu GEO-MAP",
                     ";# EXT 4000 0 0 400 300"]
            for code, uuid, x0, multipart in (
                ("4a", "a-uuid", 0, True),
                ("4b", "b-uuid", 140, False),
                ("4c", "c-uuid", 280, True)):
                lines += [
                    "*5310 255 24 0", ":ID[" + uuid + "]",
                    ":A1[" + code + "]", ":A2[SO40|0.1]",
                    "L 2 0 0 0 1 5", "L 3 0 0 0 1 5",
                    f"P 1 {x0} 0", f"P 1 {x0+45} 0",
                    f"P 1 {x0+45} 90", f"P 1 {x0} 90",
                    f"P 0 {x0} 0",
                ]
                if multipart:
                    lines += [
                        f"P 1 {x0+60} 0", f"P 1 {x0+100} 0",
                        f"P 1 {x0+100} 90", f"P 1 {x0+60} 90",
                        f"P 0 {x0+60} 0", "P 0 0 0",
                    ]
            lines.append("")
            source.write_bytes(onm.tekst_na_maz("\r\n".join(lines)))
            report = self.report(d, source)
            original = source.read_bytes()
            rendered = preview.podglad_svg(source, report,
                                           ["4a", "4b", "4c"])
            self.assertIn("4a / 4b / 4c", rendered)
            self.assertIn("SO40|0.1", rendered)
            # Widać, czy pozostały nienaprawione kolizje; sam napis
            # "PO" nie może sugerować, że wszystkie etykiety poprawiono.
            self.assertIn("NIEROZWIAZANE:", rendered)
            self.assertGreaterEqual(rendered.count("<path "), 10)
            self.assertNotIn("nan", rendered.lower())
            self.assertEqual(original, source.read_bytes())
            # SVG CLI also works and is safe, rather than throwing due to
            # iterating a multipart dict as if it were XY tuples.
            path = Path(d) / "test.svg"
            self.assertEqual(preview.main([
                str(source), str(report), "--etykiety",
                "4a", "4b", "4c", "--svg", str(path)
            ]), 0)
            self.assertIn("4c", path.read_text(encoding="utf-8"))

    def test_orphan_p0_keeps_true_number_of_contours(self):
        lines = [
            "P 1 0 0", "P 1 10 0", "P 1 10 10", "P 0 0 0",
            "P 1 30 0", "P 1 40 0", "P 1 40 10", "P 0 30 0",
            "P 0 0 0",
        ]
        fragments = preview._kontury(lines)
        self.assertEqual(len(fragments), 2)
        self.assertTrue(all(closed for _, closed in fragments))

    def test_html_escape_and_changed_leader(self):
        with TemporaryDirectory() as d:
            src = self.source(d, "3&h")
            elements, _ = dm.elementy_z_mapy(onm.wczytaj_mape(src), 4000)
            e = next(x for x in elements if x["rodzaj"] == "opis")
            old = e["prostokat"]
            new = [old[0] + 80, old[1], old[2] + 80, old[3]]
            report = self.report(d, src, changes=[{
                "id": e["id"], "rodzaj": e["rodzaj"], "tekst": e["tekst"],
                "przed": old, "po": new,
                "wysiegnik": [[new[0], new[1]], [40, 40]],
            }])
            svg = preview.podglad_svg(src, report, ["3&H"])
            self.assertIn("3&amp;h", svg)
            self.assertIn("circle", svg)
            self.assertNotIn("3&h</text>", svg)

    def test_wrong_map_name_and_stale_original_position_are_rejected(self):
        with TemporaryDirectory() as d:
            src = self.source(d)
            wrong = self.report(d, src, name="other.MAP")
            with self.assertRaisesRegex(ValueError, "innego"):
                preview.podglad_svg(src, wrong, ["3h"])
            report = self.report(d, src, changes=[{
                "id": "TEST-UUID:L3", "przed": [0, 0, 1, 1],
                "po": [5, 5, 6, 6],
                "wysiegnik": None,
            }])
            with self.assertRaisesRegex(ValueError, "Pozycje"):
                preview.podglad_svg(src, report, ["3h"])

    def test_cli_never_overwrites_existing_svg(self):
        with TemporaryDirectory() as d:
            src = self.source(d)
            report = self.report(d, src)
            svg = Path(d) / "preview.svg"
            data_before = src.read_bytes()
            self.assertEqual(preview.main([
                str(src), str(report), "--etykiety", "3h", "--svg", str(svg),
            ]), 0)
            original = svg.read_bytes()
            with self.assertRaises(SystemExit):
                preview.main([
                    str(src), str(report), "--etykiety", "3h", "--svg", str(svg),
                ])
            self.assertEqual(svg.read_bytes(), original)
            self.assertEqual(src.read_bytes(), data_before)


if __name__ == "__main__":
    unittest.main()
