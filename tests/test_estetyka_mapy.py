# -*- coding: utf-8 -*-
"""Regresje: osobny etap estetyki działa bez utraty poprawności."""
import unittest
from unittest.mock import patch

from app.core import estetyka_mapy as aesthetic
from app.core import geometria_ukladu as geo


def label(name, rect, poly, leader=None):
    return {"id":name+":L3","wydzielenie":name,"rodzaj":"opis",
            "prostokat":rect,"poligon":poly,"tekst":"SO30|0.5",
            "wysiegnik":leader}


class AestheticTests(unittest.TestCase):
    def test_moves_external_text_inside_without_new_collision(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        outside=label("a",(130,25,160,45),poly,
                      ((145,45),(50,50)))
        inner=dict(outside,prostokat=(20,20,50,40),wysiegnik=None)
        self.assertFalse(geo.waliduj_uklad([outside]))
        with patch.object(aesthetic.engine,"opcje_wydzielenia",
                          return_value=[[inner]]):
            result,rep=aesthetic.dopracuj(
                [outside],[poly],maks_grup=1,maks_par=0)
        self.assertIsNone(result[0]["wysiegnik"])
        self.assertEqual(rep["przed"]["liczba_wysiegnikow"],1)
        self.assertEqual(rep["po"]["liczba_wysiegnikow"],0)
        self.assertEqual(rep["przyjete_poprawki"],1)
        self.assertFalse(geo.waliduj_uklad(result))
        self.assertIsNot(result[0],outside)
        self.assertEqual(outside["prostokat"],(130,25,160,45))

    def test_refuses_local_improvement_if_another_label_is_hit(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        outside=label("a",(130,25,160,45),poly,
                      ((145,45),(50,50)))
        blocker=label("b",(20,20,50,40),poly)
        proposed=dict(outside,prostokat=blocker["prostokat"],
                      wysiegnik=None)
        with patch.object(aesthetic.engine,"opcje_wydzielenia",
                          return_value=[[proposed]]):
            result,rep=aesthetic.dopracuj(
                [outside,blocker],[poly],maks_grup=1,maks_par=0)
        self.assertEqual(rep["przyjete_poprawki"],0)
        self.assertEqual(result[0]["prostokat"],outside["prostokat"])
        self.assertEqual(result[1]["prostokat"],blocker["prostokat"])

    def test_quality_independent_of_original_displacement(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        outside=label("a",(130,25,160,45),poly,
                      ((145,45),(50,50)))
        closer=dict(outside,prostokat=(110,25,140,45),
                    wysiegnik=((125,45),(50,50)))
        inside=dict(outside,prostokat=(20,20,50,40),wysiegnik=None)
        self.assertLess(aesthetic._quality([inside]),
                        aesthetic._quality([closer]))
        self.assertLess(aesthetic._quality([closer]),
                        aesthetic._quality([outside]))

    def test_requested_label_is_checked_before_other_long_leaders(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        a=label("a",(130,25,160,45),poly,((145,45),(50,50)))
        b=label("b",(170,25,200,45),poly,((185,45),(50,50)))
        reviewed=[]
        def choices(group,*args,**kwargs):
            reviewed.append(group[0]["wydzielenie"])
            return []
        with patch.object(aesthetic.engine,"opcje_wydzielenia",
                          side_effect=choices):
            _,report=aesthetic.dopracuj(
                [a,b],[poly],nazwy={"a":"6j","b":"6k"},
                priorytety=["6k"],maks_grup=1,maks_par=0)
        self.assertEqual(reviewed,["b"])
        self.assertEqual(report["skanowane_grupy"],1)

    def test_approved_layout_is_immutable_even_if_priority_and_neighbor(self):
        pa=[(0,0),(100,0),(100,100),(0,100)]
        pb=[(250,0),(350,0),(350,100),(250,100)]
        a=label("a",(130,25,160,45),pa,((145,45),(50,50)))
        b=label("b",(380,25,410,45),pb,((395,45),(300,50)))
        inner_a=dict(a,prostokat=(20,20,50,40),wysiegnik=None)
        inner_b=dict(b,prostokat=(270,20,300,40),wysiegnik=None)
        calls=[]
        def candidates(group,*args,**kwargs):
            calls.append(group[0]["wydzielenie"])
            return [[inner_a]] if group[0]["wydzielenie"]=="a" else [[inner_b]]
        with patch.object(aesthetic.engine,"opcje_wydzielenia",
                          side_effect=candidates):
            out,report=aesthetic.dopracuj(
                [a,b],[pa,pb],nazwy={"a":"4c","b":"6o"},
                priorytety=["4c","6o"],chronione=["4c"],
                maks_grup=2,maks_par=0)
        self.assertNotIn("a",calls)
        self.assertEqual(out[0]["prostokat"],a["prostokat"])
        self.assertEqual(out[0]["wysiegnik"],a["wysiegnik"])
        self.assertIsNone(out[1]["wysiegnik"])
        self.assertEqual(report["chronione_wydzielenia"],["4c"])

    def test_unresolved_overlap_without_leaders_reaches_joint_solver(self):
        # Regresja rzeczywistego 6s: oba napisy mają wysięgnik=None,
        # ale jeden zasłania drugi. Musimy próbować również sąsiadów.
        poly_a=[(0,0),(100,0),(100,100),(0,100)]
        poly_b=[(100,0),(200,0),(200,100),(100,100)]
        letter={"id":"a:L2","wydzielenie":"a","rodzaj":"litera",
                "tekst":"6s","prostokat":(20,20,40,40),
                "poligon":poly_a,"wysiegnik":None}
        description=dict(letter,id="a:L3",rodzaj="opis",
                         tekst="halizna|0.2")
        other={"id":"b:L2","wydzielenie":"b","rodzaj":"litera",
               "tekst":"6t","prostokat":(130,20,150,40),
               "poligon":poly_b,"wysiegnik":None}
        self.assertTrue(any(p["typ"]=="napis_napis" for p in
                            geo.waliduj_uklad([letter,description,other])))
        def options(group,*args,**kwargs):
            return [list(group)]
        def neighborhood(groups,key,ile=5):
            return [key,"b" if key=="a" else "a"]
        with (patch.object(aesthetic.engine,"opcje_wydzielenia",
                           side_effect=options),
              patch.object(aesthetic.engine,"_sasiedztwo",
                           side_effect=neighborhood),
              patch.object(aesthetic.engine,"_wspolny_plan_dokladny",
                           return_value=(None,{})) as joint):
            out,report=aesthetic.dopracuj(
                [letter,description,other],[poly_a,poly_b],
                nazwy={"a":"6s","b":"6t"},priorytety=["6s"],
                maks_grup=1,maks_par=1)
        self.assertEqual(report["proby_par_sasiadow"],1)
        self.assertEqual(joint.call_count,1)
        self.assertEqual(out[0]["prostokat"],letter["prostokat"])

    def test_zero_budget_leaves_source_exact(self):
        poly=[(0,0),(100,0),(100,100),(0,100)]
        label_a=label("a",(10,10,30,30),poly)
        out,rep=aesthetic.dopracuj([label_a],[poly],
                                  maks_grup=0,maks_par=0)
        self.assertEqual(out,[label_a])
        self.assertEqual(rep["przyjete_poprawki"],0)
        with self.assertRaises(ValueError):
            aesthetic.dopracuj([label_a],[poly],maks_grup=-1)


if __name__=="__main__":
    unittest.main()
