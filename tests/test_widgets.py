import asyncio
from datetime import datetime, timezone
import io
import json
import time
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from backend.main import create_app
from backend.widgets import WidgetFeeds, air_quality, locations, races, read_json, weather

ORIGIN = {'origin': 'https://testserver'}


def test_widget_access_origin_transport_and_revocation():
    app = create_app(pairing_code='ABCD1234')
    app.state.widgets.get = AsyncMock(return_value={'status': 'unavailable'})
    owner = TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000))
    for url, body in [('weather', {'latitude': 43.7, 'longitude': -79.4}),
                      ('air-quality', {'latitude': 43.7, 'longitude': -79.4}),
                      ('locations', {'query': 'Toronto'})]:
        assert owner.post('/api/widgets/' + url, json=body, headers=ORIGIN).status_code == 401
    assert owner.get('/api/widgets/f1').status_code == 401
    app.state.widgets.get.assert_not_called()
    token, device = app.state.devices.create('Widget QA', '192.168.1.20')
    app.state.devices.approve(device['id'])
    tablet = TestClient(app, base_url='https://testserver', client=('192.168.1.20', 4000))
    tablet.cookies.set('g16_device', token)
    assert tablet.post('/api/widgets/weather', json={'latitude': 43.7, 'longitude': -79.4}, headers={'origin': 'https://evil.example'}).status_code == 403
    assert tablet.post('/api/widgets/weather', json={'latitude': 43.7, 'longitude': -79.4}, headers=ORIGIN).status_code == 200
    assert tablet.get('/api/widgets/f1').status_code == 200
    assert tablet.post('/api/widgets/locations', json={'query': 'Toronto'}, headers=ORIGIN).status_code == 200
    remote_http = TestClient(app, base_url='http://testserver', client=('192.168.1.20', 4000))
    remote_http.cookies.set('g16_device', token)
    assert remote_http.get('/api/widgets/f1').status_code == 426
    app.state.devices.revoke(device['id'])
    assert tablet.get('/api/widgets/f1').status_code == 401


@pytest.mark.parametrize('body', [
    {'latitude': 91, 'longitude': 0}, {'latitude': 0, 'longitude': -181},
    {'latitude': True, 'longitude': 0}, {'latitude': '43.7', 'longitude': 0},
    {'latitude': 0, 'longitude': 0, 'url': 'http://localhost/secret'},
    {'latitude': 0, 'longitude': 0, 'apiKey': 'secret'},
])
def test_strict_location_inputs(body):
    app = create_app(pairing_code='ABCD1234')
    app.state.widgets.get = AsyncMock()
    client = TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000))
    client.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
    assert client.post('/api/widgets/weather', json=body, headers=ORIGIN).status_code == 422
    app.state.widgets.get.assert_not_called()


@pytest.mark.parametrize('body', [{'query': 'x'}, {'query': '  '}, {'query': 'a'*81}, {'query': 'city\nsecret'}, {'query': 'Toronto', 'url': 'https://evil.example'}])
def test_strict_search_inputs(body):
    app = create_app(pairing_code='ABCD1234')
    client = TestClient(app, base_url='https://testserver', client=('127.0.0.1', 4000))
    client.post('/api/pair', json={'code': 'ABCD1234'}, headers=ORIGIN)
    assert client.post('/api/widgets/locations', json=body, headers=ORIGIN).status_code == 422


def weather_fixture():
    return {'current': {'time': time.time(), 'temperature_2m': 14, 'wind_speed_10m': 5},
            'timezone': 'America/Toronto', 'daily': {'time': [time.time()], 'temperature_2m_max': [18], 'temperature_2m_min': [8]}}


def test_normalization_missing_corrupt_stale_numbers_and_text():
    sample = weather_fixture()
    sample['current'].update(temperature_2m=True, apparent_temperature=float('nan'), relative_humidity_2m=300)
    normalized = weather(sample)
    assert normalized['temperature'] is None
    assert normalized['feelsLike'] is None
    assert normalized['humidity'] is None
    assert normalized['days'][0]['rain'] is None
    sample['current']['time'] = time.time() - 86400
    with pytest.raises(ValueError):
        weather(sample)
    with pytest.raises(ValueError):
        weather({'current': ['bad']})
    with pytest.raises(ValueError):
        air_quality({'current': {'time': time.time() - 86400}})
    assert air_quality({'current': {'time': time.time(), 'us_aqi': -2}})['aqi'] is None
    assert locations({'results': [{'name': 'Toronto\n', 'latitude': 43.70049, 'longitude': -79.4, 'country': 'Canada', 'url': 'http://evil'}]}) == {'locations': [{'name': 'Toronto, Canada', 'latitude': 43.7, 'longitude': -79.4}]}


def test_f1_only_real_timed_future_events_without_live_fields():
    tomorrow = datetime.fromtimestamp(time.time()+86400, timezone.utc)
    entries = [{'raceName': 'Future GP', 'date': tomorrow.date().isoformat(), 'time': tomorrow.strftime('%H:%M:%SZ'), 'Circuit': {'circuitName': 'Circuit', 'Location': {'country': 'Canada'}}},
               {'raceName': 'Missing start', 'date': tomorrow.date().isoformat()},
               {'raceName': 'Invalid season date', 'date': '9999-01-01', 'time': '12:00:00Z'},
               {'raceName': 'Bad timezone', 'date': tomorrow.date().isoformat(), 'time': '12:00:00'}]
    result = races({'MRData': {'RaceTable': {'Races': entries}}})
    assert len(result['races']) == 1
    service = WidgetFeeds()
    entry = {'data': result, 'fetchedAt': time.time(), 'failed': False}
    assert service.snapshot('f1', entry)['data']['race']['name'] == 'Future GP'
    assert 'lap' not in service.snapshot('f1', entry)['data']['race']
    result['races'][0]['start'] = time.time()-60
    assert service.snapshot('f1', entry)['data']['race'] is None


def test_single_flight_caching_failure_stale_expiry_and_shutdown():
    async def run():
        calls, clock = [], [0]
        def fetch(url):
            calls.append(url)
            return weather_fixture()
        service = WidgetFeeds(fetch, lambda: clock[0])
        assert calls == []
        replies = await asyncio.gather(*(service.get('weather', 43.7001, -79.4) for _ in range(10)))
        assert len(calls) == 1
        assert all(reply['status'] == 'ready' for reply in replies)
        assert calls[0].startswith('https://api.open-meteo.com/v1/forecast?')
        assert 'latitude=43.7' in calls[0]
        clock[0] = 901
        service.fetch = lambda url: (_ for _ in ()).throw(ValueError('Private provider detail'))
        stale = await service.get('weather', 43.7, -79.4)
        assert stale['status'] == 'stale'
        assert 'Private' not in json.dumps(stale)
        await service.get('weather', 43.7, -79.4)
        assert len(calls) == 1
        key = next(iter(service.cache))
        service.cache[key]['fetchedAt'] = time.time() - 3601
        assert (await service.get('weather', 43.7, -79.4))['status'] == 'unavailable'
        await service.close()
        assert not service.cache and not service.pending
        assert (await service.get('weather', 43.7, -79.4))['status'] == 'unavailable'
    asyncio.run(run())


def test_cache_and_global_request_rate_are_bounded():
    async def run():
        clock = [0]
        service = WidgetFeeds(lambda url: {'results': []}, lambda: clock[0])
        for i in range(40):
            clock[0] = i*61
            await service.get('locations', query=f'city{i}')
        assert len(service.cache) == 32
        for i in range(31):
            reply = await service.get('locations', query=f'new{i}')
        assert reply['status'] == 'unavailable'
        assert len(service.requests) == 30
        await service.close()
    asyncio.run(run())


def test_search_url_encodes_input_in_fixed_provider_query():
    async def run():
        calls = []
        service = WidgetFeeds(lambda url: calls.append(url) or {'results': []})
        await service.get('locations', query='Toronto&url=https://evil.example')
        assert calls[0].startswith('https://geocoding-api.open-meteo.com/v1/search?name=Toronto%26url%3Dhttps%3A%2F%2Fevil.example&')
        await service.close()
    asyncio.run(run())


def test_json_reader_caps_bytes_and_refuses_redirects():
    from email.message import Message
    from backend.widgets import NoRedirect
    with pytest.raises(ValueError):
        NoRedirect().redirect_request(None, None, 302, None, {}, 'http://127.0.0.1')
    response = io.BytesIO(b'x'*524289)
    response.headers = Message()
    response.headers['Content-Type'] = 'application/json'
    with patch('backend.widgets.build_opener') as opener:
        opener.return_value.open.return_value = response
        with pytest.raises(ValueError, match='too large'):
            read_json('https://api.open-meteo.com/v1/forecast')
        assert opener.return_value.open.call_args.kwargs['timeout'] == 6


def test_pending_limit_shared_waiter_cancellation_and_close():
    import threading
    async def run():
        release = threading.Event()
        def fetch(url):
            release.wait(2)
            return weather_fixture()
        service = WidgetFeeds(fetch)
        callers = [asyncio.create_task(service.get('weather', 40+i, -79)) for i in range(4)]
        await asyncio.sleep(.02)
        assert len(service.pending) == 4
        assert (await service.get('weather', 50, -79))['status'] == 'unavailable'
        shared = asyncio.create_task(service.get('weather', 40, -79))
        callers[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await callers[0]
        assert len(service.pending) == 4
        release.set()
        assert (await shared)['status'] == 'ready'
        await asyncio.gather(*callers[1:])
        await service.close()
        assert not service.pending and not service.cache
    asyncio.run(run())
