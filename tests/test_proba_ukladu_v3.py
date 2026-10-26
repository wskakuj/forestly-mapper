"""Regresja v3: opis może wyjść poza polygon z poprawnym prostym wysięgnikiem."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core import geometria_ukladu as geo
from app.core import proba_ukladu as v1
from app.core import proba_ukladu_v3 as v3


class ProbaUkladuV3Test(unittest.TestCase):
    def element(self, ident, rodzaj, box, poly):
        return {'id':ident,'wydzielenie':'a','uuid':'a',
                'rodzaj':rodzaj,'tekst':'test',
                'prostokat':box,'poligon':poly,'wysiegnik':None}

    def test_opis_poza_litera_w_srodku_i_poprawny_wysiegnik(self):
        poly=[(0,0),(60,0),(60,70),(0,70)]
        letter=self.element('a:L2','litera',(22,24,38,44),poly)
        desc=self.element('a:L3','opis',(17,20,44,69),poly)
        index=v1.IndeksNapisow([letter,desc])
        moves,leaders,report=v3.popraw_pary([letter,desc],index)
        self.assertIn('a:L3',moves)
        self.assertIn('a:L3',leaders)
        self.assertEqual(report['leads_added'],1)
        self.assertEqual(index.boxy['a:L2'],letter['prostokat'])
        self.assertFalse(geo.prostokaty_koliduja(
            index.boxy['a:L2'],index.boxy['a:L3']))
        anchor=leaders['a:L3'][1]
        self.assertTrue(geo.punkt_w_poligonie(anchor,poly,granica=False))

    def test_nie_nadpisuje_oryginalu(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'mapa.MAP'
            path.write_bytes(b'test bez zmian')
            with self.assertRaises(ValueError):
                v3.zapisz_kopie({},[],{},{},path,path)
            self.assertEqual(path.read_bytes(),b'test bez zmian')


if __name__=='__main__':
    unittest.main()
