# -*- coding: utf-8 -*-
"""Wymiar tekstu kontra geometria: bez zmiany oryginalnego MAP."""
import unittest
from app.core import diag_dopasowanie_wnetrza as diag


class FitDiagnosticsTests(unittest.TestCase):
    def test_real_6s_ring_shows_model_envelope_is_limiting(self):
        # Oryginalny 8-wierzchołkowy obrys 6s w pliku BYSŁAW
        coords=[
            (627143.879,436431.030),(627165.014,436464.932),
            (627147.668,436485.635),(627123.584,436525.327),
            (627092.416,436515.120),(627062.260,436493.040),
            (627089.276,436481.683),(627123.208,436441.116)]
        poly=[(x-627000,y-436400) for x,y in coords]
        desc={"id":"6s:L3","rodzaj":"opis","tekst":"halizna|0.2477",
              "wydzielenie":"6s","poligon":poly,
              "prostokat":(50,35,77,93),"wysiegnik":None}
        lit={"id":"6s:L2","rodzaj":"litera","tekst":"6s",
             "wydzielenie":"6s","poligon":poly,
             "prostokat":(50,35,66.2,54.92),"wysiegnik":None}
        nominal=diag._centra_wlasnego_poligonu(desc,1.0,krok=2)
        compact=diag._centra_wlasnego_poligonu(desc,0.8,krok=2)
        self.assertEqual(nominal,[])
        self.assertGreater(len(compact),0)
        results=diag.raport_wydzielenia([lit,desc],"6s",
                                        wspolczynniki=(1,0.8),krok=2)
        self.assertEqual(results["proby"][0]["pozycje_opisu_wewnatrz"],0)
        self.assertGreater(results["proby"][1]["pary_niekolidujace_w_poligonie"],0)

    def test_missing_or_ambiguous_label_is_rejected(self):
        with self.assertRaises(ValueError):
            diag.raport_wydzielenia([],"6s")


if __name__=="__main__":
    unittest.main()
