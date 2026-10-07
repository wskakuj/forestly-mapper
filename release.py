#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forestly Mapper — pomocnik wydawania wersji (release)
=====================================================
Jednym poleceniem zapisuje zmienione pliki do repo GitHub i wypuszcza
nowy release — Actions zbudują Forestly_Mapper.exe, a changelog trafi
do opisu Release.

Użycie (w folderze repo forestly-mapper):
    python release.py        → kreator krok po kroku
    python release.py -k     → bez pytania o potwierdzenie (konto gotowe)

Numer nowej wersji podpowiadany jest z app/config.py. Gdyby taki tag już
istniał (lokalnie albo na GitHubie), podpowiadany jest kolejny wolny numer.

Wymagania: git (zalogowany — klon robiony przez HTTPS z zapamiętanym hasłem).
"""

import re
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parent
CONFIG = REPO / "app" / "config.py"
NOTES = REPO / "RELEASE_NOTES.md"


def _z_configu(nazwa, domyslna):
    try:
        m = re.search(r'%s = "([^"]+)"' % nazwa,
                      CONFIG.read_text(encoding="utf-8"))
        return m.group(1) if m else domyslna
    except Exception:                                        # noqa: BLE001
        return domyslna


GITHUB_USER = _z_configu("GITHUB_USER", "wskakuj")
GITHUB_REPO = _z_configu("GITHUB_REPO", "forestly-mapper")
GITHUB_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}"


def git(*args, check=True, timeout=20, prompt=False, capture=True):
    """Uruchamia git w katalogu repo, zwraca stdout (lub exits przy błędzie).

    timeout  — maksymalny czas (s) na jedno polecenie. Bez tego polecenia
               sieciowe (ls-remote / push) potrafiły „wisieć" w nieskończoność,
               gdy git czekał na login/hasło albo sieć nie odpowiadała.
    prompt   — gdy False, wyłączamy interaktywne pytanie git o dane logowania
               (GIT_TERMINAL_PROMPT=0) — zamiast wisieć, polecenie od razu
               zwróci błąd (używane przy odczycie tagów).
    capture  — gdy False, wyjście git idzie wprost na ekran (widać ewentualne
               pytanie o hasło i postęp wysyłki) — używane przy push.
    """
    env = dict(os.environ)
    if not prompt:
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
    try:
        r = subprocess.run(["git", "-C", str(REPO), *args],
                           capture_output=capture, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        print(f"\n✗ git {' '.join(args)} — przekroczono czas ({timeout} s).")
        print("  Najczęściej: git czeka na login/hasło albo nie ma połączenia z GitHubem.")
        print("  Nic nie wysłano. Sprawdź internet i dane logowania, potem uruchom ponownie.")
        sys.exit(1)
    out = (r.stdout or "").strip() if capture else ""
    if check and r.returncode != 0:
        print("\n✗ BŁĄD git " + " ".join(args))
        if capture:
            if out:
                print(out)
            if r.stderr and r.stderr.strip():
                print(r.stderr.strip())
        else:
            print("   (szczegóły błędu powyżej)")
        print("\nNic nie wysłano — popraw problem i uruchom release.py ponownie.")
        sys.exit(1)
    return out


def read_current_version():
    m = re.search(r'CURRENT_VERSION = "([^"]+)"',
                  CONFIG.read_text(encoding="utf-8"))
    if not m:
        print("✗ Nie znaleziono CURRENT_VERSION w app/config.py")
        sys.exit(1)
    return m.group(1)


def set_current_version(ver):
    s = CONFIG.read_text(encoding="utf-8")
    s2 = re.sub(r'CURRENT_VERSION = "[^"]+"',
                f'CURRENT_VERSION = "{ver}"', s, count=1)
    CONFIG.write_text(s2, encoding="utf-8")


def _vt(v):
    """Wersja jako krotka liczb (do porównań)."""
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", v or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def remote_tag_list():
    """Lista tagów vX.Y.Z z GitHuba (origin) — zapytanie do serwera.

    Działa też bez lokalnego 'git fetch' i bez zalogowania (publiczne repo),
    a gdy nie ma sieci — zwraca pustą listę (release.py nie zgłasza błędu).
    """
    out = git("ls-remote", "--tags", "origin", check=False, timeout=15,
              prompt=False)
    tags = []
    for line in out.splitlines():
        m = re.search(r"refs/tags/(v\d+\.\d+\.\d+)$", line.strip())
        if m:
            tags.append(m.group(1))
    return tags


def latest_remote_tag():
    """Najwyższy tag na GitHubie (albo None, gdy nie da się odczytać)."""
    tags = remote_tag_list()
    return max(tags, key=_vt) if tags else None


def next_patch(v):
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", v)
    if not m:
        return None
    a, b, c = (int(x) for x in m.groups())
    return f"v{a}.{b}.{c + 1}"


def sanitize_notes(text):
    """Usuwa z changelogu encje HTML i gwiazdki markdownu, które w opisie
    Release na GitHubie wyglądałyby jak krzaczki."""
    A = "&"
    pairs = (
        (A + "amp;#x20;", " "),
        (A + "amp;nbsp;", " "),
        (A + "#x20;", " "),
        (A + "nbsp;", " "),
        (A + "#160;", " "),
        (A + "#xa0;", " "),
        (A + "quot;", '"'),
        (A + "#39;", "'"),
        (A + "lt;", "<"),
        (A + "gt;", ">"),
        (A + "amp;", A),
    )
    for _pass in range(2):   # dwa przebiegi — na wypadek podwójnych encji
        for old, new in pairs:
            text = text.replace(old, new)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    # wypunktowanie gwiazdką → myślnik (poprawne kropki na GitHubie)
    text = re.sub(r"(?m)^\s*\*\s+", "- ", text)
    # ukośniki ucieczki markdown (\-, \[OK\]) — zostaje sam znak
    text = re.sub(r"\\([-*_\[\]()#<>~|`])", r"\1", text)
    return text


def edit_changelog(ver):
    """Changelog: notepad na Windows, wpisywanie w konsoli gdzie indziej."""
    header = f"# Co nowego w {ver}\n\n"
    if sys.platform == "win32":
        NOTES.write_text(header + "- \n", encoding="utf-8")
        print("\nOtwieram Notatnik — napisz changelog, ZAPISZ i zamknij okno.")
        try:
            subprocess.run(["notepad.exe", str(NOTES)], check=False)
        except FileNotFoundError:
            pass
        raw = NOTES.read_text(encoding="utf-8")
        clean = sanitize_notes(raw)
        if clean != raw:
            NOTES.write_text(clean, encoding="utf-8")
            print("   (wyczyściłem znaki specjalne, które psułyby opis Release)")
        body = clean.strip()
        if body in (header.strip(), header.strip() + "-"):
            print("   (changelog pusty — użyję tylko listy commitów z GitHuba)")
            return
        return
    # wariant konsolowy (test / inne systemy)
    print("\nWpisuj linie changelogu; pusta linia kończy:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    NOTES.write_text(sanitize_notes(header + "\n".join(lines)) + "\n",
                     encoding="utf-8")


def main():
    print("=" * 62)
    print("  FORESTLY MAPPER — wydawanie nowej wersji")
    print("=" * 62)
    print(f"  Repo: {GITHUB_URL}")

    # 0) czy to w ogóle repo gita? (świeże repo może nie mieć jeszcze commita)
    jest_repo = bool(git("rev-parse", "--is-inside-work-tree", check=False))
    if not jest_repo:
        print("\n✗ To nie jest repozytorium git. Uruchom najpierw utworz_repo.py")
        sys.exit(1)
    ma_head = bool(git("rev-parse", "--verify", "HEAD", check=False))

    # 1) co się zmieniło? (pliki + ewentualne commity czekające na wysłanie)
    status = git("status", "--short")
    unpushed = git("log", "--branches", "--not", "--remotes", "--oneline",
                   check=False) if ma_head else ""
    if ma_head and not status and not unpushed:
        print("\nBrak zmian — drzewo robocze czyste. Nie ma czego wydawać.")
        sys.exit(0)
    if status:
        print(f"\nZmienione / nowe pliki ({len(status.splitlines())}):")
        for line in status.splitlines():
            print("   " + line)
    if unpushed:
        print("\nUwaga: są już commity niewysłane na GitHub —")
        print("wydanie dokończy ich wysyłkę.")

    # 2) nowa wersja — domyślnie TA z app/config.py; gdyby tag był zajęty,
    #    podpowiadamy kolejny wolny numer
    cur = read_current_version()
    print("Sprawdzam tagi na GitHubie… (gdy brak sieci — pomijam)")
    remote = latest_remote_tag()
    remote_tags = remote_tag_list()
    if remote:
        print(f"Ostatnia wersja na GitHub  : {remote}")
    else:
        print("(nie udało się odczytać tagów z GitHub — bazuję na config.py)")
    print(f"Aktualna wersja (app/config.py): {cur}")

    def _zajeta(v):
        return bool(git("tag", "-l", v)) or v in remote_tags

    prop = cur
    while _zajeta(prop):
        prop = next_patch(prop) or "v0.0.1"
    try:
        ans = input(f"Nowa wersja [{prop}]: ").strip() or prop
    except EOFError:
        ans = prop
    if not re.match(r"^v\d+\.\d+\.\d+$", ans):
        print("✗ Wersja musi być w formacie vX.Y.Z (np. v1.0.1)")
        sys.exit(1)
    # tag może już istnieć lokalnie LUB na GitHub (lokalne tagi bywają stare)
    remote_tags = remote_tag_list()
    if git("tag", "-l", ans) or ans in remote_tags:
        print(f"✗ Tag {ans} już istnieje (lokalnie lub na GitHub) — wybierz inny numer.")
        sys.exit(1)

    # 3) opis commita
    try:
        msg = input(f"Krótki opis zmian [Wersja {ans}]: ").strip() or f"Wersja {ans}"
    except EOFError:
        msg = f"Wersja {ans}"

    # 4) changelog
    edit_changelog(ans)

    # 5) potwierdzenie
    print("\n" + "-" * 62)
    print(f"Wersja : {ans}   (obecnie: {cur})")
    print(f"Commit : {msg}")
    if NOTES.exists():
        preview = [l for l in NOTES.read_text(encoding="utf-8").splitlines() if l.strip()]
        print("Release:")
        for l in preview[:5]:
            print("   " + l)
        if len(preview) > 5:
            print(f"   … (+{len(preview) - 5} linii)")
    print("-" * 62)
    if "-k" not in sys.argv:
        try:
            ok = input("\nWypuścić wersję? [T/n]: ").strip().lower()
        except EOFError:
            ok = ""
        if ok in ("n", "nie", "no"):
            print("Anulowano — nic nie wysłano.")
            sys.exit(0)

    # 6) wykonanie
    print("\nUstawiam wersję w app/config.py…")
    set_current_version(ans)
    print("Zapisuję pliki (git add + commit)…")
    git("add", "-A")
    staged = git("diff", "--cached", "--name-only")
    if staged:
        git("commit", "-m", msg)
    print("Wysyłam zmiany na GitHub (push)…")
    git("push", "-u", "origin", "HEAD", prompt=True, capture=False, timeout=180)
    print(f"Taguję {ans} i wysyłam tag — Actions budują EXE…")
    git("tag", ans)
    git("push", "origin", ans, prompt=True, capture=False, timeout=180)

    print("\n✓ WYPUŚCZONO WERSJĘ " + ans)
    print(f"  Postęp budowy : {GITHUB_URL}/actions")
    print(f"  Release (po paru minutach): {GITHUB_URL}/releases")
    if "--open" in sys.argv:
        webbrowser.open(f"{GITHUB_URL}/actions")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPrzerwano — nic nie wysłano.")
