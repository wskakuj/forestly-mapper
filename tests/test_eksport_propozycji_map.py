"""Kopie GEO-MAP: zapis tylko zmienionych L2/L3, roundtrip i bezpieczeństwo."""
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.core import diagnostyka_map as dm
from app.core import eksport_propozycji_map as exp
from app.core import opisy_na_mape as onm


class ExportTests(unittest.TestCase):
    def sample(self,folder):
        source=Path(folder)/"oryginal.MAP"
        lines=[
            ";# Plik danych systemu GEO-MAP ver=[ 8.00]  "
            "N=[           0] CHK=[00000000000000000000000000000000]",
            ";# EXT 4000 0 0 200 200",
            "*5310 255 24 0",":ID[ID-A]",":A1[4a]",":A2[SO45|0.2]",
            "L 2 0.000 0.000 0.0000000 1.0000000 5",
            "L 3 0.000 0.000 0.0000000 1.0000000 5",
            "P 1 0 0","P 1 100 0","P 1 100 100",
            "P 1 0 100","P 0 0 0",""
        ]
        raw=onm.przelicz_naglowek(lines)
        source.write_bytes(raw)
        orig=dm.elementy_z_mapy(onm.wczytaj_mape(source),4000)[0]
        self.assertEqual(len(orig),2)
        return source,orig

    def report(self,source,orig,leader=True):
        label=next(e for e in orig if e["rodzaj"]=="litera")
        old=label["prostokat"]
        rect=tuple(x+10 if i%2==0 else x+25
                   for i,x in enumerate(old))
        start=((rect[0]+rect[2])/2,rect[1])
        target=(40.0,40.0)
        return {"tryb_automatyczny_calej_mapy":True,
                "analiza_czesciowa":False,
                "plik_wejsciowy":str(source),
                "sha256_zrodla":hashlib.sha256(source.read_bytes()).hexdigest(),
                "skala":4000,"wysokosc_mm":2.5,
                "zmiany":[{
                    "id":label["id"],"tekst":label["tekst"],
                    "rodzaj":label["rodzaj"],
                    "przed":list(old),"po":list(rect),
                    "wysiegnik":[list(start),list(target)] if leader else None,
                }]}

    def test_copy_with_leader_roundtrips_and_preserves_input(self):
        with TemporaryDirectory() as d:
            src,orig=self.sample(d)
            raw=src.read_bytes()
            dest=Path(d)/"kopia_test.MAP"
            rep=self.report(src,orig)
            result=exp.eksportuj_kopie(src,rep,dest)
            self.assertEqual(result["zapisane_napisy"],1)
            self.assertEqual(result["napisy_po_odczycie"],2)
            self.assertTrue(dest.exists())
            self.assertEqual(src.read_bytes(),raw)
            self.assertNotEqual(dest.read_bytes(),raw)
            text=onm.maz_na_tekst(dest.read_bytes())
            self.assertIn(" 69 ",text)
            self.assertIn("CHK=[",text.split("\r\n")[0])
            copy_labels=dm.elementy_z_mapy(onm.wczytaj_mape(dest),4000)[0]
            self.assertEqual(len(copy_labels),2)
            self.assertEqual(len([e for e in copy_labels if e["wysiegnik"]]),1)
            with self.assertRaises(FileExistsError):
                exp.eksportuj_kopie(src,rep,dest)
            self.assertEqual(src.read_bytes(),raw)

    def test_copy_without_leader_removes_obsolete_tail(self):
        with TemporaryDirectory() as d:
            src,orig=self.sample(d)
            rep=self.report(src,orig,leader=False)
            dst=Path(d)/"kopia.MAP"
            exp.eksportuj_kopie(src,rep,dst)
            label=next(e for e in dm.elementy_z_mapy(
                onm.wczytaj_mape(dst),4000)[0] if e["rodzaj"]=="litera")
            self.assertIsNone(label["wysiegnik"])
            self.assertTrue(any(line.startswith("L 2 ")
                                and line.split()[-1]=="5"
                                for line in onm.maz_na_tekst(
                                    dst.read_bytes()).split("\r\n")))

    def test_wrong_report_and_original_paths_refused(self):
        with TemporaryDirectory() as d:
            src,orig=self.sample(d)
            before=src.read_bytes()
            rep=self.report(src,orig)
            with self.assertRaises(ValueError):
                exp.eksportuj_kopie(src,rep,src)
            rep["plik_wejsciowy"]="inna.MAP"
            with self.assertRaisesRegex(ValueError,"innego"):
                exp.eksportuj_kopie(src,rep,Path(d)/"kopia.MAP")
            self.assertEqual(src.read_bytes(),before)
            self.assertFalse((Path(d)/"kopia.MAP").exists())

    def test_changed_input_hash_refuses_export(self):
        with TemporaryDirectory() as d:
            src,orig=self.sample(d)
            report=self.report(src,orig)
            raw=src.read_bytes()
            src.write_bytes(raw+b"\r\n; nieoczekiwana zmiana\r\n")
            dst=Path(d)/"nieaktualna.MAP"
            with self.assertRaisesRegex(ValueError,"zmienila sie"):
                exp.eksportuj_kopie(src,report,dst)
            self.assertFalse(dst.exists())
            self.assertEqual(src.read_bytes(),raw+b"\r\n; nieoczekiwana zmiana\r\n")

    def test_malformed_leader_is_not_written(self):
        with TemporaryDirectory() as d:
            src,orig=self.sample(d)
            rep=self.report(src,orig)
            rep["zmiany"][0]["wysiegnik"][0][0]+=20
            dest=Path(d)/"bledna.MAP"
            with self.assertRaisesRegex(ValueError,"krawedzi"):
                exp.eksportuj_kopie(src,rep,dest)
            self.assertFalse(dest.exists())


if __name__=="__main__":
    unittest.main()
