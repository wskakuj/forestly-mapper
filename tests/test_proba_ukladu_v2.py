"""Testy par L2/L3 i odsunięcia od granic."""
import unittest
from app.core import geometria_ukladu as geo
from app.core.proba_ukladu_v2 import UkladOstrozny, _powieksz


def element(ident, rodzaj, prost, polygon):
    return {'id': ident, 'wydzielenie': ident.split(':')[0],
            'rodzaj': rodzaj, 'prostokat': prost,
            'poligon': polygon, 'tekst': 'a', 'wysiegnik': None}


class TestUkladOstrozny(unittest.TestCase):
    def setUp(self):
        self.square = [(0, 0), (100, 0), (100, 100), (0, 100)]

    def test_para_pokrywajaca_sie_zostaje_rozdzielona(self):
        a = element('a:L2', 'litera', (42, 42, 54, 54), self.square)
        b = element('a:L3', 'opis', (42, 42, 58, 58), self.square)
        opt = UkladOstrozny([a, b], 2.5, 2.5, 19)
        changes, result = opt.run()
        self.assertGreaterEqual(result['pary_ulozone_wspolnie'], 1)
        ra, rb = opt.indeks.boxy[a['id']], opt.indeks.boxy[b['id']]
        self.assertTrue(opt._inside(a, ra) and opt._inside(b, rb))
        self.assertFalse(geo.prostokaty_koliduja(_powieksz(ra, 1.25),
                                                  _powieksz(rb, 1.25)))
        self.assertEqual(result['po']['kolizje_napisow'], 0)

    def test_napis_na_granicy_jest_przesuwany_do_srodka(self):
        a = element('a:L2', 'litera', (0, 30, 12, 42), self.square)
        opt = UkladOstrozny([a], 3.5, 2.5, 19)
        changes, _ = opt.run()
        self.assertIn(a['id'], changes)
        self.assertTrue(geo.prostokat_w_poligonie(
            _powieksz(opt.indeks.boxy[a['id']], 3.5), self.square))

    def test_niemieszczacej_sie_pary_nie_rozpychamy_na_sile(self):
        poly = [(0, 0), (11, 0), (11, 11), (0, 11)]
        a = element('a:L2', 'litera', (20, 20, 38, 38), poly)
        b = element('a:L3', 'opis', (21, 21, 39, 39), poly)
        opt = UkladOstrozny([a, b], 2.5, 2.5, 19)
        changes, result = opt.run()
        self.assertFalse(changes)
        self.assertEqual(result['po']['poza'], {'litera': 1, 'opis': 1})

    def test_nie_zmienia_poprawnego_ukladu_pary(self):
        a = element('a:L2', 'litera', (20, 20, 30, 30), self.square)
        b = element('a:L3', 'opis', (50, 50, 65, 65), self.square)
        opt = UkladOstrozny([a, b], 2.5, 2.5, 19)
        changes, result = opt.run()
        self.assertFalse(changes)
        self.assertEqual(result['pary_bez_kolizji_i_z_marginesem'], 1)

    def test_sasiednia_litera_blokuje_przypadkowa_pozycje(self):
        a = element('a:L2', 'litera', (30, 30, 42, 42), self.square)
        b = element('a:L3', 'opis', (30, 30, 42, 42), self.square)
        c = element('b:L2', 'litera', (53, 53, 65, 65), self.square)
        opt = UkladOstrozny([a, b, c], 2.5, 2.5, 19)
        opt.run()
        self.assertEqual(opt.indeks.kolizje(a['id']), [])
        self.assertEqual(opt.indeks.kolizje(b['id']), [])
        self.assertEqual(opt.indeks.kolizje(c['id']), [])


if __name__ == '__main__':
    unittest.main()
