# -*- coding: utf-8 -*-
"""Ręczne wzorce: kontrola UUID, obrysu, fontu i niechcianych zmian."""
import unittest
from unittest.mock import patch

from app.core import wzorce_reczne as wzorce


def entity(uuid,kind,name,rect,poly=None,leader=None):
    return {
        "id":uuid+(":L2" if kind=="litera" else ":L3"),
        "wydzielenie":uuid,"rodzaj":kind,"tekst":name,
        "prostokat":rect,"poligon":poly or [(0,0),(100,0),(100,100),(0,100)],
        "wysiegnik":leader
    }


class ManualExemplarsTests(unittest.TestCase):
    def setUp(self):
        self.base=[
            entity("a","litera","6s",(20,20,30,35)),
            entity("a","opis","halizna|0.2477",(10,10,45,55)),
            entity("b","litera","6r",(150,20,160,35))
        ]
        self.names={"a":"6s","b":"6r"}
        self.manual=[
            dict(self.base[0],prostokat=(40,70,50,85)),
            dict(self.base[1],prostokat=(15,37,50,82)),
            dict(self.base[2],prostokat=(150.0004,20.0004,160.0004,35.0004))
        ]

    def load(self,reference=None):
        example=reference if reference is not None else self.manual
        with (patch.object(wzorce.onm,"wczytaj_mape",
                           return_value={"lines":[]}),
              patch.object(wzorce.dm,"elementy_z_mapy",
                           return_value=(example,[]))):
            return wzorce.wczytaj_wzorce(
                "private_example.MAP",self.base,self.names,
                4000,2.5,("6s",))

    def test_only_selected_6s_positions_are_imported(self):
        plans=self.load()
        self.assertEqual(list(plans),["a"])
        self.assertEqual(len(plans["a"]),2)
        self.assertEqual(plans["a"][0]["prostokat"],(40,70,50,85))
        self.assertEqual(self.base[0]["prostokat"],(20,20,30,35))

    def test_reject_unrequested_changed_6r(self):
        wrong=[dict(e) for e in self.manual]
        wrong[2]["prostokat"]=(180,20,190,35)
        with self.assertRaisesRegex(ValueError,"inne wydzielenia"):
            self.load(wrong)

    def test_reject_geometry_change_even_with_matching_uuid(self):
        wrong=[dict(e) for e in self.manual]
        wrong[0]["poligon"]=[(0,0),(200,0),(200,100),(0,100)]
        with self.assertRaisesRegex(ValueError,"obrys"):
            self.load(wrong)

    def test_reject_any_changed_font_dimensions(self):
        wrong=[dict(e) for e in self.manual]
        wrong[1]["prostokat"]=(15,37,35,82)
        with self.assertRaisesRegex(ValueError,"fontu"):
            self.load(wrong)

    def test_reject_other_labels_missing_or_renamed(self):
        with self.assertRaisesRegex(ValueError,"UUID"):
            self.load(self.manual[:2])


if __name__=="__main__":
    unittest.main()
