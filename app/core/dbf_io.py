# -*- coding: utf-8 -*-
"""
Forestly Mapper — czytanie plików DBF (MIETEK).
==============================================
Wyciągnięte z Forestly (app/core/wydruki.py), żeby zakładka „Opisy na mapę"
miała czytanie DBF bez ciągnięcia całych wydruków.

Zależności: tylko biblioteka standardowa.
"""

import struct
from pathlib import Path


def czytaj_dbf(path):
    """Czyta DBF. Zwraca listę słowników {pole: wartość} (cp852)."""
    data = Path(path).read_bytes()
    nrec = struct.unpack('<I', data[4:8])[0]
    hlen = struct.unpack('<H', data[8:10])[0]
    rlen = struct.unpack('<H', data[10:12])[0]
    fields = []
    off = 32
    while off < len(data) and data[off:off + 1] != b'\x0d':
        raw = data[off:off + 32]
        fields.append((
            raw[0:11].split(b'\x00')[0].decode('ascii', errors='replace'),
            chr(raw[11]), raw[16], raw[17],
        ))
        off += 32
    recs = []
    pos = hlen
    for _ in range(nrec):
        row = data[pos:pos + rlen]
        pos += rlen
        if not row or len(row) < rlen or row[0:1] == b'*':
            continue
        rec = {}
        o = 1
        for fname, ftype, flen, fdec in fields:
            raw = row[o:o + flen].replace(b'\x00', b' ').strip()
            o += flen
            s = raw.decode('cp852', errors='replace')
            if ftype == 'N':
                s2 = s.replace(',', '.').strip()
                try:
                    rec[fname] = float(s2) if ('.' in s2 or fdec) else int(s2)
                except ValueError:
                    rec[fname] = None
            elif ftype == 'L':
                rec[fname] = (s == 'T') if s else None
            else:
                rec[fname] = s
        recs.append(rec)
    return recs


def znajdz_dbf(katalog, prefiks):
    """Znajduje (rekurencyjnie) pierwszy plik DBF o danym prefiksie nazwy."""
    katalog = Path(katalog)
    trafienia, seen = [], set()
    for w in ('%s*.DBF' % prefiks, '%s*.dbf' % prefiks):
        for p in sorted(katalog.rglob(w)):
            if str(p).upper() not in seen:
                seen.add(str(p).upper())
                trafienia.append(p)
    return trafienia[0] if trafienia else None
