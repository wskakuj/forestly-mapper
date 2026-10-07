#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forestly Mapper — tworzenie repozytorium na GitHubie (jednorazowo)
=================================================================
Zakłada repo na Twoim koncie GitHub i wrzuca do niego cały projekt.
Potem wystarczy już tylko release.py (albo dwuklik na release.bat),
który wypuszcza nowe wersje i każe Actions zbudować Forestly_Mapper.exe.

Użycie (w folderze tego projektu):
    python utworz_repo.py

Dwa sposoby logowania — skrypt sam wybierze dostępny:
  1. GitHub CLI (gh) — jeśli masz zainstalowane i zalogowane: najprościej.
       Instalacja: https://cli.github.com  → potem:  gh auth login
  2. Token (PAT) — jeśli nie masz gh. Skrypt poprosi o token.
       Utwórz token: https://github.com/settings/tokens
       (klasyczny token z zaznaczonym zakresem „repo").

Skrypt NIGDZIE nie zapisuje tokenu — używa go tylko w tej sesji.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
CONFIG = REPO / "app" / "config.py"
TAG_PIERWSZY = "v1.0.0"
OPIS_REPO = "Forestly Mapper — układanie opisów na mapach GEO-MAP"


def _z_configu(nazwa, domyslna):
    try:
        m = re.search(r'%s = "([^"]+)"' % nazwa,
                      CONFIG.read_text(encoding="utf-8"))
        return m.group(1) if m else domyslna
    except Exception:                                        # noqa: BLE001
        return domyslna


def git(*args, check=True, prompt=False, timeout=120, capture=True):
    env = dict(os.environ)
    if not prompt:
        env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        r = subprocess.run(["git", "-C", str(REPO), *args], text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env=env, capture_output=capture)
    except subprocess.TimeoutExpired:
        print("\n✗ git %s — przekroczono czas (%s s)." % (" ".join(args), timeout))
        sys.exit(1)
    out = (r.stdout or "").strip() if capture else ""
    if check and r.returncode != 0:
        print("\n✗ BŁĄD git " + " ".join(args))
        if capture:
            print((r.stdout or "").strip())
            print((r.stderr or "").strip())
        sys.exit(1)
    return out


def _gh_dostepne():
    try:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True,
                           text=True, timeout=20)
        return r.returncode == 0
    except Exception:                                        # noqa: BLE001
        return False


def _api(metoda, url, token, dane=None):
    req = urllib.request.Request(url, method=metoda)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "forestly-mapper-setup")
    body = None
    if dane is not None:
        body = json.dumps(dane).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=body, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        tresc = e.read().decode("utf-8", "replace")
        raise RuntimeError("HTTP %s: %s" % (e.code, tresc)) from None


def _ustaw_tozsamosc_gita(user):
    """Bez user.name/user.email git nie zrobi commita (i wtedy gh nie ma
    czego wysłać). Ustawiamy je LOKALNIE w tym repo, jeśli brakuje."""
    if not git("config", "user.name", check=False):
        git("config", "user.name", user)
        print("  (ustawiłem git user.name = %s)" % user)
    if not git("config", "user.email", check=False):
        git("config", "user.email", "%s@users.noreply.github.com" % user)
        print("  (ustawiłem git user.email)")


def _zrob_commit():
    """Stage + commit. Zwraca True, jeśli repo ma teraz commit."""
    git("add", "-A")
    zmiany = git("status", "--porcelain", check=False)
    if zmiany:
        print("Robię pierwszy commit…")
        r = subprocess.run(["git", "-C", str(REPO), "commit",
                            "-m", "Forestly Mapper — pierwsza wersja"],
                           text=True, encoding="utf-8", errors="replace",
                           capture_output=True)
        if r.returncode != 0:
            print("✗ commit nie wyszedł:")
            print((r.stdout or "").strip())
            print((r.stderr or "").strip())
            sys.exit(1)
    else:
        print("(Nie ma nowych zmian do zacommitowania.)")
    return bool(git("rev-parse", "--verify", "HEAD", check=False))


def main():
    user = _z_configu("GITHUB_USER", "")
    repo = _z_configu("GITHUB_REPO", "forestly-mapper")
    if not user or user == "TWOJA_NAZWA":
        print("✗ Ustaw swoje konto w app/config.py:  GITHUB_USER = \"...\"")
        print("  (teraz jest: %r)" % user)
        sys.exit(1)

    print("=" * 62)
    print("  FORESTLY MAPPER — zakładanie repo na GitHubie")
    print("=" * 62)
    print("  Konto : %s" % user)
    print("  Repo  : %s" % repo)

    # 1) git init (jeśli trzeba)
    if not git("rev-parse", "--is-inside-work-tree", check=False):
        print("\nInicjuję repozytorium git…")
        git("init", "-b", "main")
    else:
        print("\n(Repozytorium git już istnieje — używam go.)")

    # 2) tożsamość gita + pierwszy commit (to był brakujący krok)
    _ustaw_tozsamosc_gita(user)
    ma_commit = _zrob_commit()
    if not ma_commit:
        print("✗ Nie udało się zrobić commita — nie ma czego wysyłać.")
        sys.exit(1)

    # 3) repo na GitHubie — przez gh albo przez API z tokenem
    if _gh_dostepne():
        print("\nWykryłem GitHub CLI (gh) — zakładam repo przez gh…")
        r = subprocess.run(
            ["gh", "repo", "create", "%s/%s" % (user, repo), "--public",
             "--source", str(REPO), "--remote", "origin", "--push"],
            cwd=str(REPO), text=True, capture_output=True)
        if r.returncode != 0:
            blad = ((r.stdout or "") + (r.stderr or "")).strip()
            print("  (gh zgłosił: %s)" % blad)
            print("  Próbuję dokończyć ręcznie (zdalne repo + push)…")
            zdalne = git("remote", check=False)
            if "origin" not in zdalne:
                git("remote", "add", "origin",
                    "https://github.com/%s/%s.git" % (user, repo))
            git("push", "-u", "origin", "HEAD", prompt=True)
        else:
            print("✓ Repo utworzone i wysłane przez gh.")
    else:
        print("\nBrak GitHub CLI. Użyję tokenu (PAT).")
        print("Utwórz token: https://github.com/settings/tokens")
        print("(klasyczny, z zakresem „repo”).")
        try:
            token = input("Wklej token: ").strip()
        except EOFError:
            token = ""
        if not token:
            print("✗ Bez tokenu nie założę repo. Nic nie zmieniono.")
            sys.exit(1)
        try:
            _api("POST", "https://api.github.com/user/repos", token,
                 {"name": repo, "private": False, "description": OPIS_REPO})
            print("✓ Repo utworzone.")
        except RuntimeError as e:
            if "422" in str(e):      # już istnieje
                print("(Repo już istnieje na koncie — dodaję tylko zdalne i wysyłam.)")
            else:
                print("✗ Nie udało się utworzyć repo:", e)
                sys.exit(1)
        zdalne = git("remote", check=False)
        if "origin" not in zdalne:
            git("remote", "add", "origin",
                "https://github.com/%s/%s.git" % (user, repo))
        print("Wysyłam pliki na GitHub (może poprosić o hasło/token)…")
        git("push", "-u", "origin", "HEAD", prompt=True)

    # 4) tag startowy — uruchamia pierwszą budowę EXE przez Actions
    print("\nUstawiam tag %s (uruchomi budowę EXE przez GitHub Actions)…"
          % TAG_PIERWSZY)
    if not git("tag", "-l", TAG_PIERWSZY):
        git("tag", TAG_PIERWSZY)
        git("push", "origin", TAG_PIERWSZY, prompt=True)

    print("\n✓ GOTOWE")
    print("  Repo    : https://github.com/%s/%s" % (user, repo))
    print("  Budowa  : https://github.com/%s/%s/actions" % (user, repo))
    print("  Release : https://github.com/%s/%s/releases" % (user, repo))
    print("\nPo paru minutach w zakładce Actions zobaczysz budowę, a w Releases")
    print("gotowy Forestly_Mapper.exe. Kolejne wersje: dwuklik na release.bat.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPrzerwano.")
