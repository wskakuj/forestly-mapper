# -*- coding: utf-8 -*-
"""Wąskie poligony: tryb propozycji jest bezpieczny i tylko testowy."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import kandydaci_ciasnych_wydzielen as k


def lab(owner,suffix,kind,r):
    return {
        "id":owner+":"+suffix,"wydzielenie":owner,
        "rodzaj":kind,"tekst":owner if kind=="litera" else "opis|1",
        "prostokat":r,
        "poligon":[(0,0),(100,0),(100,100),(0,100)],
        "wysiegnik":None
    }


class CandidatesTests(unittest.TestCase):
    def test_soft_visual_score_never_changes_actual_geometry(self):
        a=lab("a","L2","litera",(0,0,20,20))
        b=lab("b","L2","litera",(18,2,30,14))
        saved=dict(a)
        good=k.ocen_plan([a],[b],factor=.5)
        self.assertEqual(good["konflikty_pelnych_prostokatow"],1)
        self.assertEqual(good["konflikty_probnych_obwiedni"],0)
        self.assertEqual(a,saved)

    def test_diverse_families_are_selected(self):
        a=lab("a","L2","litera",(10,10,20,20))
        d=lab("a","L3","opis",(20,20,35,35))
        poly=a["poligon"]
        opts=[]
        for x,y in ((-70,45),(170,50),(-80,55),(40,165)):
            p=[a,dict(d,prostokat=(x,y,x+15,y+15),
                      wysiegnik=((x+7.5,y+15),(50,50)))]
            opts.append(p)
        selected=k.wybierz_kandydatow(
            opts,[],poly,ile=3,
            maks_odleglosc_srodka=240,
            maks_dlugosc_wysiegnika=240)
        self.assertEqual(len(selected),3)
        self.assertEqual(len({x[1] for x in selected}),3)

    def test_reject_crossing_with_existing_6fx_leader(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        letter=lab("6gx","L2","litera",(20,20,30,35))
        desc=lab("6gx","L3","opis",(70,60,85,85))
        desc["wysiegnik"]=((77.5,85),(77.5,15))
        other=lab("6fx","L3","opis",(0,0,10,10))
        other["wysiegnik"]=((5,5),(100,75))
        risks=k.ocen_plan([letter,desc],[other])
        self.assertGreater(risks["przeciecia_z_cudzymi_wysiegnikami"],0)
        diagnosis={}
        selected=k.wybierz_kandydatow(
            [[letter,desc]],[other],poly,diagnostyka=diagnosis)
        self.assertEqual(selected,[])
        self.assertEqual(
            diagnosis["odrzucone_powody"][
                "kolizja_z_istniejacymi_wysiegnikami_lub_napisami"],1)

    def test_reject_when_existing_6fx_leader_cuts_new_text(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        letter=lab("6gx","L2","litera",(20,20,30,35))
        desc=lab("6gx","L3","opis",(70,60,85,85))
        other=lab("6fx","L3","opis",(0,0,10,10))
        other["wysiegnik"]=((5,5),(90,95))
        risks=k.ocen_plan([letter,desc],[other])
        self.assertGreater(risks["cudze_wysiegniki_przez_nowe_napisy"],0)
        self.assertFalse(k.wybierz_kandydatow([[letter,desc]],[other],poly))

    def test_reject_remote_labels_but_keep_nearby_alternative(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        letter=lab("6gx","L2","litera",(20,20,30,35))
        near=lab("6gx","L3","opis",(75,70,90,90))
        far=lab("6gx","L3","opis",(500,500,515,520))
        report={}
        selected=k.wybierz_kandydatow(
            [[letter,far],[letter,near]],[],poly,
            diagnostyka=report,maks_odleglosc_srodka=120)
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0][3][1]["prostokat"],near["prostokat"])
        self.assertEqual(
            report["odrzucone_powody"][
                "napisy_zbyt_daleko_od_wydzielenia"],1)

    def test_reject_unreasonably_long_leader(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        letter=lab("6gx","L2","litera",(20,20,30,35))
        desc=lab("6gx","L3","opis",(60,60,80,80))
        desc["wysiegnik"]=((70,80),(500,500))
        report={}
        self.assertEqual(
            k.wybierz_kandydatow(
                [[letter,desc]],[],poly,diagnostyka=report),[])
        self.assertEqual(report["odrzucone_powody"]["za_dlugi_wysiegnik"],1)

    def test_local_sampler_adds_nearby_options_when_general_engine_only_finds_remote(self):
        # Bardzo dlugi L3 i waski poligon, reprezentatywne dla 6gx.
        # Generowanie nie moze zalezec od zewnetrznej siatki ogolnego
        # silnika, ktora znajduje jedynie pozycje wiele setek metrow
        # od konturu.
        poly=[(0,0),(180,0),(180,35),(0,35)]
        letter=lab("6gx","L2","litera",(80,5,96,25))
        description=lab("6gx","L3","opis",(70,-60,97,155))
        letter["poligon"]=poly
        description["poligon"]=poly
        plans=k._lokalne_plany_waskiego_poligonu(
            [letter,description],maks_odleglosc=145,
            maks_wysiegnik=130)
        self.assertTrue(plans)
        self.assertTrue(any(
            all(k._center(e["prostokat"]) is not None for e in plan)
            for plan in plans))
        self.assertTrue(all(not k.geo.waliduj_uklad(plan)
                            for plan in plans))
        bounds=k.engine.bbox(poly)
        self.assertTrue(all(
            k.engine.odleglosc_boxow(e["prostokat"],bounds)<=145
            for plan in plans for e in plan))
        self.assertTrue(all(
            not e["wysiegnik"] or
            k.math.dist(*e["wysiegnik"])<=130
            for plan in plans for e in plan))
        self.assertTrue(all(
            not e.get("wysiegnik") or
            k.geo.punkt_w_poligonie(e["wysiegnik"][1],poly)
            for plan in plans for e in plan))

    def test_long_text_can_be_close_to_border_even_if_center_far(self):
        poly=[(0,0),(220,0),(220,120),(0,120)]
        letter=lab("6gx","L2","litera",(110,-25,126,-5))
        desc=lab("6gx","L3","opis",(100,-220,127,-5))
        score={}
        chosen=k.wybierz_kandydatow(
            [[letter,desc]],[],poly,ile=1,
            maks_odleglosc_srodka=30,
            maks_dlugosc_wysiegnika=130,
            diagnostyka=score)
        self.assertEqual(len(chosen),1)
        self.assertEqual(score["przeszlo_filtry"],1)
        # Centrum tekstu 107 m od poligonu, ale krawedz
        # obrysu oddalona jest o zaledwie 5 m.
        self.assertGreater(k.math.dist(
            k._center(desc["prostokat"]),k._center(k.engine.bbox(poly))),
            100)

    def test_export_preserves_approved_neighbor_change(self):
        original=[
            lab("6gx","L2","litera",(10,10,20,25)),
            lab("6gx","L3","opis",(40,40,70,70)),
            lab("6s","L2","litera",(30,50,45,70))]
        current=[
            dict(original[0]),dict(original[1]),
            dict(original[2],prostokat=(55,50,70,70))]
        plan=[dict(original[0],prostokat=(120,120,130,135),
                   wysiegnik=((125,135),(50,50))),
              dict(original[1],prostokat=(130,120,160,150),
                   wysiegnik=((145,150),(50,50)))]
        modified=k._zmiany_z_bazy(original,current,plan)
        changes={e["id"]:e for e in modified}
        self.assertIn("6s:L2",changes)
        self.assertEqual(changes["6s:L2"]["po"],[55,50,70,70])
        self.assertEqual(changes["6gx:L3"]["po"],[130,120,160,150])
        self.assertEqual(len(changes),3)

    def test_full_pipeline_uses_baseline_and_never_touches_original(self):
        original=[
            lab("6gx","L2","litera",(10,10,20,25)),
            lab("6gx","L3","opis",(40,40,70,70)),
            lab("6s","L2","litera",(30,50,45,70))]
        current=[dict(original[0]),dict(original[1]),
                 dict(original[2],prostokat=(55,50,70,70))]
        proposal=[
            dict(current[0],prostokat=(120,120,130,135),
                 wysiegnik=((125,135),(100,100))),
            dict(current[1],prostokat=(150,120,180,150),
                 wysiegnik=((165,150),(100,100)))]
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/"before.json"
            base.write_text(json.dumps({"skala":4000,"wysokosc_mm":2.5,
                                        "tryb_automatyczny_calej_mapy":True,
                                        "zmiany":[]}))
            copied=[]
            def mock_export(source,report,dest):
                copied.append((str(source),report,str(dest)))
            with (patch.object(k.onm,"wczytaj_mape",return_value={}),
                  patch.object(k.dm,"elementy_z_mapy",
                               return_value=(original,[])),
                  patch.object(k.resume,"odtworz",
                               return_value=(current,{})),
                  patch.object(k.uk,"wszystkie_poligony",return_value=[]),
                  patch.object(k.engine,"opcje_wydzielenia",
                               return_value=[proposal]),
                  patch.object(k,"_lokalne_plany_waskiego_poligonu",
                               return_value=[]),
                  patch.object(k.export,"eksportuj_kopie",
                               side_effect=mock_export)):
                result=k.przygotuj(
                    Path(td)/"source.MAP",base,"6gx",
                    str(Path(td)/"proba"),ile=1,
                    maks_dlugosc_wysiegnika=220)
            self.assertEqual(len(copied),1)
            changes={r["id"]:r for r in copied[0][1]["zmiany"]}
            self.assertEqual(changes["6s:L2"]["po"],[55,50,70,70])
            self.assertEqual(changes["6gx:L2"]["po"],[120,120,130,135])
            self.assertEqual(result["warianty"][0]["numer"],1)
            self.assertIn("TYLKO DO OCENY",result["status"])
            self.assertEqual(original[0]["prostokat"],(10,10,20,25))
            self.assertTrue((Path(td)/"proba_ocena.json").exists())

    def test_reject_existing_destination_without_overwrite(self):
        original=[lab("6gx","L2","litera",(10,10,20,25)),
                  lab("6gx","L3","opis",(40,40,70,70))]
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/"before.json"
            base.write_text(json.dumps({"skala":4000,"wysokosc_mm":2.5}))
            (Path(td)/"proba_01.MAP").write_text("DO NOT OVERWRITE")
            with (patch.object(k.onm,"wczytaj_mape",return_value={}),
                  patch.object(k.dm,"elementy_z_mapy",
                               return_value=(original,[])),
                  patch.object(k.resume,"odtworz",
                               return_value=(original,{})),
                  patch.object(k.uk,"wszystkie_poligony",return_value=[]),
                  patch.object(k.engine,"opcje_wydzielenia",
                               return_value=[original])):
                with self.assertRaises(FileExistsError):
                    k.przygotuj("source.MAP",base,"6gx",
                               str(Path(td)/"proba"),ile=1)
            self.assertEqual((Path(td)/"proba_01.MAP").read_text(),
                             "DO NOT OVERWRITE")


if __name__=="__main__":
    unittest.main()
