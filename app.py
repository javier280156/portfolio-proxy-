from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import time

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

@app.route('/health')
def health():
    return jsonify({'ok': True, 'ts': int(time.time()), 'cacheSize': len(cache)})

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
