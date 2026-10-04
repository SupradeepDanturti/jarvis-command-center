"""Optional read-only feeds. Fixed providers; no URLs, keys, or disk history."""
import asyncio
from collections import OrderedDict, deque
from datetime import datetime, timezone
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirects are not accepted')


def read_json(url):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'JarvisCommandCenter/1.0'})
    with build_opener(NoRedirect()).open(request, timeout=6) as response:
        if response.headers.get_content_type() != 'application/json':
            raise ValueError('Unexpected content')
        raw = response.read(524289)
    if len(raw) > 524288:
        raise ValueError('Response too large')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('Invalid feed')
    return data


def number(value, low, high):
    return value if type(value) in (int, float) and math.isfinite(value) and low <= value <= high else None


def text(value, limit=100):
    if not isinstance(value, str):
        return ''
    return ''.join(c for c in value if c.isprintable())[:limit]


def stamp(value):
    return number(value, 946684800, 32503680000)


def weather(data):
    current = data.get('current') or {}
    daily = data.get('daily') or {}
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise ValueError('Invalid weather')
    observed = stamp(current.get('time'))
    if observed is None or abs(time.time() - observed) > 7200:
        raise ValueError('Outdated weather')
    days = []
    times = daily.get('time')
    if isinstance(times, list):
        for i, day in enumerate(times[:3]):
            def item(key, low, high):
                values = daily.get(key)
                return number(values[i], low, high) if isinstance(values, list) and i < len(values) else None
            if stamp(day) is not None:
                days.append({'time': day, 'high': item('temperature_2m_max', -100, 70),
                             'low': item('temperature_2m_min', -100, 70),
                             'rain': item('precipitation_probability_max', 0, 100),
                             'sunrise': item('sunrise', 946684800, 32503680000),
                             'sunset': item('sunset', 946684800, 32503680000)})
    return {'observedAt': observed, 'timezone': text(data.get('timezone'), 80),
            'temperature': number(current.get('temperature_2m'), -100, 70),
            'feelsLike': number(current.get('apparent_temperature'), -120, 90),
            'humidity': number(current.get('relative_humidity_2m'), 0, 100),
            'wind': number(current.get('wind_speed_10m'), 0, 500),
            'code': number(current.get('weather_code'), 0, 99), 'days': days}


def air_quality(data):
    current = data.get('current') or {}
    if not isinstance(current, dict):
        raise ValueError('Invalid air quality')
    observed = stamp(current.get('time'))
    if observed is None or abs(time.time() - observed) > 10800:
        raise ValueError('Outdated air quality')
    return {'observedAt': observed, 'aqi': number(current.get('us_aqi'), 0, 1000),
            'pm25': number(current.get('pm2_5'), 0, 10000), 'pm10': number(current.get('pm10'), 0, 10000)}


def locations(data):
    result = []
    for entry in (data.get('results') or [])[:5]:
        if not isinstance(entry, dict):
            continue
        lat, lon = number(entry.get('latitude'), -90, 90), number(entry.get('longitude'), -180, 180)
        name = text(entry.get('name'), 60)
        if lat is not None and lon is not None and name:
            label = ', '.join(filter(None, [name, text(entry.get('admin1'), 60), text(entry.get('country'), 60)]))
            result.append({'name': label[:160], 'latitude': round(lat, 3), 'longitude': round(lon, 3)})
    return {'locations': result}


def race_time(entry):
    try:
        value = datetime.fromisoformat(entry['date'] + 'T' + entry['time'].replace('Z', '+00:00'))
        return value.timestamp() if value.tzinfo is not None else None
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


def races(data):
    entries = data.get('MRData', {}).get('RaceTable', {}).get('Races')
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError('Invalid schedule')
    result = []
    now = time.time()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        start = number(race_time(entry), now - 366 * 86400, now + 366 * 86400)
        circuit = entry.get('Circuit') or {}
        location = circuit.get('Location') or {}
        if not isinstance(circuit, dict) or not isinstance(location, dict):
            continue
        if start is not None and text(entry.get('raceName')):
            result.append({'name': text(entry['raceName']), 'start': start,
                           'circuit': text(circuit.get('circuitName')),
                           'location': ', '.join(filter(None, [text(location.get('locality'), 60), text(location.get('country'), 60)])),
                           'qualifying': number(race_time(entry.get('Qualifying') or {}), start - 7 * 86400, start)})
    return {'races': sorted(result, key=lambda race: race['start'])}


class WidgetFeeds:
    def __init__(self, fetch=read_json, clock=time.monotonic):
        self.fetch, self.clock = fetch, clock
        self.cache = OrderedDict()
        self.pending = {}
        self.requests = deque()
        self.closed = False

    async def get(self, kind, latitude=None, longitude=None, query=None):
        now = self.clock()
        year = datetime.now(timezone.utc).year
        coords = (round(latitude, 3), round(longitude, 3)) if latitude is not None else None
        key = (kind, coords, query, year if kind == 'f1' else None)
        cached = self.cache.get(key)
        if cached and cached['expires'] > now:
            self.cache.move_to_end(key)
            return self.snapshot(kind, cached)
        if self.closed:
            return self.snapshot(kind, None)
        if key not in self.pending:
            while self.requests and self.requests[0] <= now - 60:
                self.requests.popleft()
            if len(self.pending) >= 4 or len(self.requests) >= 30:
                return self.snapshot(kind, cached, unavailable=True)
            self.requests.append(now)
            self.pending[key] = asyncio.create_task(self.load(key, kind, coords, query, year, cached))
        await asyncio.shield(self.pending[key])
        return self.snapshot(kind, self.cache.get(key))

    async def load(self, key, kind, coords, query, year, previous):
        ttl = {'weather': 900, 'air-quality': 1800, 'locations': 3600, 'f1': 3600}[kind]
        try:
            if kind == 'locations':
                url = 'https://geocoding-api.open-meteo.com/v1/search?' + urlencode({'name': query, 'count': 5, 'language': 'en', 'format': 'json'})
                normalize = locations
            elif kind == 'f1':
                url = f'https://api.jolpi.ca/ergast/f1/{year}/?limit=100'
                normalize = races
            else:
                parameters = {'latitude': coords[0], 'longitude': coords[1], 'timeformat': 'unixtime'}
                if kind == 'weather':
                    parameters.update(current='temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code',
                                      daily='temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset', timezone='auto', forecast_days=3)
                    url = 'https://api.open-meteo.com/v1/forecast?' + urlencode(parameters)
                    normalize = weather
                else:
                    parameters.update(current='us_aqi,pm2_5,pm10')
                    url = 'https://air-quality-api.open-meteo.com/v1/air-quality?' + urlencode(parameters)
                    normalize = air_quality
            data = normalize(await asyncio.wait_for(asyncio.to_thread(self.fetch, url), timeout=8))
            entry = {'data': data, 'fetchedAt': time.time(), 'expires': self.clock() + ttl, 'failed': False}
        except asyncio.CancelledError:
            raise
        except Exception:
            # Provider exceptions may include location query strings; never log them.
            entry = {**(previous or {'data': None, 'fetchedAt': None}), 'expires': self.clock() + 60, 'failed': True}
        finally:
            self.pending.pop(key, None)
        if not self.closed:
            self.cache[key] = entry
            self.cache.move_to_end(key)
            while len(self.cache) > 32:
                self.cache.popitem(last=False)

    def snapshot(self, kind, entry, unavailable=False):
        now = time.time()
        data = entry.get('data') if entry else None
        age = now - entry['fetchedAt'] if entry and entry.get('fetchedAt') else float('inf')
        stale = bool(unavailable or (entry and entry.get('failed')))
        if age > {'weather': 3600, 'air-quality': 7200, 'locations': 86400, 'f1': 86400}[kind]:
            data = None
        if kind == 'f1' and data is not None:
            data = {'race': next((race for race in data['races'] if race['start'] >= now), None)}
        return {'status': 'unavailable' if data is None else 'stale' if stale else 'ready',
                'data': data, 'fetchedAt': entry.get('fetchedAt') if entry else None, 'serverTime': now}

    async def close(self):
        self.closed = True
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.cache.clear()
