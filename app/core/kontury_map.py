# -*- coding: utf-8 -*-
"""Odczyt konturow P z obiektu GEO-MAP bez fikcyjnych polaczen.

P 0 zamyka biezacy lancuch punktow; dodatkowe P 0 bez poprzedzajacych
punktow jest znacznikiem konca, NIE nowym pustym konturem.
Nie interpretujemy otwartych linii jako wypelnionych poligonow.
"""


def fragmenty_z_linii(blok):
    """Zwraca listę {'punkty': [...], 'zamkniety': bool}.

    Nie poprawia automatycznie niezgodnego punktu zamkniecia.
    Nie dopisuje odcinka pierwszego/ostatniego dla otwartej polilinii.
    """
    wynik, biezacy = [], []
    for line in blok:
        if not line.startswith("P "):
            continue
        parts = line.split()
        if len(parts) < 4 or parts[1] not in ("0", "1"):
            continue
        try:
            point = (float(parts[2]), float(parts[3]))
        except ValueError:
            continue
        if parts[1] == "1":
            biezacy.append(point)
        elif biezacy:
            biezacy.append(point)
            if len(biezacy) >= 2:
                wynik.append({
                    "punkty": biezacy,
                    "zamkniety": (len(set(biezacy[:-1])) >= 3
                                  and biezacy[0] == point),
                })
            biezacy = []
        # Samodzielny P 0 po zamknieciu czesci lub calosci obiektu:
        # nie ma nowego segmentu i nie nalezy go laczyc z poprzednim.
    if len(biezacy) >= 2:
        wynik.append({
            "punkty": biezacy,
            "zamkniety": (len(set(biezacy)) >= 3
                          and biezacy[0] == biezacy[-1]),
        })
    return wynik


def kontury_z_linii(blok):
    """Tylko rzeczywiste zamkniete, niedegenerowane kontury."""
    return [f["punkty"] for f in fragmenty_z_linii(blok)
            if f["zamkniety"]]


def model_wydzielenia(blok):
    """Struktura geometrii napisu do oddzielnej walidacji konturowej.

    Regula nieparzystej liczby otaczajacych konturow: rozlaczne czesci
    daja unie, a zagniezdzone pierscienie — dziury. Nie potwierdza
    zgodnosci tego odwzorowania z wizualnym rysunkiem GEO-MAP.
    """
    fragments = fragmenty_z_linii(blok)
    rings = [f["punkty"] for f in fragments if f["zamkniety"]]
    return {
        "kontury": rings,
        "kompletne": bool(rings) and all(f["zamkniety"] for f in fragments),
        "liczba_fragmentow": len(fragments),
    }
