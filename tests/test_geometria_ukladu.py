"""Przypadki regresyjne bez uzależnienia od GEO-MAP ani GUI."""
import unittest
from app.core.geometria_ukladu import (
    punkt_w_poligonie, prostokat_w_poligonie, odcinek_przecina_prostokat,
    przeciecie_odcinkow, wysiegniki_koliduja, waliduj_uklad,
)


class GeometriaTest(unittest.TestCase):
    KWADRAT = [(0, 0), (10, 0), (10, 10), (0, 10)]
    WKL = [(0, 0), (10, 0), (10, 10), (7, 10), (7, 3), (3, 3), (3, 10), (0, 10)]

    def test_zawartosc_prostokata_nie_tylko_rogi(self):
        r = (2, 1, 8, 4)
        self.assertTrue(all(punkt_w_poligonie(p, self.WKL) for p in
                            [(2,1),(8,1),(8,4),(2,4)]))
        self.assertFalse(prostokat_w_poligonie(r, self.WKL))
        self.assertTrue(prostokat_w_poligonie((0.5, 1, 2.5, 9), self.WKL))

    def test_poligon_wklesly_i_brzeg(self):
        self.assertFalse(punkt_w_poligonie((5, 8), self.WKL))
        self.assertTrue(punkt_w_poligonie((3, 5), self.WKL))
        self.assertFalse(punkt_w_poligonie((3, 5), self.WKL, granica=False))
        self.assertTrue(prostokat_w_poligonie((0, 0, 2, 2), self.WKL))

    def test_odcinek_przez_wlasny_napis(self):
        r = (10,10,20,20)
        self.assertTrue(odcinek_przecina_prostokat((10,15),(30,15),r))
        self.assertFalse(odcinek_przecina_prostokat((10,15),(0,15),r,wnetrze=True))
        self.assertTrue(odcinek_przecina_prostokat((10,15),(20,15),r,wnetrze=True))

    def test_wspolny_punkt_jest_dozwolony(self):
        w1 = ((20, 20), (0, 0))
        w2 = ((20, -20), (0, 0))
        self.assertFalse(wysiegniki_koliduja(w1, w2, to_samo_wydzielenie=True))
        self.assertTrue(wysiegniki_koliduja(w1, w2, to_samo_wydzielenie=False))

    def test_przeciecia_i_nakladanie(self):
        self.assertEqual(przeciecie_odcinkow((0,0),(10,10),(0,10),(10,0))[0], 'punkt')
        self.assertEqual(przeciecie_odcinkow((0,0),(10,0),(5,0),(15,0))[0], 'nakladanie')
        self.assertEqual(przeciecie_odcinkow((0,0),(10,0),(10,0),(10,5))[0], 'punkt')
        self.assertEqual(przeciecie_odcinkow((0,0),(10,0),(12,0),(15,0))[0], 'brak')
        self.assertTrue(wysiegniki_koliduja(((0,0),(10,0)), ((5,0),(15,0)),
                                            to_samo_wydzielenie=True))

    def test_wysiegnik_opisu_musi_dotykac_obwodu_wlasnej_litery(self):
        from app.core.geometria_ukladu import (
            cel_na_literze, punkt_na_obwodzie_prostokata,
            wysiegnik_trafia_w_litere)
        poly = [(0,0),(100,0),(100,100),(0,100)]
        letter = dict(id='a:L2',wydzielenie='a',rodzaj='litera',
                      prostokat=(40,40,50,50),poligon=poly,wysiegnik=None)
        desc = dict(id='a:L3',wydzielenie='a',rodzaj='opis',
                    prostokat=(40,130,60,150),poligon=poly,wysiegnik=None)
        goal = cel_na_literze(letter['prostokat'],desc['prostokat'])
        self.assertTrue(punkt_na_obwodzie_prostokata(goal,letter['prostokat']))
        correct = dict(desc,wysiegnik=((50,130),goal))
        self.assertTrue(wysiegnik_trafia_w_litere(correct['wysiegnik'],
                                                  letter['prostokat']))
        self.assertEqual(waliduj_uklad([letter,correct]), [])
        # Losowy punkt wewnątrz poligonu nie spełnia nowej reguły.
        wrong = dict(desc,wysiegnik=((50,130),(35,30)))
        self.assertIn('cel_opisu_poza_litera',
                      {e['typ'] for e in waliduj_uklad([letter,wrong])})

    def test_koniec_na_literze_wolno_ale_przejsc_przez_litere_nie(self):
        from app.core.geometria_ukladu import wysiegnik_trafia_w_litere
        r = (40,40,50,50)
        self.assertTrue(wysiegnik_trafia_w_litere(((45,100),(45,50)),r))
        self.assertFalse(wysiegnik_trafia_w_litere(((45,100),(45,40)),r))
        self.assertFalse(wysiegnik_trafia_w_litere(((45,100),(45,45)),r))

    def test_dwa_zewnetrzne_napisy_musza_miec_wspolny_cel(self):
        poly = [(0,0),(100,0),(100,100),(0,100)]
        lit = dict(id='b:L2',wydzielenie='b',rodzaj='litera',
                   prostokat=(10,120,25,135),poligon=poly,
                   wysiegnik=((17.5,120),(50,50)))
        opis = dict(id='b:L3',wydzielenie='b',rodzaj='opis',
                    prostokat=(60,120,80,140),poligon=poly,
                    wysiegnik=((70,120),(50,50)))
        self.assertEqual(waliduj_uklad([lit,opis]), [])
        altered = dict(opis,wysiegnik=((70,120),(60,55)))
        self.assertIn('rozne_cele_jednego_wydzielenia',
                      {e['typ'] for e in waliduj_uklad([lit,altered])})

    def test_opis_nie_moze_przecinac_innych_napisow_aby_dojsc_do_litery(self):
        poly = [(0,0),(100,0),(100,100),(0,100)]
        lit = dict(id='a:L2',wydzielenie='a',rodzaj='litera',
                   prostokat=(40,40,50,50),poligon=poly,wysiegnik=None)
        desc = dict(id='a:L3',wydzielenie='a',rodzaj='opis',
                    prostokat=(40,130,60,150),poligon=poly,
                    wysiegnik=((50,130),(45.2631578947,50)))
        other = dict(id='c:L2',wydzielenie='c',rodzaj='litera',
                     prostokat=(42,80,57,98),poligon=poly,wysiegnik=None)
        self.assertIn('wysiegnik_napis',
                      {e['typ'] for e in waliduj_uklad([lit,desc,other])})

    def test_walidator_wspolny_cel_opis_litera(self):
        poly = [(0,0),(10,0),(10,10),(0,10)]
        opis = dict(id='opis',wydzielenie='a',rodzaj='opis',prostokat=(20,6,24,8),
                    poligon=poly,wysiegnik=((20,7),(5,5)))
        litera = dict(id='litera',wydzielenie='a',rodzaj='litera',prostokat=(20,2,22,4),
                      poligon=poly,wysiegnik=((20,3),(5,5)))
        self.assertEqual(waliduj_uklad([opis, litera]), [])
        zly = dict(litera, wysiegnik=((20,3),(7,5)))
        self.assertIn('rozne_cele_jednego_wydzielenia',
                      {x['typ'] for x in waliduj_uklad([opis,zly])})

    def test_walidator_krzyzowanie_i_tekst(self):
        poly = [(-1,-1),(3,-1),(3,3),(-1,3)]
        a = dict(id='a',wydzielenie='a',rodzaj='opis',prostokat=(10,10,12,12),
                 poligon=poly,wysiegnik=((10,11),(1,1)))
        b = dict(id='b',wydzielenie='b',rodzaj='opis',prostokat=(10,0,12,2),
                 poligon=poly,wysiegnik=((10,1),(1,11)))
        self.assertIn('wysiegnik_wysiegnik', {x['typ'] for x in waliduj_uklad([a,b])})
        c = dict(id='c',wydzielenie='c',rodzaj='litera',prostokat=(5,5,7,7),
                 poligon=poly,wysiegnik=None)
        self.assertIn('wysiegnik_napis', {x['typ'] for x in waliduj_uklad([a,c])})

    def test_walidator_brak_i_zbedny_wysiegnik(self):
        poly = [(0,0),(10,0),(10,10),(0,10)]
        e = dict(id='a',wydzielenie='a',rodzaj='opis',prostokat=(20,20,22,22),
                 poligon=poly,wysiegnik=None)
        self.assertIn('poza_bez_wysiegnika', {x['typ'] for x in waliduj_uklad([e])})


if __name__ == '__main__':
    unittest.main()
