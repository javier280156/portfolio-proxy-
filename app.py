from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import time
import threading
import logging

# ── Scraper en hilo de fondo ──────────────────────────────────────────────
try:
    from live_scraper_v2 import run_loop as scraper_run_loop
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False
    logging.warning("live_scraper_v2.py no encontrado — scraper desactivado")

app = Flask(__name__)
CORS(app)

# Cache en memoria (15 minutos)
cache = {}
CACHE_TTL = 15 * 60

def get_cache(key):
    entry = cache.get(key)
    if not entry:
        return None
    if time.time() - entry['ts'] > CACHE_TTL:
        del cache[key]
        return None
    return entry['data']

def set_cache(key, data):
    cache[key] = {'data': data, 'ts': time.time()}

# ── PORTFOLIO ROUTES ──────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({
        'ok': True,
        'ts': int(time.time()),
        'cacheSize': len(cache),
        'scraper': scraper_status.get('running', False)
    })

@app.route('/quote')
def quote():
    symbol = request.args.get('symbol', '').strip()
    if not symbol:
        return jsonify({'error': 'symbol required'}), 400
    cached = get_cache('quote:' + symbol)
    if cached:
        return jsonify(cached)
    result = {}
    symbols = [s.strip() for s in symbol.split(',')]
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            info = t.fast_info
            prev = info.previous_close or info.last_price
            price = info.last_price
            change = price - prev
            changePct = (change / prev * 100) if prev else 0
            result[sym] = {
                'symbol': sym,
                'price': round(price, 4) if price else None,
                'change': round(change, 4),
                'changePct': round(changePct, 4),
                'prevClose': round(prev, 4) if prev else None,
                'currency': getattr(info, 'currency', 'USD'),
                'timestamp': int(time.time()),
            }
        except Exception as e:
            print(f'[quote error] {sym}: {e}')
    set_cache('quote:' + symbol, result)
    return jsonify(result)

@app.route('/dividend')
def dividend():
    symbol = request.args.get('symbol', '').strip()
    if not symbol:
        return jsonify({'error': 'symbol required'}), 400
    cached = get_cache('div:' + symbol)
    if cached:
        return jsonify(cached)
    try:
        t = yf.Ticker(symbol)
        info = t.info
        dividend_yield = info.get('dividendYield')
        result = {
            'symbol': symbol,
            'name': info.get('longName') or info.get('shortName') or symbol,
            'price': info.get('regularMarketPrice') or info.get('currentPrice'),
            'currency': info.get('currency', 'USD'),
            'annualDividend': info.get('dividendRate'),
            'yieldPct': round(dividend_yield * 100, 2) if dividend_yield else None,
            'exDividendDate': info.get('exDividendDate'),
            'payoutRatio': info.get('payoutRatio'),
            'fiveYearAvgDividendYield': info.get('fiveYearAvgDividendYield'),
            'timestamp': int(time.time()),
        }
        set_cache('div:' + symbol, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/debug')
def debug():
    symbol = request.args.get('symbol', '').strip()
    if not symbol:
        return jsonify({'error': 'symbol required'}), 400
    try:
        t = yf.Ticker(symbol)
        return jsonify({'info': t.info, 'fast_info': dict(t.fast_info)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── SCRAPER ROUTES ────────────────────────────────────────────────────────

scraper_status = {'running': False, 'started_at': None}

@app.route('/scraper/status')
def scraper_status_route():
    return jsonify(scraper_status)

@app.route('/scraper/sync/today')
def scraper_sync_today():
    if not SCRAPER_AVAILABLE:
        return jsonify({'error': 'Scraper no disponible'}), 503
    try:
        from live_scraper_v2 import sync_today
        threading.Thread(target=sync_today, daemon=True).start()
        return jsonify({'triggered': 'today'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/scraper/sync/live')
def scraper_sync_live():
    if not SCRAPER_AVAILABLE:
        return jsonify({'error': 'Scraper no disponible'}), 503
    try:
        from live_scraper_v2 import sync_live
        threading.Thread(target=sync_live, daemon=True).start()
        return jsonify({'triggered': 'live'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/scraper/sync/<liga>')
def scraper_sync_liga(liga):
    if not SCRAPER_AVAILABLE:
        return jsonify({'error': 'Scraper no disponible'}), 503
    ligas_map = {
        'laliga'     : ('4335', 'LaLiga'),
        'laliga2'    : ('4953', 'LaLiga 2'),
        'premier'    : ('4328', 'Premier League'),
        'bundesliga' : ('4331', 'Bundesliga'),
        'seriea'     : ('4332', 'Serie A'),
        'ligue1'     : ('4334', 'Ligue 1'),
        'champions'  : ('4480', 'Champions League'),
        'europa'     : ('4481', 'Europa League'),
        'conference' : ('4498', 'Conference League'),
        'copadelrey' : ('4342', 'Copa del Rey'),
    }
    if liga not in ligas_map:
        return jsonify({'error': f'Liga desconocida: {liga}', 'disponibles': list(ligas_map.keys())}), 400
    lid, lname = ligas_map[liga]
    try:
        from live_scraper_v2 import sync_league
        threading.Thread(target=lambda: sync_league(lid, lname), daemon=True).start()
        return jsonify({'triggered': lname})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── ARRANQUE ──────────────────────────────────────────────────────────────

def start_scraper_background():
    """Lanza el bucle del scraper en un hilo separado."""
    if not SCRAPER_AVAILABLE:
        logging.warning("Scraper no disponible — omitiendo")
        return
    scraper_status['running'] = True
    scraper_status['started_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    logging.info("🚀 Scraper lanzado en hilo de fondo")
    try:
        scraper_run_loop()
    except Exception as e:
        logging.error(f"Scraper detenido con error: {e}")
        scraper_status['running'] = False

# Lanzar scraper al arrancar (solo en producción con gunicorn)
scraper_thread = threading.Thread(target=start_scraper_background, daemon=True)
scraper_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
