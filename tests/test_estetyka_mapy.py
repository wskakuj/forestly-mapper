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
