import unittest
from app.core import geometria_ukladu as geo
from app.core import silnik_grupowy as engine


def item(name, kind, rect, poly, district=None):
    return dict(id=name, wydzielenie=district or name.split(':')[0],
                rodzaj=kind, prostokat=rect, poligon=poly, wysiegnik=None)


class EngineTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(engine.optymalizuj([])[0], [])

    def test_duplicate_ids(self):
        poly = [(0,0),(40,0),(40,40),(0,40)]
        e = item('a:L2','litera',(10,10,15,15),poly)
        with self.assertRaises(ValueError):
            engine.optymalizuj([e,e])

    def test_internal_pair_no_overlap(self):
        poly = [(0,0),(100,0),(100,100),(0,100)]
        a = item('a:L2','litera',(45,45,55,55),poly)
        b = item('a:L3','opis',(45,45,65,65),poly)
        output, report = engine.optymalizuj([a,b], wszystkie_poligony=[poly])
        self.assertFalse(geo.prostokaty_koliduja(
            output[0]['prostokat'],output[1]['prostokat']))
        self.assertFalse(report['nierozwiazane'])
        self.assertEqual(a['prostokat'],(45,45,55,55))

    def test_common_anchor_for_two_exterior_labels(self):
        poly = [(0,0),(18,0),(18,18),(0,18)]
        a = item('a:L2','litera',(4,4,24,24),poly)
        b = item('a:L3','opis',(4,4,24,24),poly)
        boundaries = engine.Granice([poly])
        plans = engine.opcje_wydzielenia([a,b],boundaries,[poly])
        both = [p for p in plans if all(e['wysiegnik'] for e in p)]
        self.assertTrue(both, "Brak poprawnej pary z dwoma wysiegnikami")
        self.assertEqual(both[0][0]['wysiegnik'][1],
                         both[0][1]['wysiegnik'][1])
        self.assertEqual(geo.waliduj_uklad(both[0]), [])

    def test_group_neighbors_do_not_include_distant_polygons(self):
        a = [(0,0),(30,0),(30,30),(0,30)]
        nearby = [(30,0),(60,0),(60,30),(30,30)]
        distant = [(1000,0),(1030,0),(1030,30),(1000,30)]
        groups = {
            'a': [item('a:L2','litera',(10,10,18,18),a)],
            'near': [item('near:L2','litera',(35,10,43,18),nearby)],
            'far': [item('far:L2','litera',(1010,10,1018,18),distant)],
        }
        self.assertEqual(engine._sasiedztwo(groups,'a'),['a','near'])

    def test_two_exterior_labels_get_same_target(self):
        poly = [(0,0),(18,0),(18,18),(0,18)]
        a = item('a:L2','litera',(4,4,24,24),poly)
        b = item('a:L3','opis',(4,4,24,24),poly)
        after, report = engine.optymalizuj([a,b],wszystkie_poligony=[poly])
        self.assertEqual(report['nierozwiazane'], [])
        self.assertTrue(all(e['wysiegnik'] is not None for e in after))
        self.assertEqual(after[0]['wysiegnik'][1],after[1]['wysiegnik'][1])
        self.assertEqual(geo.waliduj_uklad(after), [])

    def test_progress_callback_and_partial_scan(self):
        pa = [(0,0),(100,0),(100,100),(0,100)]
        pb = [(200,0),(300,0),(300,100),(200,100)]
        items = [
            item('a:L2','litera',(20,20,30,30),pa),
            item('a:L3','opis',(20,20,40,40),pa),
            item('b:L2','litera',(220,20,230,30),pb),
            item('b:L3','opis',(220,20,240,40),pb),
        ]
        messages = []
        _, result = engine.optymalizuj(
            items, wszystkie_poligony=[pa,pb], limit_grup=1,
            przebiegi=1, postep=messages.append)
        self.assertEqual(len(messages), 1)
        self.assertEqual(result["rozpatrzone_grupy"], 1)
        self.assertTrue(result["analiza_czesciowa"])
        self.assertGreaterEqual(result["pominiete_przez_limit"], 1)

    def test_farther_move_is_always_more_expensive(self):
        poly = [(0,0),(1000,0),(1000,1000),(0,1000)]
        e = item('a:L3','opis',(0,0,10,20),poly)
        original = {e['id']: e}
        p1 = dict(e, prostokat=(130,0,140,20))
        p2 = dict(e, prostokat=(260,0,270,20))
        score1 = engine._koszt([p1], original)
        score2 = engine._koszt([p2], original)
        self.assertGreater(score2, score1)

    def test_move_score_scales_with_label_size(self):
        poly = [(0,0),(1000,0),(1000,1000),(0,1000)]
        e = item('a:L3','opis',(0,0,10,20),poly)
        moved = dict(e, prostokat=(130,0,140,20))
        large = dict(e, prostokat=(0,0,100,200))
        large_move = dict(large, prostokat=(1300,0,1400,200))
        self.assertAlmostEqual(engine._koszt([moved],{e['id']:e}),
                               engine._koszt([large_move], {e['id']:large}))

    def test_deterministic(self):
        poly = [(0,0),(90,0),(90,90),(0,90)]
        items = [item('a:L2','litera',(20,20,32,32),poly),
                 item('a:L3','opis',(20,20,42,42),poly)]
        self.assertEqual(engine.optymalizuj(items),engine.optymalizuj(items))


if __name__ == '__main__':
    unittest.main()
