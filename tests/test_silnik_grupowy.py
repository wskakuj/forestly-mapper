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

    def test_multipart_local_grid_finds_narrow_distant_ring(self):
        near = [(0,0),(10,0),(10,10),(0,10),(0,0)]
        far = [(1000,0),(1040,0),(1040,40),(1000,40),(1000,0)]
        model = {"kontury":[near,far],"kompletne":True}
        # Ogólna siatka bbox (szerokość 1040) pomija drugi pierścień.
        e = item('a:L2','litera',(1,1,21,21),model)
        found = list(engine._pozycje_wewnatrz(
            e, engine.Granice([model]), margines=2.5, limit=9))
        self.assertTrue(found, "Lokalna siatka musi odnalezc miejsce")
        self.assertTrue(all(engine.srodek(r)[0] >= 1000 for r in found))
        self.assertTrue(all(geo.prostokat_w_poligonie(r,model)
                            for r in found))

    def test_multiring_targets_sample_individual_components(self):
        small = [(0,0),(20,0),(20,20),(0,20),(0,0)]
        distant = [(1000,0),(1020,0),(1020,20),(1000,20),(1000,0)]
        poly = {"kontury":[small,distant],"kompletne":True}
        base = list(engine._cele(poly,n=7))
        extended = list(engine._cele(poly,n=9))
        self.assertTrue(any(0 < x < 20 for x,y in extended))
        self.assertTrue(any(1000 < x < 1020 for x,y in extended))
        self.assertGreater(len(extended),len(base))
        self.assertEqual(len(extended),len(set(extended)))
        self.assertTrue(all(geo.punkt_w_poligonie(p,poly)
                            for p in extended))

    def test_weighted_plan_pool_reserves_clean_family(self):
        """Cheaper but penalized candidates must not erase a rare clean one."""
        poly = [(0,0),(100,0),(100,100),(0,100)]
        label = item('a:L2','litera',(20,20,30,30),poly)
        near = [(200+i*3,20,210+i*3,30) for i in range(40)]
        clean = (6000,20,6010,30)
        boxes = near + [clean]
        def positions(*args,**kwargs):
            return iter(boxes)
        def cost(plan):
            return 0 if plan[0]["prostokat"] == clean else 50
        with (patch.object(engine,'_pozycje_wewnatrz',
                           side_effect=lambda *a,**kw:iter(())),
              patch.object(engine,'_pozycje_zewnetrzne',
                           side_effect=positions),
              patch.object(engine,'_cele',
                           side_effect=lambda *a,**kw:iter([(50,50)])),
              patch.object(engine,'_poprawne',return_value=True)):
            plain=engine.opcje_wydzielenia(
                [label],engine.Granice([]),[],limit=25)
            weighted=engine.opcje_wydzielenia(
                [label],engine.Granice([]),[],limit=25,
                ocena_dodatkowa=cost)
        self.assertEqual(len(plain),25)
        self.assertEqual(len(weighted),25)
        self.assertNotIn(clean,[p[0]["prostokat"] for p in plain])
        self.assertIn(clean,[p[0]["prostokat"] for p in weighted])

    def test_weighted_target_sampling_keeps_farther_crossing_free_goal(self):
        poly = [(0,0),(100,0),(100,100),(0,100)]
        letter = item('a:L2','litera',(0,0,10,10),poly)
        short=(10,5)
        far=(70,5)
        candidates=[short,far]
        no_penalty=engine._cele_ocenione(
            candidates,[(letter,letter["prostokat"])],None,limit=1)
        self.assertEqual(no_penalty,[short])
        def crossing_penalty(plan):
            return 100.0 if plan[0]["wysiegnik"][1]==short else 0.0
        optimized=engine._cele_ocenione(
            candidates,[(letter,letter["prostokat"])],
            crossing_penalty,limit=1)
        self.assertEqual(optimized,[far])

    def test_multiring_exterior_positions_cover_both_local_contours(self):
        ring_a = [(0,0),(100,0),(100,100),(0,100),(0,0)]
        ring_b = [(900,0),(1000,0),(1000,100),(900,100),(900,0)]
        multi = {"kontury":[ring_a,ring_b],"kompletne":True}
        desc = item('area:L3','opis',(0,0,30,30),multi)
        candidates = list(engine._pozycje_zewnetrzne(
            desc,engine.Granice([multi]),[multi],margines=2.5,
            limit=96))
        center = [engine.srodek(r) for r in candidates]
        self.assertTrue(any(900 < x < 1000 and y > 100
                            for x,y in center),
                        "Drugi kontur potrzebuje osobnej siatki zewnetrznej")
        self.assertTrue(any(0 < x < 100 and y > 100
                            for x,y in center))

    def test_successful_but_stretched_pair_is_refined_after_24(self):
        """A valid initial solution must not block a prettier 72-plan variant."""
        pa = [(0,0),(100,0),(100,100),(0,100)]
        pb = [(300,0),(400,0),(400,100),(300,100)]
        elements = [
            item('a:L2','litera',(20,20,35,35),pa),
            item('a:L3','opis',(20,20,50,70),pa),
            item('b:L2','litera',(320,20,335,35),pb),
            item('b:L3','opis',(320,45,350,95),pb),
        ]
        def pair(outside_desc):
            target = (50,50)
            rl = (10,140,25,160)
            rd = outside_desc
            return [
                dict(elements[0],prostokat=rl,
                     wysiegnik=engine.lider(rl,target)),
                dict(elements[1],prostokat=rd,
                     wysiegnik=engine.lider(rd,target)),
            ]
        far = pair((80,170,110,220))
        compact = pair((35,170,65,220))
        fixed = [elements[2],elements[3]]
        def plans(group,*args,**kwargs):
            if group[0]['wydzielenie'] == 'b':
                return [fixed]
            return [compact if kwargs.get('limit',24) > 24 else far]
        self.assertGreater(engine._maks_odstep_pary(far), .75)
        self.assertLess(engine._maks_odstep_pary(compact),
                        engine._maks_odstep_pary(far))
        with patch.object(engine,'opcje_wydzielenia',side_effect=plans):
            actual, report = engine.optymalizuj(
                elements, wszystkie_poligony=[pa,pb],
                wybrane_wydzielenia={'a','b'},
                maks_grupa=2, przebiegi=1)
        info = report['wspolna_proba']
        self.assertTrue(info['sukces'])
        self.assertEqual(info['wybrany_limit_planow'],72)
        self.assertEqual([p['limit_planow_na_wydzielenie']
                          for p in info['proby']], [24,72])
        self.assertEqual(next(e for e in actual if e['id']=='a:L3')
                         ['prostokat'],compact[1]['prostokat'])

    def test_refinement_keeps_best_when_extended_pool_is_worse(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        e1=item('a:L2','litera',(20,20,35,35),poly)
        e2=item('a:L3','opis',(20,20,50,70),poly)
        a=[dict(e1,prostokat=(15,140,30,160),
                wysiegnik=engine.lider((15,140,30,160),(50,50))),
           dict(e2,prostokat=(50,170,80,220),
                wysiegnik=engine.lider((50,170,80,220),(50,50)))]
        b=[dict(a[0]),dict(a[1],prostokat=(300,170,330,220),
                             wysiegnik=engine.lider((300,170,330,220),(50,50)))]
        original={e['id']:e for e in (e1,e2)}
        self.assertLess(engine._koszt(a,original),
                        engine._koszt(b,original))

    def test_targeted_joint_attempt_expands_pool_after_24_fail(self):
        pa = [(0,0),(100,0),(100,100),(0,100)]
        pb = [(200,0),(300,0),(300,100),(200,100)]
        elements = [
            item('a:L2','litera',(30,30,45,45),pa),
            item('a:L3','opis',(30,30,55,55),pa),
            item('b:L2','litera',(230,30,245,45),pb),
            item('b:L3','opis',(230,30,255,55),pb),
        ]
        seen_limits = []
        def plans(group,*args,**kwargs):
            code = group[0]['wydzielenie']
            cap = kwargs.get('limit',24)
            seen_limits.append(cap)
            # Pierwszy przebieg po 24 dla obu wymusza konflikt
            # tych dwóch grup, lecz po rozszerzeniu jeden może
            # wykorzystać inną pozycję we własnym poligonie.
            shift = (0 if code == 'a' else 200)
            if cap == 24:
                shift = 0
            return [[dict(e,prostokat=(
                (20 if e['rodzaj']=='litera' else 20)+shift,
                (20 if e['rodzaj']=='litera' else 45),
                (35 if e['rodzaj']=='litera' else 45)+shift,
                (35 if e['rodzaj']=='litera' else 70)
            )) for e in group]]
        with patch.object(engine,'opcje_wydzielenia',side_effect=plans):
            placed, report = engine.optymalizuj(
                elements, wszystkie_poligony=[pa,pb],
                wybrane_wydzielenia={'a','b'},
                maks_grupa=2, przebiegi=1)
        self.assertEqual(report['wspolna_proba']['sukces'],True)
        self.assertEqual([p['limit_planow_na_wydzielenie']
                          for p in report['wspolna_proba']['proby']],
                         [24,72])
        self.assertIn(72,seen_limits)
        self.assertFalse(geo.waliduj_uklad(placed))

    def test_joint_solver_prefers_crossing_free_plan_with_soft_cost(self):
        pa = [(0,0),(100,0),(100,100),(0,100)]
        pb = [(200,0),(300,0),(300,100),(200,100)]
        ea = item('a:L2','litera',(20,20,40,40),pa)
        eb = item('b:L2','litera',(220,20,240,40),pb)
        moved = dict(ea,prostokat=(55,20,75,40))
        original = {e['id']:e for e in (ea,eb)}
        plans = {'a':[[ea],[moved]],'b':[[eb]]}
        baseline,_ = engine._wspolny_plan_dokladny(
            ['a','b'],plans.__getitem__,original,original,2.5)
        self.assertEqual(next(e for e in baseline if e['id']=='a:L2')
                         ['prostokat'], ea['prostokat'])
        def penalty(plan):
            return 50 if any(e['id']=='a:L2' and
                             e['prostokat']==ea['prostokat']
                             for e in plan) else 0
        scored,report = engine._wspolny_plan_dokladny(
            ['a','b'],plans.__getitem__,original,original,2.5,
            ocena_dodatkowa=penalty)
        self.assertTrue(report['sukces'])
        self.assertEqual(next(e for e in scored if e['id']=='a:L2')
                         ['prostokat'], moved['prostokat'])

    def test_exact_joint_search_does_not_drop_necessary_third_plan(self):
        """A cheap partial combination is not sufficient for all three."""
        poly = [(0,0),(300,0),(300,300),(0,300)]
        orig = {
            'a:L2': item('a:L2','litera',(5,5,15,15),poly),
            'b:L2': item('b:L2','litera',(35,5,45,15),poly),
            'c:L2': item('c:L2','litera',(65,5,75,15),poly),
        }
        def rectplan(k,box):
            return [dict(orig[k + ':L2'], prostokat=box)]
        plans = {
            'a': [rectplan('a',(10,10,20,20)),
                  rectplan('a',(60,60,70,70))],
            'b': [rectplan('b',(60,60,70,70)),
                  rectplan('b',(90,10,100,20))],
            'c': [rectplan('c',(10,10,20,20))],
        }
        chosen, report = engine._wspolny_plan_dokladny(
            ['a','b','c'],plans.__getitem__,orig,orig,2.5)
        self.assertTrue(report['sukces'])
        self.assertEqual(len(chosen),3)
        self.assertEqual(
            next(e for e in chosen if e['id'] == 'a:L2')['prostokat'],
            (60,60,70,70))
        self.assertEqual(
            next(e for e in chosen if e['id'] == 'b:L2')['prostokat'],
            (90,10,100,20))
        self.assertFalse(geo.waliduj_uklad(chosen))

    def test_explicit_small_cluster_is_optimized_jointly_before_greedy(self):
        items = []
        plans = {}
        for number, label in enumerate(('a','b','c')):
            x = number * 200
            poly = [(x,0),(x+100,0),(x+100,100),(x,100)]
            letter = item(label+':L2','litera',(x+20,20,x+35,35),poly)
            desc = item(label+':L3','opis',(x+20,20,x+45,45),poly)
            items.extend([letter,desc])
            plans[label] = [[dict(letter,prostokat=(x+10,10,x+25,25)),
                             dict(desc,prostokat=(x+10,45,x+35,70))]]
        with patch.object(engine,'opcje_wydzielenia',
                          side_effect=lambda group,*a,**kw:
                          plans[group[0]['wydzielenie']]):
            result, report = engine.optymalizuj(
                items, maks_grupa=3, przebiegi=1,
                wybrane_wydzielenia={'a','b','c'},
                wszystkie_poligony=[e['poligon'] for e in items])
        self.assertEqual(report['wspolna_proba']['sukces'],True)
        self.assertEqual(report['wspolna_proba']['liczba_wydzielen'],3)
        self.assertEqual(geo.waliduj_uklad(result),[])
        self.assertEqual(len(result),6)

    def test_actual_label_blocker_selected_before_nearest_polygon(self):
        """Geometrically distant owner may have a label blocking the target."""
        pa = [(0,0),(100,0),(100,100),(0,100)]
        near = [(100,0),(200,0),(200,100),(100,100)]
        far = [(1000,0),(1100,0),(1100,100),(1000,100)]
        target = item('a:L2','litera',(105,15,125,35),pa)
        neighbor = item('c:L2','litera',(150,70,165,85),near)
        blocker = item('d:L2','litera',(20,20,40,40),far)
        plan_a = dict(target,prostokat=(20,20,40,40))
        plan_d = dict(blocker,prostokat=(1030,20,1050,40))

        def candidates(group,*args,**kwargs):
            uuid = group[0]["wydzielenie"]
            if uuid == 'a':
                return [[plan_a]]
            if uuid == 'd':
                return [[plan_d]]
            return [[group[0]]]

        # Wg odległości do poligonów najbliższy jest c,
        # ale realnym blokerem napisu a jest d.
        with patch.object(engine,'opcje_wydzielenia',side_effect=candidates):
            placed, report = engine.optymalizuj(
                [target,neighbor,blocker],
                wszystkie_poligony=[pa,near,far],
                maks_grupa=2,przebiegi=1,
                wybrane_wydzielenia={'a'})
        by_id = {e['id']:e for e in placed}
        self.assertEqual(by_id['a:L2']['prostokat'],plan_a['prostokat'])
        self.assertEqual(by_id['d:L2']['prostokat'],plan_d['prostokat'])
        self.assertEqual(by_id['c:L2']['prostokat'],neighbor['prostokat'])
        self.assertGreaterEqual(report['udane_grupy'],1)
        self.assertFalse(geo.waliduj_uklad(placed))

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

    def test_aesthetic_score_prefers_compact_pair_at_equal_movement(self):
        poly = [(0,0),(1000,0),(1000,1000),(0,1000)]
        letter = item('a:L2','litera',(0,0,10,20),poly)
        desc = item('a:L3','opis',(0,0,20,20),poly)
        original = {e['id']:e for e in (letter,desc)}
        near = [letter,dict(desc,prostokat=(-25,0,-5,20))]
        far = [letter,dict(desc,prostokat=(25,0,45,20))]
        # Ruch opisu jest w obu przypadkach taki sam (25 jednostek).
        # Różni się jedynie odstęp do litery: 5 kontra 15.
        self.assertAlmostEqual(
            engine._koszt(far,original) - engine._koszt(near,original),
            7.0 * (15-5) / 20)
        target = (3,50)
        both_near = [dict(e,wysiegnik=(engine.srodek(e['prostokat']),target))
                     for e in near]
        both_far = [dict(e,wysiegnik=(engine.srodek(e['prostokat']),target))
                    for e in far]
        # Dwa zewnętrzne napisy mają większą preferencję kompaktowości.
        # Korekta opisuje tylko ranking, nie zwalnia z walidacji.
        self.assertGreater(engine._koszt(both_far,original),
                           engine._koszt(both_near,original))

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
