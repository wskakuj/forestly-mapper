# -*- coding: utf-8 -*-
"""Wybrany do dalszej oceny wariant MAP nie może zmienić mapy sąsiadów."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import awansuj_wybrany_wariant as promote


def label(owner,kind,rect,leader=None):
    return {
        "id":owner+":L"+("2" if kind=="litera" else "3"),
        "wydzielenie":owner,"rodzaj":kind,
        "tekst":owner if kind=="litera" else "opis|1",
        "prostokat":rect,"wysiegnik":leader,
        "poligon":[(0,0),(100,0),(100,100),(0,100)]
    }


class CandidatePromotionTests(unittest.TestCase):
    def test_reject_any_nonlabel_geometry_change(self):
        a={"lines":[
            ";# Plik N=[2] CHK=[abc]",
            "L 2 0.000 0.000 0.0000000 1.0000000 5",
            "P 1 20 30"]}
        b={"lines":[
            ";# Plik N=[2] CHK=[def]",
            "L 2 5.000 9.000 0.0000000 1.0000000 5",
            "P 1 22 30"]}
        with patch.object(promote.export,"_mapowanie_linii",
                          return_value={"a:L2":1}):
            with self.assertRaisesRegex(ValueError,"niezatwierdzona linie"):
                promote._sprawdz_nietekstowe_linie(a,b)
        b["lines"][2]="P 1 20 30"
        with patch.object(promote.export,"_mapowanie_linii",
                          return_value={"a:L2":1}):
            promote._sprawdz_nietekstowe_linie(a,b)
        b["lines"][1]="L 2 5.000 9.000 2.0 1.0000000 5"
        with patch.object(promote.export,"_mapowanie_linii",
                          return_value={"a:L2":1}):
            with self.assertRaisesRegex(ValueError,"fontu"):
                promote._sprawdz_nietekstowe_linie(a,b)

    def test_reject_foreign_leader_crossing(self):
        chosen=[label("6gx","litera",(40,70,50,82),
                      ((45,70),(50,50)))]
        other=[label("6fx","opis",(90,90,100,100),
                     ((95,95),(5,5)))]
        with self.assertRaisesRegex(ValueError,"cudzy wysiegnik"):
            promote._sprawdz_wysiegniki(chosen,other)

    def test_build_changes_preserves_already_approved_6s(self):
        original=[label("6s","litera",(0,0,10,20)),
                  label("6gx","litera",(20,20,30,40)),
                  label("6gx","opis",(20,10,45,60))]
        final=[dict(original[0],prostokat=(10,10,20,30)),
               dict(original[1],prostokat=(55,55,65,75)),
               dict(original[2],prostokat=(80,80,105,130))]
        changes=promote._zmiany(original,final)
        self.assertEqual(len(changes),3)
        self.assertIn("6s:L2",{r["id"] for r in changes})
        self.assertEqual(changes[-1]["po"],[80,80,105,130])
        self.assertEqual(original[0]["prostokat"],(0,0,10,20))

    def test_selected_sample_becomes_resumable_base(self):
        original=[label("6gx","litera",(20,20,30,35)),
                  label("6gx","opis",(20,10,45,60)),
                  label("6s","litera",(120,20,135,35))]
        current=[dict(original[0]),dict(original[1]),
                 dict(original[2],prostokat=(140,20,155,35))]
        anchor=(50,50)
        selected=[
            dict(original[0],prostokat=(40,110,50,125),
                 wysiegnik=((45,110),anchor)),
            dict(original[1],prostokat=(60,110,85,160),
                 wysiegnik=((72.5,110),anchor))
        ]
        source_lines=[";# N=4 CHK=[abc]",
                      "L 2 0.000 0.000 0.0 1.0 5",
                      "L 3 0.000 0.000 0.0 1.0 5",
                      "L 2 0.000 0.000 0.0 1.0 5"]
        sample_lines=[";# N=4 CHK=[def]",
                      "L 2 1.000 1.000 0.0 1.0 69 2.0 2.0",
                      "L 3 2.000 3.000 0.0 1.0 69 2.0 2.0",
                      "L 2 4.000 5.000 0.0 1.0 5"]
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"original.MAP"
            choice=Path(td)/"selected.MAP"
            source.write_bytes(b"SOURCE")
            choice.write_bytes(b"SELECTED")
            base=Path(td)/"base.json"
            base.write_text(json.dumps({
                "skala":4000,"wysokosc_mm":2.5,
                "zmiany":[{"id":"6s:L2"}],
                "kara_za_przeciecie":25,
                "kara_wielokrotnej_granicy":50,
                "tryb_automatyczny_calej_mapy":True,
                "sha256_zrodla":"x",
                "liczba_napisow":3}))
            out=Path(td)/"promoted.json"
            copied=Path(td)/"promoted.MAP"
            fake_index=type("Index",(),{
                "kara_planu":lambda self,*args:0.0})()
            maps=[{"lines":source_lines},{"lines":sample_lines}]
            with (patch.object(promote.onm,"wczytaj_mape",
                               side_effect=maps),
                  patch.object(promote.export,"_mapowanie_linii",
                               return_value={"6gx:L2":1,"6gx:L3":2,"6s:L2":3}),
                  patch.object(promote.dm,"elementy_z_mapy",
                               return_value=(original,[])),
                  patch.object(promote.resume,"odtworz",
                               return_value=(current,{})),
                  patch.object(promote.manual,"wczytaj_wzorce",
                               return_value={"6gx":selected}),
                  patch.object(promote.uk,"wszystkie_poligony",
                               return_value=[]),
                  patch.object(promote.pm,"IndeksPrzeciec",
                               return_value=fake_index),
                  patch.object(promote.diag,
                               "_przeciecia_wysiegnikow_z_obiektami",
                               return_value=[])):
                details=promote.awansuj(
                    source,base,choice,"6gx",out,copied)
            report=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(details["zapisane_zmiany"],3)
            self.assertEqual(report["wybrany_wariant_operatora"][
                "status"],"NAJLEPSZY_WYBRANY_DO_DALSZEJ_OCENY")
            self.assertEqual(report["liczba_nierozwiazanych"],len(
                promote.geo.waliduj_uklad(
                    [*selected,current[2]])))
            self.assertEqual(copied.read_bytes(),b"SELECTED")
            self.assertEqual(source.read_bytes(),b"SOURCE")
            self.assertIn("6s:L2",{e["id"] for e in report["zmiany"]})
            with self.assertRaisesRegex(ValueError,"nadpisywac"):
                promote.awansuj(source,base,choice,"6gx",out,copied)


if __name__=="__main__":
    unittest.main()
