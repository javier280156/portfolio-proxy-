#!/usr/bin/env python3
"""
ScoutBook - Live Scraper v2
Fuente: TheSportsDB (gratuito, sin bloqueos, sin key)
"""

import requests
import time
import random
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scoutbook")

SUPABASE_URL = "https://pbfbizhspahncvmzdzsb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBiZmJpemhzcGFobmN2bXpkenNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwNzc0NjEsImV4cCI6MjA5MDY1MzQ2MX0.d5jhUNURvMXUpxCAkfiSV1FZ9YZGB2zlJ5XsQjSW-Fg"

# TheSportsDB league IDs — gratuito, sin key, sin bloqueos
LIGAS = {
    "4335" : "LaLiga",
    "4953" : "LaLiga 2",
    "4328" : "Premier League",
    "4331" : "Bundesliga",
    "4332" : "Serie A",
    "4334" : "Ligue 1",
    "4344" : "Primeira Liga",
    "4329" : "Championship",
    "4337" : "Eredivisie",
    "4480" : "Champions League",
    "4481" : "Europa League",
    "4342" : "Copa del Rey",
    "4399" : "Coppa Italia",
    "4402" : "DFB Pokal",
    "4498" : "Conference League",
}

API = "https://www.thesportsdb.com/api/v1/json/3"

SB_H = {
    "Content-Type" : "application/json",
    "apikey"       : SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Prefer"       : "return=minimal,resolution=merge-duplicates",
}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.3 Safari/605.1.15",
]

def get(url):
    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            r = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json"}, timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                wait = 30 * (2 ** attempt)
                log.warning(f"Rate limit. Esperando {wait}s...")
                time.sleep(wait)
            else:
                log.warning(f"HTTP {r.status_code}")
                time.sleep(10)
        except Exception as e:
            log.warning(f"Error (intento {attempt+1}): {e}")
            time.sleep(15)
    return None

def parse(e, league_id, league_name):
    try:
        home = e.get("strHomeTeam", "")
        away = e.get("strAwayTeam", "")
        if not home or not away:
            return None
        status_raw = (e.get("strStatus") or "").lower()
        if status_raw in ("match finished", "ft", "aet", "pen", "ap"):
            status = "FINISHED"
        elif status_raw in ("live", "1h", "2h", "ht", "match in progress"):
            status = "IN_PLAY"
        else:
            status = "SCHEDULED"
        hs = as_ = None
        if status == "FINISHED":
            try:
                hs = int(e.get("intHomeScore") or 0)
                as_ = int(e.get("intAwayScore") or 0)
            except:
                pass
        matchday = None
        try:
            matchday = int(e.get("intRound") or 0) or None
        except:
            pass
        event_id = e.get("idEvent")
        if not event_id:
            return None
        return {
            "external_id" : int(event_id),
            "league_id"   : league_id,
            "league_name" : league_name,
            "season"      : "2024",
            "match_date"  : e.get("dateEvent") or None,
            "match_time"  : (e.get("strTime") or "")[:5] or None,
            "home_team"   : home,
            "away_team"   : away,
            "home_score"  : hs,
            "away_score"  : as_,
            "status"      : status,
            "matchday"    : matchday,
            "current_minute": None,
        }
    except Exception as ex:
        log.warning(f"Parse error: {ex}")
        return None

def upsert(rows):
    if not rows:
        return 0
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/sb_fixtures?on_conflict=external_id", headers=SB_H, json=rows, timeout=20)
        if r.status_code in (200, 201, 204):
            return len(rows)
        log.warning(f"Supabase {r.status_code}: {r.text[:200]}")
        return 0
    except Exception as e:
        log.error(f"Supabase error: {e}")
        return 0

def sync_league(league_id, league_name, season="2024-2025"):
    log.info(f"📥 {league_name}...")
    data = get(f"{API}/eventsseason.php?id={league_id}&s={season}")
    events = (data.get("events") or []) if data else []
    if not events:
        data = get(f"{API}/eventsseason.php?id={league_id}&s=2024")
        events = (data.get("events") or []) if data else []
    if not events:
        past = get(f"{API}/eventspastleague.php?id={league_id}")
        nxt = get(f"{API}/eventsnextleague.php?id={league_id}")
        events = ((past or {}).get("events") or []) + ((nxt or {}).get("events") or [])
    rows = [r for e in events if (r := parse(e, league_id, league_name))]
    saved = upsert(rows)
    log.info(f"   ✅ {league_name}: {saved} partidos")
    return saved

def sync_today():
    today = datetime.now().strftime("%Y-%m-%d")
    log.info(f"📅 Partidos de hoy ({today})...")
    total = 0
    for lid, lname in LIGAS.items():
        data = get(f"{API}/eventsday.php?d={today}&l={lid}")
        events = (data.get("events") or []) if data else []
        rows = [r for e in events if (r := parse(e, lid, lname))]
        saved = upsert(rows)
        if saved:
            log.info(f"   {lname}: {saved}")
            total += saved
        time.sleep(random.uniform(0.8, 2.0))
    log.info(f"   ✅ Total: {total}")
    return total

def sync_live():
    today = datetime.now().strftime("%Y-%m-%d")
    total = 0
    for lid, lname in LIGAS.items():
        data = get(f"{API}/eventsday.php?d={today}&l={lid}")
        events = (data.get("events") or []) if data else []
        live = [e for e in events if (e.get("strStatus") or "").lower() in ("live","1h","2h","ht","match in progress")]
        if live:
            rows = [r for e in live if (r := parse(e, lid, lname))]
            saved = upsert(rows)
            if saved:
                log.info(f"   🔴 {lname}: {saved} en vivo")
                total += saved
        time.sleep(random.uniform(0.5, 1.2))
    if not total:
        log.info("   Sin partidos en vivo")
    return total

def sync_all():
    log.info("🚀 Sincronizando todas las ligas...")
    total = 0
    for lid, lname in LIGAS.items():
        try:
            total += sync_league(lid, lname)
            time.sleep(random.uniform(4, 8))
        except Exception as e:
            log.error(f"Error {lname}: {e}")
    log.info(f"🎉 Total: {total} partidos")

def run_loop():
    log.info("🚀 ScoutBook Scraper iniciado (TheSportsDB)")
    sync_today()
    last_full = 0
    while True:
        try:
            if time.time() - last_full > 86400 and 3 <= datetime.now().hour <= 5:
                sync_all()
                last_full = time.time()
            live = sync_live()
            if live > 0:
                wait = random.uniform(55, 95)
                log.info(f"   Próxima actualización en {wait:.0f}s")
            else:
                sync_today()
                wait = random.uniform(600, 1200)
                log.info(f"   Sin partidos. Siguiente en {wait/60:.0f} min")
            time.sleep(wait)
        except KeyboardInterrupt:
            log.info("⛔ Detenido")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "loop"
    cmds = {
        "loop"       : run_loop,
        "today"      : sync_today,
        "live"       : sync_live,
        "all"        : sync_all,
        "laliga"     : lambda: sync_league("4335", "LaLiga"),
        "laliga2"    : lambda: sync_league("4953", "LaLiga 2"),
        "premier"    : lambda: sync_league("4328", "Premier League"),
        "bundesliga" : lambda: sync_league("4331", "Bundesliga"),
        "seriea"     : lambda: sync_league("4332", "Serie A"),
        "ligue1"     : lambda: sync_league("4334", "Ligue 1"),
        "portugal"   : lambda: sync_league("4344", "Primeira Liga"),
        "eredivisie" : lambda: sync_league("4337", "Eredivisie"),
        "champions"  : lambda: sync_league("4480", "Champions League"),
        "europa"     : lambda: sync_league("4481", "Europa League"),
        "conference" : lambda: sync_league("4498", "Conference League"),
        "copadelrey" : lambda: sync_league("4342", "Copa del Rey"),
    }
    if cmd in cmds:
        cmds[cmd]()
    else:
        print(f"Comandos disponibles: {', '.join(cmds.keys())}")
