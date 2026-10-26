import unittest
from unittest.mock import patch
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

    def test_keep_exterior_alternatives_even_with_many_inside_candidates(self):
        poly = [(0,0),(120,0),(120,120),(0,120)]
        a = item('a:L2','litera',(40,40,50,55),poly)
        b = item('a:L3','opis',(42,41,64,76),poly)
        plans = engine.opcje_wydzielenia(
            [a,b],engine.Granice([poly]),[poly],limit=24)
        self.assertTrue(any(all(e['wysiegnik'] is None for e in p) for p in plans))
        self.assertTrue(any(any(e['wysiegnik'] is not None for e in p) for p in plans),
                        'Nie mozna odrzucic wszystkich strategii z wysiegnikiem')
        self.assertLessEqual(len(plans),24)
        self.assertTrue(all(geo.waliduj_uklad(p) == [] for p in plans))

    def test_open_polyline_does_not_create_phantom_polygon_border(self):
        """An open path outside a parcel must not close diagonally over it."""
        parcel = [(-30,-30),(30,-30),(30,30),(-30,30)]
        open_line = [(-100,100),(-100,-100),(100,-100)]
        candidate = (-10,-10,10,10)
        actual_edges = engine.Granice([
            {"punkty": parcel, "zamkniety": True},
            {"punkty": open_line, "zamkniety": False},
        ])
        self.assertFalse(actual_edges.przecina(candidate))
        # The old implementation always closed the path and invented
        # a 200-m diagonal through the label.
        wrong_edges = engine.Granice([parcel, open_line])
        self.assertTrue(wrong_edges.przecina(candidate))
        label = item('test:L2','litera',candidate,parcel)
        places = list(engine._pozycje_wewnatrz(label,actual_edges,2.5))
        self.assertTrue(places)

    def test_exterior_label_may_occupy_clear_interior_of_neighbor(self):
        """No border intersection; neighboring polygon interior is not forbidden."""
        own = [(0,0),(18,0),(18,18),(0,18)]
        neighbor = [(-200,-200),(200,-200),(200,-5),(-200,-5)]
        e = item('a:L3','opis',(0,0,20,20),own)
        borders = engine.Granice([own,neighbor])
        candidates = list(engine._pozycje_zewnetrzne(
            e,borders,[own,neighbor],2.5,limit=50))
        self.assertTrue(candidates)
        self.assertTrue(any(
            geo.punkt_w_poligonie(engine.srodek(r), neighbor,
                                  granica=False)
            and not borders.przecina(engine.powieksz(r,2.5))
            and not geo.punkt_w_poligonie(engine.srodek(r),own)
            for r in candidates))

    def test_exterior_sampler_reaches_narrow_offset_corridor(self):
        """Pozycje pomiędzy starymi próbkami muszą być osiągalne.

        Zakres i położenie są w jednostkach względnych etykiety; żaden
        konkretny UUID ani współrzędne mapy BYSŁAW nie są zakodowane.
        """
        poly = [(0,0),(40,0),(40,40),(0,40)]
        e = item('area:L3','opis',(10,0,30,40),poly)
        class NarrowFreeCorridor:
            def przecina(self, rect):
                x,y = engine.srodek(rect)
                return not (abs(x - 26) < .1 and abs(y - 68) < .1)
        positions = list(engine._pozycje_zewnetrzne(
            e,NarrowFreeCorridor(),[poly],margines=2.5))
        self.assertEqual(len(positions),1)
        x,y = engine.srodek(positions[0])
        self.assertAlmostEqual(x,26)
        self.assertAlmostEqual(y,68)

    def test_exterior_sampler_uses_label_relative_distances(self):
        poly = [(0,0),(40,0),(40,40),(0,40)]
        small = item('small:L3','opis',(10,0,30,40),poly)
        big = item('big:L3','opis',(10,-20,30,60),poly)
        class Free:
            def przecina(self, rect):
                return False
        small_centers = [engine.srodek(r) for r in
                         engine._pozycje_zewnetrzne(
                             small,Free(),[poly],margines=2.5)]
        big_centers = [engine.srodek(r) for r in
                       engine._pozycje_zewnetrzne(
                           big,Free(),[poly],margines=2.5)]
        self.assertTrue(small_centers)
        self.assertTrue(big_centers)
        self.assertNotEqual(small_centers,big_centers)

    def test_generator_connects_exterior_description_to_inside_letter(self):
        poly = [(0,0),(40,0),(40,40),(0,40)]
        letter = item('a:L2','litera',(14,14,24,24),poly)
        desc = item('a:L3','opis',(0,0,75,75),poly)
        plans = engine.opcje_wydzielenia(
            [letter,desc],engine.Granice([poly]),[poly],limit=24)
        mixed = [p for p in plans
                 if any(e['rodzaj'] == 'litera' and not e['wysiegnik'] for e in p)
                 and any(e['rodzaj'] == 'opis' and e['wysiegnik'] for e in p)]
        self.assertTrue(mixed, "Generator nie znalazl polaczenia opisu z litera")
        for plan in mixed:
            inside_letter = next(e for e in plan if e['rodzaj'] == 'litera')
            outside_desc = next(e for e in plan if e['rodzaj'] == 'opis')
            self.assertTrue(geo.wysiegnik_trafia_w_litere(
                outside_desc['wysiegnik'], inside_letter['prostokat']))
            self.assertEqual(geo.waliduj_uklad(plan), [])

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

    def test_alone_can_be_fixed_when_neighbor_alternatives_are_blocked(self):
        """A correct neighbor must not force an impossible joint rearrangement."""
        pa = [(0,0),(80,0),(80,80),(0,80)]
        pb = [(0,80),(80,80),(80,160),(0,160)]
        a = item('a:L2','litera',(20,20,30,30),pa)
        desc = item('a:L3','opis',(20,20,44,45),pa)
        b = item('b:L2','litera',(30,105,45,119),pb)
        real = engine.opcje_wydzielenia

        def candidates(group, *args, **kwargs):
            if group[0]['wydzielenie'] == 'b':
                # A deliberately incompatible alternative for the
                # already correct neighbour; its ORIGINAL placement is fine.
                return [[dict(group[0], prostokat=(-5,-5,85,75),
                              wysiegnik=((40,75),(40,115)))]]
            return real(group, *args, **kwargs)

        with patch.object(engine,'opcje_wydzielenia',side_effect=candidates):
            result, report = engine.optymalizuj(
                [a,desc,b],wszystkie_poligony=[pa,pb],
                maks_grupa=2,przebiegi=1)
        self.assertEqual(geo.waliduj_uklad(result), [])
        self.assertEqual(result[2]['prostokat'],b['prostokat'])
        self.assertGreaterEqual(report['udane_grupy'],1)

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

    def test_targeted_scan_preserves_other_conflicting_groups(self):
        pa = [(0,0),(100,0),(100,100),(0,100)]
        pb = [(250,0),(350,0),(350,100),(250,100)]
        items = [
            item('a:L2','litera',(20,20,30,30),pa),
            item('a:L3','opis',(20,20,40,40),pa),
            item('b:L2','litera',(270,20,280,30),pb),
            item('b:L3','opis',(270,20,290,40),pb),
        ]
        actual, report = engine.optymalizuj(
            items, wszystkie_poligony=[pa,pb], maks_grupa=1,
            wybrane_wydzielenia={'b'})
        self.assertEqual(actual[0]['prostokat'],items[0]['prostokat'])
        self.assertEqual(actual[1]['prostokat'],items[1]['prostokat'])
        self.assertFalse(geo.prostokaty_koliduja(
            actual[2]['prostokat'],actual[3]['prostokat']))
        self.assertGreaterEqual(report['pominiete_przez_wybor'],1)
        self.assertTrue(report['analiza_czesciowa'])

    def test_most_conflicted_group_is_processed_first(self):
        """Priority must depend on real conflicts, not arbitrary UUID order."""
        pa = [(0,0),(100,0),(100,100),(0,100)]
        pb = [(300,0),(400,0),(400,100),(300,100)]
        elements = [
            item('a:L2','litera',(20,20,32,32),pa),
            item('a:L3','opis',(24,24,44,44),pa),
            item('z:L2','litera',(425,25,445,45),pb),
            item('z:L3','opis',(428,28,453,53),pb),
        ]
        progress = []
        with patch.object(engine, 'opcje_wydzielenia', return_value=[]):
            _, report = engine.optymalizuj(
                elements, wszystkie_poligony=[pa,pb],
                limit_grup=1, przebiegi=1, postep=progress.append)
        self.assertEqual(report['rozpatrzone_grupy'], 1)
        self.assertEqual(progress[0]['wydzielenie'], 'z')

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
