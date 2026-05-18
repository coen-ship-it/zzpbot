"""
monitor.py — ZZPbot Desktop Monitor (Windows)
Pollt elke 10 seconden het actieve venster, stuurt elke 5 minuten
een geaggregeerde samenvatting naar de server, en slaat alles lokaal op
in monitoring_data.json (te uploaden na een week).

Build naar .exe met:
    pyinstaller build_monitor.spec
"""

import glob
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

# Windows-specifieke imports
try:
    import win32gui
    import win32process
    import psutil
    WINDOWS = True
except ImportError:
    WINDOWS = False

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

POLL_INTERVAL   = 10      # seconden tussen vensterpolls
SEND_INTERVAL   = 300     # seconden tussen server-batch (5 min)
SAVE_INTERVAL   = 60      # seconden tussen lokale opslag
DATA_FILE       = "monitoring_data.json"
LOG_FILE        = "monitor.log"
VERSION         = "1.0.0"

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("zzpbot")

# ---------------------------------------------------------------------------
# App categorisatie
# ---------------------------------------------------------------------------

CATEGORIEEN: dict[str, list[str]] = {
    "Email":         ["outlook.exe", "thunderbird.exe", "mailbird.exe"],
    "Browser":       ["chrome.exe", "firefox.exe", "msedge.exe", "brave.exe", "opera.exe", "iexplore.exe"],
    "Spreadsheets":  ["excel.exe"],
    "Tekstverwerker":["winword.exe", "wordpad.exe", "write.exe"],
    "Communicatie":  ["teams.exe", "slack.exe", "zoom.exe", "skype.exe", "discord.exe", "lync.exe"],
    "Boekhouding":   ["snelstart", "e-boekhouden", "twinfield", "exact", "moneybird", "quickbooks"],
    "Design":        ["photoshop.exe", "illustrator.exe", "figma.exe", "affinity", "paint.exe", "mspaint.exe"],
    "Ontwikkeling":  ["code.exe", "pycharm64.exe", "idea64.exe", "sublime_text.exe", "notepad++.exe", "git"],
    "PDF":           ["acrobat.exe", "acrord32.exe", "foxitreader.exe", "sumatrapdf.exe"],
    "Bestandsbeheer":["explorer.exe", "totalcmd.exe"],
    "Notities":      ["onenote.exe", "obsidian.exe", "notion.exe", "evernote.exe", "notion"],
    "Planning":      ["msproject.exe", "trello", "asana", "clickup"],
}


def categorize(process_name: str, window_title: str) -> str:
    """Bepaal de categorie van een applicatie."""
    p = process_name.lower()
    t = window_title.lower()
    for cat, keywords in CATEGORIEEN.items():
        for kw in keywords:
            if kw in p or kw in t:
                return cat
    return "Overig"


# ---------------------------------------------------------------------------
# Configuratie inlezen
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """
    Laadt de zzpbot_*.json configuratie vanuit de huidige map.
    Stopt het programma als er geen configuratie gevonden wordt.
    """
    # Zoek in dezelfde map als de executable (of het script)
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

    configs = list(base.glob("zzpbot_*.json"))
    if not configs:
        print("\n" + "="*60)
        print("FOUT: Geen zzpbot configuratiebestand gevonden!")
        print("")
        print("Zorg dat zzpbot_*.json in dezelfde map staat")
        print("als monitor.exe (of monitor.py).")
        print("")
        print("Download je configuratiebestand op: zzpbot.nl/intake")
        print("="*60)
        input("\nDruk op Enter om te sluiten...")
        sys.exit(1)

    config_path = configs[0]
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    print(f"✓ Configuratie geladen: {config_path.name}")
    return config


# ---------------------------------------------------------------------------
# Vensterbeheer (Windows API)
# ---------------------------------------------------------------------------

def get_active_window() -> dict:
    """Haal info op over het momenteel actieve venster."""
    if not WINDOWS:
        # Testmodus op niet-Windows systemen
        import random
        test_windows = [
            ("Microsoft Outlook", "OUTLOOK.EXE"),
            ("Spreadsheet - Excel", "EXCEL.EXE"),
            ("Google Chrome", "chrome.exe"),
            ("Slack", "slack.exe"),
        ]
        title, process = random.choice(test_windows)
        return {"title": title, "process": process, "pid": 0}

    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return {}

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            proc = psutil.Process(pid)
            process_name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_name = "onbekend.exe"

        return {"title": title, "process": process_name, "pid": pid}

    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Monitor klasse
# ---------------------------------------------------------------------------

class Monitor:
    def __init__(self, config: dict):
        self.config    = config
        self.client_id = config["client_id"]
        self.naam      = config.get("naam", "")
        self.server    = config.get("server_url", "http://localhost:5000").rstrip("/")

        self.sessions: list[dict] = []
        self.current_window: dict | None = None
        self.current_start: float = 0.0

        self._last_send = time.time()
        self._last_save = time.time()
        self._start_time = datetime.now().isoformat()

        self._load_existing()

    # ---- Persistentie ----

    def _load_existing(self) -> None:
        """Herlaad bestaande data als de monitor opnieuw wordt gestart."""
        if not Path(DATA_FILE).exists():
            return
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self.sessions = data.get("sessions", [])
            self._start_time = data.get("start_date", self._start_time)
            log.info(f"Bestaande data geladen: {len(self.sessions)} sessies")
        except Exception as e:
            log.warning(f"Kon bestaande data niet laden: {e}")

    def _save_local(self) -> None:
        """Sla alle data op in monitoring_data.json."""
        self._flush_current()
        data = {
            "client_id":    self.client_id,
            "naam":         self.naam,
            "versie":       VERSION,
            "start_date":   self._start_time,
            "end_date":     datetime.now().isoformat(),
            "sessions":     self.sessions,
            "summary":      self._compute_summary(),
        }
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)

    def _compute_summary(self) -> dict:
        """Bereken samenvattingsstatistieken."""
        by_process:  dict[str, float] = defaultdict(float)
        by_category: dict[str, float] = defaultdict(float)
        total = 0.0

        for s in self.sessions:
            dur = s.get("duration_seconds", 0)
            by_process[s.get("process", "onbekend")] += dur
            by_category[s.get("category", "Overig")] += dur
            total += dur

        return {
            "total_seconds": total,
            "total_hours":   round(total / 3600, 2),
            "by_process":    dict(sorted(by_process.items(), key=lambda x: x[1], reverse=True)),
            "by_category":   dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True)),
        }

    # ---- Venster tracking ----

    def _flush_current(self) -> None:
        """Sla het huidige venster op als sessie."""
        if not self.current_window or not self.current_start:
            return
        duration = time.time() - self.current_start
        if duration < 5:  # Negeer flitsen korter dan 5 seconden
            return

        cat = categorize(
            self.current_window.get("process", ""),
            self.current_window.get("title", ""),
        )
        self.sessions.append({
            "timestamp":        datetime.fromtimestamp(self.current_start).isoformat(),
            "process":          self.current_window.get("process", ""),
            "title":            self.current_window.get("title", ""),
            "category":         cat,
            "duration_seconds": int(duration),
        })

    def poll(self) -> None:
        """Één polling-cyclus: check actief venster."""
        window = get_active_window()
        if not window or not window.get("title"):
            return

        changed = (
            self.current_window is None
            or window["process"] != self.current_window.get("process")
            or window["title"] != self.current_window.get("title")
        )
        if changed:
            self._flush_current()
            self.current_window = window
            self.current_start  = time.time()

    # ---- Server communicatie ----

    def send_to_server(self) -> None:
        """Stuur batch naar de server."""
        summary = self._compute_summary()
        payload = {
            "client_id":       self.client_id,
            "timestamp":       datetime.now().isoformat(),
            "summary":         summary,
            "recent_sessions": self.sessions[-30:],
        }
        try:
            r = requests.post(
                f"{self.server}/activity",
                json=payload,
                timeout=10,
            )
            if r.status_code == 200:
                log.info(f"✓ Data verstuurd naar server ({len(self.sessions)} sessies totaal)")
            else:
                log.warning(f"Server antwoordde {r.status_code}")
        except requests.exceptions.ConnectionError:
            log.info("Server niet bereikbaar — data wordt lokaal bewaard")
        except Exception as e:
            log.warning(f"Verstuurdfout: {e}")

    # ---- Status output ----

    def print_status(self) -> None:
        summary = self._compute_summary()
        uren    = summary["total_hours"]
        cat_top = list(summary["by_category"].items())[:3]
        cat_str = " | ".join(f"{c}: {round(s/3600,1)}u" for c, s in cat_top)
        log.info(f"📊 {uren} uur getrackt — Top: {cat_str or 'nog geen data'}")

    # ---- Hoofdloop ----

    def run(self) -> None:
        print()
        print("=" * 60)
        print(f"  ZZPbot Monitor v{VERSION}")
        print(f"  Ondernemer : {self.naam}")
        print(f"  Client ID  : {self.client_id}")
        print(f"  Server     : {self.server}")
        print(f"  Data       : {DATA_FILE}")
        print("=" * 60)
        print()
        print("Monitoring actief... (Ctrl+C om te stoppen)")
        print()

        try:
            while True:
                self.poll()
                time.sleep(POLL_INTERVAL)

                now = time.time()

                # Lokale opslag
                if now - self._last_save >= SAVE_INTERVAL:
                    self._save_local()
                    self._last_save = now

                # Verstuur naar server
                if now - self._last_send >= SEND_INTERVAL:
                    self._flush_current()
                    self.send_to_server()
                    self.print_status()
                    self._last_send = now

        except KeyboardInterrupt:
            print()
            print("Monitoring gestopt.")
            self._flush_current()
            self._save_local()
            summary = self._compute_summary()
            print()
            print("=" * 60)
            print(f"  Totaal getrackt : {summary['total_hours']} uur")
            print(f"  Sessies         : {len(self.sessions)}")
            print(f"  Opgeslagen in   : {DATA_FILE}")
            print()
            print("  Upload je data op:")
            print(f"  {self.server}/upload")
            print("=" * 60)
            input("\nDruk op Enter om te sluiten...")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    if not WINDOWS:
        print("⚠️  WAARSCHUWING: win32-modules niet beschikbaar.")
        print("   Testmodus actief (willekeurige vensterdata).\n")

    config  = load_config()
    monitor = Monitor(config)
    monitor.run()


if __name__ == "__main__":
    main()
