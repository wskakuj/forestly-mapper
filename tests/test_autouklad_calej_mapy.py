"""Automatyczny pełny skan mapy: bezpieczeństwo i raport skuteczności."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.core import autouklad_calej_mapy as auto
from app.core import diag_silnik_grupowy as diag
from app.core import geometria_ukladu as geo
from app.core import opisy_na_mape as onm


def make_labels():
    pa=[(0,0),(40,0),(40,40),(0,40)]
    pb=[(100,0),(140,0),(140,40),(100,40)]
    a={"id":"a:L2","wydzielenie":"a","rodzaj":"litera",
       "tekst":"a","prostokat":(65,10,75,20),
       "poligon":pa,"wysiegnik":None}
    b={"id":"b:L2","wydzielenie":"b","rodzaj":"litera",
       "tekst":"b","prostokat":(110,10,120,20),
       "poligon":pb,"wysiegnik":None}
    return [a,b],[pa,pb]


class FullMapTests(unittest.TestCase):
    def test_second_stage_repairs_neighbor_cluster_automatically(self):
        labels,poly=make_labels()
        self.assertEqual(len(geo.waliduj_uklad(labels)),1)
        calls=[]
        def fake(source,**kwargs):
            selected=kwargs.get("wybrane_wydzielenia")
            calls.append(selected)
            if not selected:
                return source,{"nierozwiazane":geo.waliduj_uklad(source),
                               "rozpatrzone_grupy":2}
            changed=[dict(e) for e in source]
            if selected==frozenset({"a","b"}):
                changed[0]["prostokat"]=(5,10,15,20)
            return changed,{}
        with patch.object(auto.engine,"optymalizuj",side_effect=fake):
            out,report=auto.uloz_cala_mape(
                labels,poly,nazwy={"a":"1a","b":"1b"},
                maks_trudnych=2,rundy_dodatkowe=2)
        self.assertFalse(geo.waliduj_uklad(out))
        self.assertTrue(any(s==frozenset({"a","b"}) for s in calls))
        self.assertEqual(report["tryb"],"cala_mapa")
        self.assertEqual(report["skutecznosc"]["napisy_naprawione"],1)
        self.assertEqual(report["skutecznosc"]["wydzielenia_naprawione"],1)
        self.assertEqual(report["skutecznosc"]["napisy_nowe_z_problemem"],0)
        self.assertFalse(report["analiza_czesciowa"])

    def test_does_not_accept_new_collision_or_original_regression(self):
        labels,poly=make_labels()
        def fake(source,**kwargs):
            if not kwargs.get("wybrane_wydzielenia"):
                return source,{}
            changed=[dict(e) for e in source]
            changed[0]["prostokat"]=(110,10,120,20)
            return changed,{}
        with patch.object(auto.engine,"optymalizuj",side_effect=fake):
            out,report=auto.uloz_cala_mape(
                labels,poly,maks_trudnych=1,rundy_dodatkowe=1)
        self.assertEqual([e["prostokat"] for e in out],
                         [e["prostokat"] for e in labels])
        self.assertEqual(report["skutecznosc"]["napisy_nowe_z_problemem"],0)
        self.assertGreater(report["proby_dopracowania_odrzucone"],0)

    def test_whole_map_report_without_modifying_source_file(self):
        with TemporaryDirectory() as folder:
            src=Path(folder)/"przyklad.MAP"
            lines=[
                ";# Plik danych systemu GEO-MAP",
                ";# EXT 4000 0 0 100 100",
                "*5310 255 24 0",":ID[A]",":A1[a]",":A2[SO45|0.1]",
                "L 2 10 10 0 1 5","L 3 11 11 0 1 5",
                "P 1 0 0","P 1 100 0","P 1 100 100",
                "P 1 0 100","P 0 0 0",""]
            src.write_bytes(onm.tekst_na_maz("\r\n".join(lines)))
            original=src.read_bytes()
            result=diag.diagnozuj(src,skala=4000,cala_mapa=True,
                                  maks_trudnych=0,rundy_dodatkowe=0)
            self.assertTrue(result["tryb_automatyczny_calej_mapy"])
            self.assertEqual(result["liczba_napisow"],2)
            self.assertEqual(result["skutecznosc_calej_mapy"]["napisy_razem"],2)
            self.assertTrue(result["raport_silnika"]["skan_calej_mapy"])
            self.assertEqual(src.read_bytes(),original)

    def test_full_scan_does_not_accept_label_selection(self):
        with self.assertRaisesRegex(ValueError,"--cala-mapa"):
            diag.diagnozuj("nieistniejaca.MAP",cala_mapa=True,
                          etykiety=["4a"])
        with self.assertRaises(ValueError):
            auto.uloz_cala_mape([],[],maks_trudnych=-1)


if __name__=="__main__":
    unittest.main()
