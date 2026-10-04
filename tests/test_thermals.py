from pathlib import Path
import struct
import time

import pytest

from backend.activity import match_game
from backend.thermals import HEADER, ThermalMonitor, parse_memory


def memory(readings=None, stamp=None):
    readings = readings or [(1, 1, 'CPU Package', '°C', 62), (3, 2, 'CPU Fan', 'RPM', 2100),
                            (8, 3, 'Core Thermal Throttling', 'Yes/No', 0)]
    sensor = struct.pack('<II', 123, 0)+b'CPU sensor'.ljust(128,b'\0')+b'CPU sensor'.ljust(128,b'\0')
    out = HEADER.pack(0x53695748, 1, 1, int(time.time()) if stamp is None else stamp, 48, 264, 1, 312, 316, len(readings))+struct.pack('<I', 2000)+sensor
    for kind, identity, label, unit, value in readings:
        out += struct.pack('<III', kind, 0, identity)+label.encode('cp1252').ljust(128,b'\0')+label.encode('cp1252').ljust(128,b'\0')+unit.encode('cp1252').ljust(16,b'\0')+struct.pack('<dddd', value, 0, 0, 0)
    return out


def test_parse_values_flags_and_fahrenheit():
    values = parse_memory(memory())
    assert [r['value'] for r in values] == [62, 2100, False]
    assert values[0]['id'] == '0000007b-00000000-00000001'
    assert parse_memory(memory([(1, 1, 'SSD', 'F', 104)]))[0]['value'] == 40
    assert parse_memory(memory([(1, 1, 'Temperature', 'mV', 62)])) == []
    assert parse_memory(memory([(1, 1, 'Temperature', 'C', float('nan'))])) == []


@pytest.mark.parametrize('offset,value', [(0,0), (4,99), (8,99), (20,0), (24,1), (28,300), (32,1), (36,1), (40,5000)])
def test_malformed_headers_fail_closed(offset, value):
    data = bytearray(memory())
    struct.pack_into('<I', data, offset, value)
    with pytest.raises(ValueError):
        parse_memory(data)


def test_truncated_stale_duplicate_and_invalid_sensor_reference():
    for data in [memory()[:50], memory(stamp=int(time.time())-30), memory([(1,1,'One','C',42),(1,1,'Two','C',43)])]:
        with pytest.raises(ValueError):
            parse_memory(data)
    data = bytearray(memory())
    struct.pack_into('<I', data, 312+4, 20)
    with pytest.raises(ValueError):
        parse_memory(data)


def test_mapping_is_explicit_persistent_and_stopped_provider_clears_values(tmp_path):
    path = tmp_path/'thermal.json'
    monitor = ThermalMonitor(path, reader=memory)
    assert monitor.sample()['cpuTemperature'] is None
    monitor.configure({**monitor.settings, 'enabled': True})
    assert monitor.sample()['cpuTemperature'] is None
    readings = monitor.inventory
    monitor.configure({**monitor.settings,'cpuTemperature':readings[0]['id'],'cpuThrottle':readings[2]['id'],'fans':[readings[1]['id']]})
    assert monitor.snapshot()['cpuTemperature']['value'] == 62
    assert monitor.snapshot()['cpuThrottle']['value'] is False
    restored = ThermalMonitor(path, reader=memory)
    assert restored.sample()['fans'][0]['value'] == 2100
    restored.reader = lambda: memory(stamp=int(time.time())-20)
    assert restored.sample()['cpuTemperature'] is None
    assert not restored.snapshot()['available']


def test_game_match_requires_trusted_directory_and_rejects_helpers(tmp_path):
    folder = tmp_path/'Game'
    folder.mkdir()
    game = {'id':'game-one','name':'Game One','folder':folder,'target':'steam://rungameid/123','launcher':'Steam'}
    assert match_game(folder/'bin/game.exe',[game]) == {'id':'game-one','name':'Game One'}
    assert match_game(tmp_path/'GameOther/game.exe',[game]) is None
    assert match_game(folder/'CrashReportClient.exe',[game]) is None
    assert match_game(folder/'launcher.exe',[game]) is None
    assert match_game(folder/'game.exe',[game,{**game,'id':'game-two'}]) is None
