"""Regresja: bezpieczne przesuwanie napisów wyłącznie do ich poligonów."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core import proba_ukladu as p
from app.core import opisy_na_mape as onm


def napis(ident, prost, poligon):
    return {"id": ident, "wydzielenie": ident.split(":")[0],
            "rodzaj": "opis", "tekst": "SO40|0.50",
            "prostokat": prost, "poligon": poligon, "wysiegnik": None}


class ProbaUkladuTest(unittest.TestCase):
    def test_przesuwa_napis_do_wlasnego_poligonu(self):
        poligon = [(0, 0), (100, 0), (100, 100), (0, 100)]
        e = napis("a:L3", (110, 110, 120, 120), poligon)
        zmiany, raport = p.uloz_wewnatrz([e])
        self.assertIn("a:L3", zmiany)
        self.assertEqual(raport["po"]["poza"].get("opis", 0), 0)
        self.assertEqual(raport["po"]["kolizje_napisow"], 0)

    def test_bez_wolnego_miejsca_nie_rysuje_wysiegnika(self):
        poligon = [(0, 0), (8, 0), (8, 8), (0, 8)]
        e = napis("a:L3", (20, 20, 40, 40), poligon)
        zmiany, raport = p.uloz_wewnatrz([e])
        self.assertEqual(zmiany, {})
        self.assertEqual(raport["po"]["poza"].get("opis", 0), 1)

    def test_nie_psuje_poprawnego_napisu(self):
        poligon = [(0, 0), (100, 0), (100, 100), (0, 100)]
        e = napis("a:L3", (20, 20, 30, 30), poligon)
        zmiany, raport = p.uloz_wewnatrz([e])
        self.assertEqual(zmiany, {})
        self.assertEqual(raport["po"]["kolizje_napisow"], 0)

    def test_dwa_napisy_sa_rozdzielone(self):
        poligon = [(0, 0), (100, 0), (100, 100), (0, 100)]
        a = napis("a:L3", (20, 20, 40, 40), poligon)
        b = napis("b:L3", (20, 20, 40, 40), poligon)
        zmiany, raport = p.uloz_wewnatrz([a, b])
        self.assertTrue(zmiany)
        self.assertEqual(raport["po"]["kolizje_napisow"], 0)

    def test_odmowa_nadpisania_wejscia(self):
        with TemporaryDirectory() as td:
            sciezka = Path(td) / "mapa.MAP"
            sciezka.write_bytes(b"bez zmian")
            with self.assertRaises(ValueError):
                p.zapisz_kopie_mapy({"lines": []}, [], {}, sciezka, sciezka)
            self.assertEqual(sciezka.read_bytes(), b"bez zmian")


if __name__ == "__main__":
    unittest.main()
