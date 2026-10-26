"""Testy parsowania podpisów GEO-MAP i raportu, bez zapisu do map."""
import unittest
from app.core.diagnostyka_map import elementy_z_mapy, skala_naglowka


class DiagnostykaMapTest(unittest.TestCase):
    def mapa(self, l2="L 2 0.000 0.000 0.0000000 1.0000000 5",
             l3="L 3 0.000 0.000 0.0000000 1.0000000 5",
             opis="SO55|0.55"):
        lines = [
            ";# Plik danych systemu GEO-MAP",
            ";# EXT 4000 0 0 100 100",
            "*5310 255 24 0",
            ":ID[TEST-UUID]",
            ":A1[a]",
            ":A2[" + opis + "]",
            l2, l3,
            "P 1 0 0", "P 1 100 0", "P 1 100 100",
            "P 1 0 100", "P 0 0 0",
        ]
        return {"lines": lines}

    def test_pobiera_skale_z_naglowka(self):
        self.assertEqual(skala_naglowka(self.mapa()), 4000)

    def test_pobiera_litere_i_opis(self):
        elements, warnings = elementy_z_mapy(self.mapa())
        self.assertEqual(len(elements), 2)
        self.assertFalse(warnings)
        self.assertEqual({e["id"] for e in elements},
                         {"TEST-UUID:L2", "TEST-UUID:L3"})
        self.assertTrue(all(e["wysiegnik"] is None for e in elements))

    def test_cel_wysiegnika_liczony_od_bazy_poligonu(self):
        m = self.mapa(l3="L 3 55.000 0.000 0.0000000 1.0000000 69 4.000 3.000")
        elements, _ = elementy_z_mapy(m)
        opis = next(e for e in elements if e["rodzaj"] == "opis")
        self.assertEqual(opis["wysiegnik"][1], (54, 53))

    def test_nie_traktuje_innego_a2_jako_opisu(self):
        elements, warnings = elementy_z_mapy(self.mapa(opis="SO55"))
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["rodzaj"], "litera")
        self.assertFalse(warnings)


if __name__ == "__main__":
    unittest.main()
