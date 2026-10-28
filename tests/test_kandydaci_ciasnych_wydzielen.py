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
        selected=k.wybierz_kandydatow(opts,[],poly,ile=3)
        self.assertEqual(len(selected),3)
        self.assertEqual(len({x[1] for x in selected}),3)

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
                 wysiegnik=((125,135),(50,50))),
            dict(current[1],prostokat=(150,120,180,150),
                 wysiegnik=((165,150),(50,50)))]
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
                  patch.object(k.export,"eksportuj_kopie",
                               side_effect=mock_export)):
                result=k.przygotuj(
                    Path(td)/"source.MAP",base,"6gx",
                    str(Path(td)/"proba"),ile=1)
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
