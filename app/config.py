"""
Forestly Mapper — konfiguracja globalna
=======================================
Ten plik jest CZYTAJ I ZAPISYWANY przez release.py (numer wersji).

Zależności: brak (tylko biblioteka standardowa) — dzięki temu importuje się
szybko i nie ciągnie ciężkich bibliotek przy starcie programu.
"""

import sys
from pathlib import Path

# --- WERSJA I AKTUALIZACJA ---
# Ten numer podnosi release.py przy wypuszczaniu nowej wersji (tag na GitHubie).
CURRENT_VERSION = "v1.0.2"

# --- REPOZYTORIUM ---
# Zmień na swoje konto, jeśli wypuszczasz pod inną nazwą użytkownika.
GITHUB_USER = "wskakuj"
GITHUB_REPO = "forestly-mapper"

# --- NAZWA PROGRAMU ---
APP_NAME = "Forestly Mapper"
APP_TITLE = "Forestly Mapper — układanie opisów na mapach GEO-MAP"


def katalog_zasobow() -> Path:
    """Folder z plikami dołączonymi do EXE (np. ui.html).

    W wersji spakowanej PyInstaller rozpakowuje zasoby do folderu _MEIPASS;
    uruchamiany ze źródeł — bierzemy folder tego pliku.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def katalog_programu() -> Path:
    """Folder, w którym leży program (EXE albo źródła) — tu zapisujemy logi."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
