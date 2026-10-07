"""
Forestly Mapper — aktualizator GitHub
=====================================
Zależności: config.py (CURRENT_VERSION, GITHUB_USER, GITHUB_REPO)

Odpowiada za:
  * sprawdzenie, czy na GitHubie jest nowsze wydanie (Release),
  * pobranie nowego Forestly_Mapper.exe i podmianę go na działający plik
    (przez graficzny skrypt PowerShell — tak jak w Forestly).

Sprawdzenie przy starcie jest ciche (błędy sieci ignorujemy). Ręczne
„Sprawdź aktualizacje" pokazuje wynik.
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from app.config import CURRENT_VERSION, GITHUB_USER, GITHUB_REPO

NAZWA_EXE = "Forestly_Mapper.exe"
API_LATEST = ("https://api.github.com/repos/%s/%s/releases/latest"
              % (GITHUB_USER, GITHUB_REPO))


def _wersja_krotka(v):
    """'v1.2.3' -> (1, 2, 3); cokolwiek innego -> (0,)."""
    try:
        return tuple(map(int, re.findall(r"\d+", str(v))))
    except Exception:                                        # noqa: BLE001
        return (0,)


def sprawdz(timeout=6):
    """Sprawdza najnowsze wydanie na GitHubie.

    Zwraca słownik:
        {"ok": bool, "nowsza": bool, "obecna": str, "wersja": str,
         "opis": str, "url": str, "pliki": [(nazwa, url), ...], "blad": str}
    """
    wynik = {"ok": False, "nowsza": False, "obecna": CURRENT_VERSION,
             "wersja": "", "opis": "", "url": "", "pliki": [], "blad": ""}
    try:
        req = urllib.request.Request(API_LATEST,
                                     headers={"User-Agent": "ForestlyMapper-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dane = json.loads(resp.read().decode("utf-8"))
    except Exception as e:                                   # noqa: BLE001
        wynik["blad"] = str(e)
        return wynik

    wynik["ok"] = True
    wynik["wersja"] = dane.get("tag_name") or ""
    wynik["opis"] = dane.get("body") or ""
    wynik["url"] = dane.get("html_url") or ""
    wynik["nowsza"] = bool(wynik["wersja"]) and \
        _wersja_krotka(wynik["wersja"]) > _wersja_krotka(CURRENT_VERSION)

    exe = [a for a in dane.get("assets", []) if a.get("name", "").lower().endswith(".exe")]
    by_name = {a["name"]: a for a in exe}
    if NAZWA_EXE in by_name:
        wynik["pliki"] = [(NAZWA_EXE, by_name[NAZWA_EXE]["browser_download_url"])]
    elif exe:      # fallback: pierwszy .exe z wydania
        wynik["pliki"] = [(exe[0]["name"], exe[0]["browser_download_url"])]
    return wynik


def _ps_literal(v):
    return "'" + str(v).replace("'", "''") + "'"


def pobierz_i_zainstaluj(pliki, wersja, opis=""):
    """Pobiera nowe pliki i podmienia je na działające, po czym restartuje program.

    `pliki` to lista (nazwa, url). Działa tylko w wersji spakowanej do EXE.
    Zwraca (True, "") gdy się udało (proces kończy się sam), albo (False, błąd).
    """
    if not getattr(sys, "frozen", False):
        return False, ("Automatyczna podmiana działa tylko w wersji .exe. "
                       "Uruchomiony ze źródeł — pobierz nową wersję ręcznie z Releases.")
    if not pliki:
        return False, "W wydaniu nie ma pliku .exe do pobrania."

    try:
        exe_path = Path(sys.executable).resolve()
        target_dir = exe_path.parent
        pid = os.getpid()

        ps_downloads = ",\n            ".join(
            "@{{ Name = {0}; Url = {1} }}".format(_ps_literal(n), _ps_literal(u))
            for n, u in pliki)

        changelog_b64 = base64.b64encode(
            json.dumps({"version": wersja, "changelog": opis},
                       ensure_ascii=False).encode("utf-8")).decode("utf-8")

        ps_script = f"""
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    function Clear-PyInstallerEnv {{
        $names = @('_MEIPASS','_MEIPASS2','PYTHONHOME','PYTHONPATH',
                   'TCL_LIBRARY','TK_LIBRARY','_PYVENV_LAUNCHER_','__PYVENV_LAUNCHER__')
        foreach ($n in $names) {{ Remove-Item -Path "Env:$n" -ErrorAction SilentlyContinue }}
        Get-ChildItem Env: -ErrorAction SilentlyContinue |
            Where-Object {{ $_.Name -like '_MEI*' -or $_.Name -like '_PYI*' }} |
            ForEach-Object {{ Remove-Item -Path "Env:$($_.Name)" -ErrorAction SilentlyContinue }}
        if ($env:PATH) {{
            $clean = $env:PATH -split ';' | Where-Object {{ $_ -and ($_ -notmatch '_MEI') }}
            $env:PATH = ($clean -join ';')
        }}
    }}

    function Test-FileLocked {{
        param([string]$Path)
        if (-not (Test-Path -Path $Path)) {{ return $false }}
        try {{ $fs = [System.IO.File]::Open($Path,'Open','ReadWrite','None'); $fs.Close(); return $false }}
        catch {{ return $true }}
    }}

    Clear-PyInstallerEnv

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Forestly Mapper — Aktualizacja"
    $form.Size = New-Object System.Drawing.Size(520, 214)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedToolWindow"
    $form.BackColor = [System.Drawing.Color]::FromArgb(35, 38, 45)
    $form.ForeColor = [System.Drawing.Color]::White
    $form.TopMost = $true

    $title = New-Object System.Windows.Forms.Label
    $title.Location = New-Object System.Drawing.Point(20, 16)
    $title.Size = New-Object System.Drawing.Size(470, 28)
    $title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 12)
    $title.ForeColor = [System.Drawing.Color]::FromArgb(79, 163, 255)
    $title.Text = "Forestly Mapper — Aktualizacja"
    $form.Controls.Add($title)

    $label = New-Object System.Windows.Forms.Label
    $label.Location = New-Object System.Drawing.Point(20, 54)
    $label.Size = New-Object System.Drawing.Size(470, 46)
    $label.Font = New-Object System.Drawing.Font("Segoe UI", 10)
    $label.ForeColor = [System.Drawing.Color]::FromArgb(232, 232, 232)
    $label.Text = "Czekam na zamknięcie starej wersji programu..."
    $form.Controls.Add($label)

    $progressBar = New-Object System.Windows.Forms.ProgressBar
    $progressBar.Location = New-Object System.Drawing.Point(20, 108)
    $progressBar.Size = New-Object System.Drawing.Size(460, 14)
    $progressBar.Style = "Marquee"
    $progressBar.MarqueeAnimationSpeed = 30
    $form.Controls.Add($progressBar)

    $footer = New-Object System.Windows.Forms.Label
    $footer.Location = New-Object System.Drawing.Point(20, 176)
    $footer.Size = New-Object System.Drawing.Size(470, 20)
    $footer.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
    $footer.ForeColor = [System.Drawing.Color]::FromArgb(120, 128, 138)
    $footer.Text = "Instaluję wersję {wersja}"
    $form.Controls.Add($footer)

    $form.Add_Shown({{
        $form.Refresh()
        $pidToWait = {pid}
        $exePath = {_ps_literal(exe_path)}
        $targetDir = {_ps_literal(target_dir)}
        $downloads = @(
            {ps_downloads}
        )
        $waitStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        while ((Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) -or (Test-FileLocked $exePath)) {{
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 200
            if ($waitStopwatch.Elapsed.TotalSeconds -gt 30) {{ break }}
        }}
        Start-Sleep -Milliseconds 500
        $label.Text = "Pobieranie nowej wersji. To może chwilę potrwać..."
        $form.Refresh()
        try {{
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $webClient = New-Object System.Net.WebClient
            foreach ($d in $downloads) {{
                $tempPath = Join-Path $env:TEMP ("ForestlyMapper_Update_" + $d.Name)
                $label.Text = "Pobieranie: " + $d.Name + "..."
                $form.Refresh()
                $webClient.DownloadFileAsync([uri]$d.Url, $tempPath)
                while ($webClient.IsBusy) {{
                    [System.Windows.Forms.Application]::DoEvents()
                    Start-Sleep -Milliseconds 50
                }}
                $file = Get-Item $tempPath -ErrorAction SilentlyContinue
                if ($null -eq $file -or ($file.Length / 1MB) -lt 1) {{
                    $label.Text = "BŁĄD: Pobrany plik " + $d.Name + " jest uszkodzony."
                    $label.ForeColor = [System.Drawing.Color]::Red
                    $progressBar.Style = "Blocks"
                    $form.Refresh(); Start-Sleep -Seconds 5; $form.Close(); exit 1
                }}
            }}
            $label.Text = "Pobrano poprawnie. Podmiana plików..."
            $form.Refresh(); Start-Sleep -Milliseconds 500
            foreach ($d in $downloads) {{
                $dest = Join-Path $targetDir $d.Name
                $tempPath = Join-Path $env:TEMP ("ForestlyMapper_Update_" + $d.Name)
                if (Test-FileLocked $dest) {{ Start-Sleep -Seconds 2 }}
                $backupName = $d.Name + ".old_" + (Get-Date -Format yyyyMMddHHmmss)
                $backupPath = Join-Path $targetDir $backupName
                Remove-Item -Path $backupPath -Force -ErrorAction SilentlyContinue
                if (Test-Path -Path $dest) {{
                    try {{ Rename-Item -Path $dest -NewName $backupName -Force -ErrorAction Stop }}
                    catch {{ Remove-Item -Path $dest -Force -ErrorAction SilentlyContinue }}
                }}
                Move-Item -Path $tempPath -Destination $dest -Force
                Remove-Item -Path $backupPath -Force -ErrorAction SilentlyContinue
            }}
            $changelogFile = Join-Path $targetDir "pending_changelog.json"
            $jsonBytes = [System.Convert]::FromBase64String("{changelog_b64}")
            [System.IO.File]::WriteAllBytes($changelogFile, $jsonBytes)
            $label.Text = "Zakończono! Uruchamianie nowej wersji..."
            $label.ForeColor = [System.Drawing.Color]::LightGreen
            $progressBar.Style = "Blocks"; $progressBar.Value = 100
            $form.Refresh(); Start-Sleep -Seconds 1
            Clear-PyInstallerEnv
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $exePath
            $psi.WorkingDirectory = $targetDir
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true
            $removeNames = @('_MEIPASS','_MEIPASS2','PYTHONHOME','PYTHONPATH',
                             'TCL_LIBRARY','TK_LIBRARY','_PYVENV_LAUNCHER_','__PYVENV_LAUNCHER__')
            foreach ($n in $removeNames) {{
                if ($psi.EnvironmentVariables.ContainsKey($n)) {{ $psi.EnvironmentVariables.Remove($n) }}
            }}
            foreach ($key in @($psi.EnvironmentVariables.Keys)) {{
                if ($key -like '_MEI*' -or $key -like '_PYI*') {{ $psi.EnvironmentVariables.Remove($key) }}
            }}
            $pathKey = $null
            foreach ($key in @($psi.EnvironmentVariables.Keys)) {{ if ($key -eq 'PATH') {{ $pathKey = $key }} }}
            if ($pathKey) {{ $psi.EnvironmentVariables[$pathKey] = $env:PATH }}
            else {{ $psi.EnvironmentVariables['PATH'] = $env:PATH }}
            [System.Diagnostics.Process]::Start($psi) | Out-Null
        }} catch {{
            $label.Text = "Wystąpił błąd podczas aktualizacji."
            $label.ForeColor = [System.Drawing.Color]::Red
            $progressBar.Style = "Blocks"
            $form.Refresh(); Start-Sleep -Seconds 5
        }}
        $form.Close()
    }})

    $form.ShowDialog()
    """

        # czyste środowisko dla PowerShell (bez ścieżek PyInstallera)
        pomin = {"_MEIPASS", "_MEIPASS2", "PYTHONHOME", "PYTHONPATH",
                 "TCL_LIBRARY", "TK_LIBRARY", "_PYVENV_LAUNCHER_",
                 "__PYVENV_LAUNCHER__"}
        meipass = None
        if getattr(sys, "_MEIPASS", None):
            meipass = Path(sys._MEIPASS)
        clean_env = {}
        for key, value in os.environ.items():
            uk = key.upper()
            if uk in pomin or uk.startswith("_MEI") or uk.startswith("_PYI"):
                continue
            if uk == "PATH":
                czesci = [p for p in str(value).split(os.pathsep)
                          if p and "_MEI" not in p.upper()]
                value = os.pathsep.join(czesci)
            clean_env[key] = value

        subprocess.Popen(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
             "-Command", ps_script],
            env=clean_env, creationflags=subprocess.CREATE_NO_WINDOW)
        return True, ""
    except Exception as e:                                   # noqa: BLE001
        return False, str(e)


def zjedz_pending_changelog(katalog):
    """Jeśli instalator zapisał pending_changelog.json — zwraca jego treść
    (żeby po aktualizacji pokazać „Co nowego") i usuwa plik."""
    try:
        p = Path(katalog) / "pending_changelog.json"
        if not p.exists():
            return None
        dane = json.loads(p.read_text(encoding="utf-8"))
        p.unlink(missing_ok=True)
        return dane
    except Exception:                                        # noqa: BLE001
        return None
