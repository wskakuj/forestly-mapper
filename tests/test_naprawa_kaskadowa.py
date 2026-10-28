# -*- coding: utf-8 -*-
"""Kaskady: więcej niż dwie blokady i bezpieczna atomowa akceptacja."""
import unittest
from unittest.mock import patch
from app.core import naprawa_kaskadowa as cascade
from app.core import silnik_grupowy as engine
from app.core import geometria_ukladu as geo


def fixture():
    poly=[(0,0),(500,0),(500,500),(0,500)]
    def entry(uid,owner,kind,rect):
        return {"id":uid,"wydzielenie":owner,"rodzaj":kind,
                "tekst":uid,"prostokat":rect,"poligon":poly,
                "wysiegnik":None}
    a1=entry("a:L2","a","litera",(15,15,25,25))
    a2=entry("a:L3","a","opis",(15,15,25,25))
    original=[a1,a2]
    choices={
        "a":[[a1,dict(a2,prostokat=(100,100,250,140))]]
    }
    for i,k in enumerate(("b","c","d","e")):
        x=112+i*32
        old=entry(k+":L2",k,"litera",(x,112,x+12,124))
        original.append(old)
        choices[k]=[[dict(old,prostokat=(x,200,x+12,212))]]
    current={e["id"]:dict(e) for e in original}
    grouped={}
    for e in original:
        grouped.setdefault(e["wydzielenie"],[]).append(e)
    return poly,original,current,grouped,choices


class CascadeTests(unittest.TestCase):
    def test_moves_four_blockers_as_one_atomic_repair(self):
        poly,original,current,grouped,choices=fixture()
        initial=geo.waliduj_uklad(list(current.values()))
        self.assertEqual(len(initial),1)
        accepted=[]
        def accept(changed):
            updates={e["id"]:e for e in changed}
            out=[updates.get(e["id"],e) for e in current.values()]
            if geo.waliduj_uklad(out):
                return False
            current.update(updates)
            accepted.append(changed)
            return True
        with patch.object(engine,"opcje_wydzielenia",
                          side_effect=lambda group,*a,**kw:
                          choices[group[0]["wydzielenie"]]):
            report=cascade.napraw_kaskadowo(
                current,grouped,engine.Granice([poly]),[poly],
                targets=["a"],zaakceptuj=accept,
                maks_przesuniec=5,maks_poczatkow=2,maks_stanow=35)
        self.assertEqual(report["przyjete"],1)
        self.assertEqual(report["udane_wydzielenia"][0][
            "liczba_przesunietych_wydzielen"],5)
        self.assertEqual(len(accepted),1)
        self.assertFalse(geo.waliduj_uklad(list(current.values())))
        self.assertEqual(original[1]["prostokat"],(15,15,25,25))

    def test_protected_blocker_refuses_entire_cascade(self):
        poly,original,current,grouped,choices=fixture()
        initial=[dict(e) for e in current.values()]
        with patch.object(engine,"opcje_wydzielenia",
                          side_effect=lambda group,*a,**kw:
                          choices[group[0]["wydzielenie"]]):
            report=cascade.napraw_kaskadowo(
                current,grouped,engine.Granice([poly]),[poly],
                targets=["a"],protected={"d"},
                zaakceptuj=lambda _: self.fail("nie mozna przyjac"),
                maks_przesuniec=5)
        self.assertEqual(report["przyjete"],0)
        self.assertEqual(list(current.values()),initial)
        self.assertGreater(report["przyczyny"]["kolizja_z_chronionym"],0)

    def test_multiple_starts_with_same_blocking_group_are_preserved(self):
        poly,original,current,grouped,choices=fixture()
        alternative=[
            choices["a"][0][0],
            dict(choices["a"][0][1],prostokat=(115,103,245,137))
        ]
        choices["a"].append(alternative)
        rejected=[]
        with patch.object(engine,"opcje_wydzielenia",
                          side_effect=lambda group,*a,**kw:
                          choices[group[0]["wydzielenie"]]):
            report=cascade.napraw_kaskadowo(
                current,grouped,engine.Granice([poly]),[poly],
                targets=["a"],zaakceptuj=lambda plan:(
                    rejected.append(plan) or False),
                maks_przesuniec=5,maks_poczatkow=2,maks_stanow=80)
        self.assertEqual(report["przyjete"],0)
        self.assertEqual(report["cele"]["a"]["rodziny_blokad"],1)
        self.assertEqual(report["cele"]["a"]["przeanalizowane_poczatki"],2)
        self.assertGreaterEqual(len(rejected),1)
        self.assertEqual(current["a:L3"]["prostokat"],(15,15,25,25))

    def test_budget_rejects_large_cluster_without_mutation(self):
        poly,original,current,grouped,choices=fixture()
        with patch.object(engine,"opcje_wydzielenia",
                          side_effect=lambda group,*a,**kw:
                          choices[group[0]["wydzielenie"]]):
            report=cascade.napraw_kaskadowo(
                current,grouped,engine.Granice([poly]),[poly],
                targets=["a"],zaakceptuj=lambda _:self.fail("brak budzetu"),
                maks_przesuniec=4)
        self.assertEqual(report["przyjete"],0)
        self.assertGreater(report["przyczyny"]["potrzeba_wiecej_przesuniec"],0)
        self.assertEqual(current["a:L3"]["prostokat"],(15,15,25,25))


if __name__=="__main__":
    unittest.main()
