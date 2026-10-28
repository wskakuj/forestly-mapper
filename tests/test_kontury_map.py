"""Kontury GEO-MAP: rozłączne pierścienie, dziury i końcowe P 0."""
import unittest

from app.core import geometria_ukladu as geo
from app.core import kontury_map as km
from app.core import silnik_grupowy as engine


class KonturyTest(unittest.TestCase):
    def test_orphan_p0_does_not_create_third_contour(self):
        lines = [
            "P 1 0 0", "P 1 20 0", "P 1 20 20", "P 1 0 20",
            "P 0 0 0",
            "P 1 40 0", "P 1 60 0", "P 1 60 20", "P 1 40 20",
            "P 0 40 0",
            "P 0 0 0",  # znak końcowy obiektu, nie trzeci kontur
        ]
        fragments = km.fragmenty_z_linii(lines)
        self.assertEqual(len(fragments), 2)
        self.assertTrue(all(x["zamkniety"] for x in fragments))
        model = km.model_wydzielenia(lines)
        self.assertTrue(model["kompletne"])
        self.assertEqual(len(model["kontury"]), 2)
        self.assertFalse(geo.punkt_w_poligonie((30,10), model))
        self.assertTrue(geo.punkt_w_poligonie((10,10), model))
        self.assertTrue(geo.punkt_w_poligonie((50,10), model))
        self.assertFalse(geo.prostokat_w_poligonie((25,5,35,15), model))
        self.assertTrue(geo.prostokat_w_poligonie((2,2,8,8), model))

    def test_two_disjoint_rings_have_no_connector_edge(self):
        lines = [
            "P 1 0 0", "P 1 20 0", "P 1 20 20",
            "P 0 0 0",
            "P 1 100 0", "P 1 120 0", "P 1 120 20",
            "P 0 100 0",
            "P 0 0 0",
        ]
        pieces = km.fragmenty_z_linii(lines)
        edges = list(engine.krawedzie(pieces))
        self.assertFalse(any(
            a[0] == 20 and b[0] == 100 for a,b,_ in edges))
        self.assertFalse(engine.Granice(pieces).przecina((40,5,60,15)))

    def test_nested_ring_hole_blocks_text_even_if_corners_inside(self):
        outer = [(0,0),(100,0),(100,100),(0,100),(0,0)]
        hole = [(35,35),(65,35),(65,65),(35,65),(35,35)]
        model = {"kontury":[outer,hole],"kompletne":True}
        self.assertTrue(geo.punkt_w_poligonie((10,10),model))
        self.assertFalse(geo.punkt_w_poligonie((50,50),model))
        self.assertFalse(geo.prostokat_w_poligonie((45,45,55,55),model))
        self.assertFalse(geo.prostokat_w_poligonie((20,20,80,80),model))
        self.assertTrue(geo.prostokat_w_poligonie((8,8,18,18),model))
        self.assertTrue(geo.punkt_w_poligonie((35,50),model))
        self.assertFalse(geo.punkt_w_poligonie((35,50),model,granica=False))

    def test_unclosed_path_is_not_polygon(self):
        model = km.model_wydzielenia([
            "P 1 0 0", "P 1 20 0", "P 1 20 20",
        ])
        self.assertFalse(model["kompletne"])
        self.assertEqual(model["kontury"], [])
        self.assertFalse(km.fragmenty_z_linii(
            ["P 1 0 0","P 1 20 0","P 1 20 20"])[0]["zamkniety"])

    def test_group_generator_accepts_multicontour_owner(self):
        left = [(0,0),(70,0),(70,90),(0,90),(0,0)]
        right = [(170,0),(240,0),(240,90),(170,90),(170,0)]
        poly = {"kontury":[left,right],"kompletne":True}
        def item(ident,rodzaj,rect):
            return {"id":ident,"wydzielenie":"a","rodzaj":rodzaj,
                    "prostokat":rect,"poligon":poly,"wysiegnik":None}
        letter = item("a:L2","litera",(10,10,25,25))
        desc = item("a:L3","opis",(10,10,40,60))
        elements, report = engine.optymalizuj([letter,desc],
            wszystkie_poligony=[poly], maks_grupa=1)
        self.assertFalse(report["nierozwiazane"])
        self.assertEqual(geo.waliduj_uklad(elements), [])
        self.assertFalse(geo.prostokaty_koliduja(
            elements[0]["prostokat"],elements[1]["prostokat"]))


if __name__ == "__main__":
    unittest.main()
