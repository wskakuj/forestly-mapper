# -*- coding: utf-8 -*-
"""Porównawczy podgląd SVG oryginału i symulacji GEO-MAP (bez zapisu MAP).

Rysuje dwie plansze w tej samej skali i tym samym obszarze mapy.
To podgląd geometrii i szacowanych prostokątów tekstu, a NIE renderer GEO-MAP.
"""
import argparse
import html
import json
import math
from pathlib import Path

from app.core import diagnostyka_map as dm
from app.core import geometria_ukladu as geo
from app.core import kontury_map as km
from app.core import opisy_na_mape as onm


def _bbox(points):
    return (min(x for x, _ in points), min(y for _, y in points),
            max(x for x, _ in points), max(y for _, y in points))


def _intersects(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _fmt(value):
    return f"{value:.2f}"


def _kontury(lines):
    """Jeden parser dla SVG i silnika; bez pustych P 0 i fałszywych linii."""
    return [(fragment["punkty"], fragment["zamkniety"])
            for fragment in km.fragmenty_z_linii(lines)]


def _obiekty_liniowe(mapa):
    """Wszystkie obiekty z co najmniej dwoma punktami P.

    Parser poligonów odrzuca legalne linie dwupunktowe. W SVG musimy
    narysować również je, aby podgląd nie ukrywał przeszkód.
    """
    lines = mapa["lines"]
    for index, line in enumerate(lines):
        if not line.startswith("*"):
            continue
        end = index + 1
        while end < len(lines) and not lines[end].startswith("*"):
            end += 1
        blok = lines[index + 1:end]
        pts = [p for pts, _ in _kontury(blok) for p in pts]
        if len(pts) >= 2:
            yield {"start": index, "punkty": pts, "linie": blok}


def _apply_changes(elements, changes):
    updated = {e["id"]: dict(e) for e in elements}
    for change in changes:
        ident = change["id"]
        if ident not in updated:
            raise ValueError("Raport zawiera nieznany napis: " + ident)
        original = updated[ident]["prostokat"]
        reported = change["przed"]
        if max(abs(a - b) for a, b in zip(original, reported)) > .01:
            raise ValueError(
                "Pozycje w raporcie roznia sie od wskazanej mapy dla " + ident)
        updated[ident]["prostokat"] = tuple(change["po"])
        updated[ident]["wysiegnik"] = change.get("wysiegnik")
    return updated


def podglad_svg(mapa_path, raport_path, nazwy, *, kontekst=40, szerokosc=1200,
                 wysokosc=650, max_obiektow=500):
    """Zwraca SVG, nie zapisując żadnego pliku.

    Dopuszcza mapę z wieloma konturami wyłącznie w celach oglądowych:
    polilinie są rysowane oddzielnie. Analiza wnętrza wielokątów i
    dokładne czcionki GEO-MAP pozostają poza zakresem tego podglądu.
    """
    if kontekst < 0 or szerokosc < 700 or wysokosc < 350 or max_obiektow < 1:
        raise ValueError("Niepoprawne wymiary, kontekst lub limit obiektow")
    mapa_path, raport_path = Path(mapa_path), Path(raport_path)
    raport = json.loads(raport_path.read_text(encoding="utf-8"))
    if Path(raport.get("plik_wejsciowy", "")).name.casefold() != mapa_path.name.casefold():
        raise ValueError("Raport pochodzi z innego pliku MAP")
    mapa = onm.wczytaj_mape(mapa_path)
    elementy, _ = dm.elementy_z_mapy(
        mapa, raport.get("skala"), raport.get("wysokosc_mm", 2.5))
    if len(elementy) != raport.get("liczba_napisow"):
        raise ValueError("Niezgodna liczba napisow w MAP i raporcie")
    po = _apply_changes(elementy, raport.get("zmiany", []))
    wybrane = {x.strip().casefold() for x in nazwy if x.strip()}
    if not wybrane:
        raise ValueError("Podaj co najmniej jedna nazwe wydzielenia")
    own = [e for e in elementy if e["rodzaj"] == "litera"
           and e["tekst"].strip().casefold() in wybrane]
    znalezione = {e["tekst"].strip().casefold() for e in own}
    if wybrane - znalezione:
        raise ValueError("Nie znaleziono A1: " + ", ".join(sorted(wybrane - znalezione)))
    uuids = {e["wydzielenie"] for e in own}
    targets = [e for e in elementy if e["wydzielenie"] in uuids]
    # Rysunek nie może sugerować, że każdy napis w prawym panelu jest
    # poprawiony. Wylicz status docelowych wydzieleń także po symulacji.
    issues_before = geo.waliduj_uklad(elementy)
    issues_after = geo.waliduj_uklad(list(po.values()))
    labels_by_uuid = {e["wydzielenie"]: e["tekst"] for e in own}
    def unresolved(problems):
        ids = {ident for issue in problems for ident in issue["elementy"]}
        return sorted(labels_by_uuid[uuid] for uuid in uuids
                      if any(e["id"] in ids for e in targets
                             if e["wydzielenie"] == uuid))
    wrong_before, wrong_after = unresolved(issues_before), unresolved(issues_after)

    focus = []
    for e in targets:
        # Poligon jedno- lub wielokonturowy; nie iteruj po kluczach
        # slownika {"kontury": ...} jak po punktach (blad SVG dla 4a/4c).
        focus.extend(p for ring in
                     (e["poligon"]["kontury"] if isinstance(e["poligon"], dict)
                      else [e["poligon"]])
                     for p in ring)
        for rect in (e["prostokat"], po[e["id"]]["prostokat"]):
            focus.extend(((rect[0], rect[1]), (rect[2], rect[3])))
        for leader in (e.get("wysiegnik"), po[e["id"]].get("wysiegnik")):
            if leader:
                focus.extend(leader)
    x0, y0, x1, y1 = _bbox(focus)
    pad = max(kontekst, (x1 - x0) * .12, (y1 - y0) * .12)
    world = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    obiekty = list(_obiekty_liniowe(mapa))
    visible = [o for o in obiekty if _intersects(_bbox(o["punkty"]), world)]
    skipped = max(0, len(visible) - max_obiektow)
    visible = visible[:max_obiektow]
    panel_w = (szerokosc - 52) / 2
    panel_h = wysokosc - 163
    lefts = [18, panel_w + 34]
    top = 112
    ratio = min((panel_w - 22) / (world[2] - world[0]),
                (panel_h - 22) / (world[3] - world[1]))
    x_margin = (panel_w - (world[2] - world[0]) * ratio) / 2
    y_margin = (panel_h - (world[3] - world[1]) * ratio) / 2

    def project(point, panel):
        return (lefts[panel] + x_margin + (point[0] - world[0]) * ratio,
                top + y_margin + (world[3] - point[1]) * ratio)

    def lines_for(panel):
        out = []
        # Geometria jest zapisywana w obiektach GEO-MAP; P 0 wyznacza
        # oddzielne kontury. Nie tworzymy przekątnej między nimi.
        for obj in visible:
            selected = any(
                ("ID[" + uuid + "]") in "\n".join(obj["linie"]) for uuid in uuids)
            stroke = "#64748b" if selected else "#cbd5e1"
            thickness = 1.8 if selected else .85
            for pts, closed in _kontury(obj["linie"]):
                part = " ".join(("M" if i == 0 else "L") +
                                _fmt(project(point, panel)[0]) + "," +
                                _fmt(project(point, panel)[1])
                                for i, point in enumerate(pts))
                if closed:
                    part += " Z"
                out.append(
                    f'<path d="{part}" fill="none" stroke="{stroke}" '
                    f'stroke-width="{thickness}" />')
        entries = elementy if panel == 0 else [po[e["id"]] for e in elementy]
        for e in entries:
            # Draw neighboring labels too, so their conflicts remain visible.
            rect = e["prostokat"]
            if not _intersects(rect, world):
                continue
            chosen = e["wydzielenie"] in uuids
            px, py = project((rect[0], rect[3]), panel)
            rw, rh = (rect[2] - rect[0]) * ratio, (rect[3] - rect[1]) * ratio
            stroke = ("#2563eb" if e["rodzaj"] == "litera" else "#ea580c") if chosen else "#9ca3af"
            fill = ("#dbeafe" if e["rodzaj"] == "litera" else "#ffedd5") if chosen else "#f3f4f6"
            opacity = ".60" if chosen else ".20"
            out.append(f'<rect x="{_fmt(px)}" y="{_fmt(py)}" '
                       f'width="{_fmt(rw)}" height="{_fmt(rh)}" '
                       f'fill="{fill}" fill-opacity="{opacity}" '
                       f'stroke="{stroke}" stroke-width="{2 if chosen else .7}"/>')
            if chosen:
                # GEO-MAP A2 zawiera linie oddzielone '|'. Tekst w
                # jednym wierszu nachodził na obrysy i był nieczytelny.
                # SVG jest poglądowe, lecz każda linia musi być czytelna
                # we własnym prostokącie (bez udawania fontów GEO-MAP).
                full = e.get("tekst", "")
                lines = full.split("|") if e["rodzaj"] == "opis" else [full]
                cx, cy = project(((rect[0] + rect[2]) / 2,
                                  (rect[1] + rect[3]) / 2), panel)
                font = (13.0 if e["rodzaj"] == "litera" else
                        min(13.0, max(9.0, rh / (len(lines) + .65) * .87)))
                advance = font * 1.28
                baseline = cy - (len(lines) - 1) * advance / 2 + font * .35
                spans = "".join(
                    f'<tspan x="{_fmt(cx)}" '
                    f'y="{_fmt(baseline + i * advance)}">'
                    f'{html.escape(line)}</tspan>'
                    for i, line in enumerate(lines))
                out.append(f'<text x="{_fmt(cx)}" '
                           f'data-full-text="{html.escape(full, quote=True)}" '
                           f'fill="#111827" text-anchor="middle" '
                           f'font-size="{_fmt(font)}" '
                           f'font-weight="700" '
                           f'font-family="Arial,sans-serif" paint-order="stroke" '
                           f'stroke="#ffffff" stroke-width=".65">{spans}</text>')
            leader = e.get("wysiegnik")
            if leader:
                (ax, ay), (bx, by) = project(leader[0], panel), project(leader[1], panel)
                out.append(f'<path d="M{_fmt(ax)},{_fmt(ay)} L{_fmt(bx)},{_fmt(by)}" '
                           f'fill="none" stroke="{stroke if chosen else "#9ca3af"}" '
                           f'stroke-width="{2.6 if chosen else 1}" />')
                if chosen:
                    out.append(f'<circle cx="{_fmt(bx)}" cy="{_fmt(by)}" '
                               f'r="3" fill="{stroke}"/>')
        return "".join(out)

    title = html.escape(" / ".join(sorted(wybrane)))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{szerokosc}" '
        f'height="{wysokosc}" viewBox="0 0 {szerokosc} {wysokosc}">',
        f'<title>Forestly Mapper: przed i po — {title}</title>',
        f'<rect width="{szerokosc}" height="{wysokosc}" fill="#ffffff"/>',
        f'<text x="18" y="32" font-size="20" font-weight="bold" '
        f'font-family="Arial,sans-serif" fill="#111827">'
        f'Forestly Mapper — {title}</text>',
        '<text x="18" y="53" font-size="12" fill="#4b5563" '
        'font-family="Arial,sans-serif">'
        'Szacunkowe prostokaty tekstu, prawdziwe odcinki MAP; podglad NIE jest wydrukiem GEO-MAP'
        '</text>',
    ]
    for panel, label in enumerate(("PRZED: zrodlo MAP",
                                   "PO: propozycja algorytmu")):
        x = lefts[panel]
        broken = wrong_before if panel == 0 else wrong_after
        status = ("NIEROZWIAZANE: " + ", ".join(broken)) if broken else "Bez wykrytych kolizji w wybranych wydzieleniach"
        color = "#b91c1c" if broken else "#166534"
        parts += [
            f'<text x="{_fmt(x + 5)}" y="101" fill="{color}" '
            f'font-size="13" font-weight="700" '
            f'font-family="Arial,sans-serif">{html.escape(status)}</text>',
            f'<rect x="{_fmt(x)}" y="{top}" width="{_fmt(panel_w)}" '
            f'height="{_fmt(panel_h)}" fill="#f8fafc" stroke="#d1d5db"/>',
            f'<text x="{_fmt(x + 5)}" y="79" font-size="15" '
            f'font-family="Arial,sans-serif" font-weight="bold">{label}</text>',
            f'<defs><clipPath id="clip{panel}"><rect x="{_fmt(x)}" y="{top}" '
            f'width="{_fmt(panel_w)}" height="{_fmt(panel_h)}"/></clipPath></defs>',
            f'<g clip-path="url(#clip{panel})">{lines_for(panel)}</g>',
        ]
    footer = (f'Obiekty w podgladzie: {len(visible)}'
              + (f' (pominieto {skipped} przez limit)' if skipped else '')
              + '; nie wolno traktowac szkicu jako walidacji wielokonturowych wydzielen.')
    parts.append(f'<text x="18" y="{wysokosc - 25}" font-size="12" '
                 f'font-family="Arial,sans-serif" fill="#4b5563">'
                 f'{html.escape(footer)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def main(argv=None):
    p = argparse.ArgumentParser(description="Tylko SVG: podglad porownawczy przed i po")
    p.add_argument("mapa", help="Wejsciowa MAP (tylko odczyt)")
    p.add_argument("raport", help="JSON z diagnozy (tylko odczyt)")
    p.add_argument("--etykiety", nargs="+", required=True, help="A1 np. 3h")
    p.add_argument("--svg", required=True, help="Nowy plik .svg, bez nadpisywania")
    p.add_argument("--kontekst", type=float, default=40.0)
    args = p.parse_args(argv)
    destination = Path(args.svg)
    if destination.suffix.lower() != ".svg":
        p.error("Podaj docelowy plik z rozszerzeniem .svg")
    if destination.exists():
        p.error("Plik SVG juz istnieje; wybierz nowa nazwe (bez nadpisywania)")
    if destination.resolve() in (Path(args.mapa).resolve(), Path(args.raport).resolve()):
        p.error("Nie wolno nadpisac MAP ani JSON")
    try:
        svg = podglad_svg(args.mapa, args.raport, args.etykiety,
                          kontekst=args.kontekst)
    except (ValueError, OSError, KeyError) as exc:
        p.error(str(exc))
    # Exclusive create: także wyścig z innym procesem nie nadpisze istniejącego.
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(svg)
    print("Podglad zapisany:", destination)
    print("MAP oraz JSON pozostaly bez zmian. Otworz SVG w przegladarce.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
