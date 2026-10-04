"""Optional read-only HWiNFO v1 shared-memory adapter. No hardware driver/writes."""
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import struct
import threading
import time

from fastapi import HTTPException

# Packed public HWiNFO SM2 header/record prefixes. Extended records retain these prefixes.
HEADER = struct.Struct('<IIIqIIIIII')
MAX_BYTES, MAX_SENSORS, MAX_READINGS = 8 * 1024 * 1024, 256, 4096


def layout(data):
    if len(data) < HEADER.size:
        raise ValueError('Incomplete sensor header')
    signature, version, revision, stamp, so, ss, sn, ro, rs, rn = HEADER.unpack_from(data)
    minimum = 48 if revision >= 1 else 44
    if signature != 0x53695748:
        raise ValueError('Sensor source stopped')
    if version != 1 or revision not in {0, 1, 2}:
        raise ValueError('Unsupported sensor format')
    if not (264 <= ss <= 4096 and 316 <= rs <= 4096 and sn <= MAX_SENSORS and rn <= MAX_READINGS):
        raise ValueError('Invalid sensor sizes')
    end_s, end_r = so + ss * sn, ro + rs * rn
    if so < minimum or ro < end_s or max(end_s, end_r) > MAX_BYTES:
        raise ValueError('Invalid sensor offsets')
    return stamp, so, ss, sn, ro, rs, rn, max(end_s, end_r, minimum)


def text(data):
    raw = data.split(b'\0', 1)[0]
    try:
        value = raw.decode('utf-8')
    except UnicodeDecodeError:
        value = raw.decode('cp1252', errors='replace')
    return ''.join(c for c in value if c.isprintable())[:128]


def parse_memory(data, wall=None):
    stamp, so, ss, sn, ro, rs, rn, length = layout(data)
    if len(data) < length:
        raise ValueError('Incomplete sensor data')
    wall = time.time() if wall is None else wall
    if not 0 <= wall - stamp <= 5:
        raise ValueError('Sensor readings are stale')
    sensors = []
    for index in range(sn):
        record = data[so + ss * index:so + ss * index + ss]
        sid, instance = struct.unpack_from('<II', record)
        sensors.append((sid, instance, text(record[8:136])))
    readings, seen = [], set()
    for index in range(rn):
        record = data[ro + rs * index:ro + rs * index + rs]
        kind, sensor_index, rid = struct.unpack_from('<III', record)
        if sensor_index >= len(sensors):
            raise ValueError('Invalid sensor reference')
        sid, instance, sensor = sensors[sensor_index]
        identity = f'{sid:08x}-{instance:08x}-{rid:08x}'
        if identity in seen:
            raise ValueError('Duplicate sensor identity')
        seen.add(identity)
        unit, value = text(record[268:284]), struct.unpack_from('<d', record, 284)[0]
        if not math.isfinite(value):
            continue
        label = text(record[12:140])
        reading_type = None
        if kind == 1 and unit in {'°C', 'C', '°F', 'F'} and -50 <= value <= 350:
            if unit in {'°F', 'F'}:
                value = (value - 32) * 5 / 9
            unit, reading_type = '°C', 'temperature'
        elif kind == 3 and unit.upper() == 'RPM' and 0 <= value <= 30000:
            unit, reading_type = 'RPM', 'fan'
        elif kind == 8 and value in {0., 1.} and (unit == 'Yes/No' or 'throttling' in label.lower()):
            value, unit, reading_type = bool(value), 'Yes/No', 'flag'
        if reading_type:
            readings.append({'id': identity, 'sensor': sensor, 'label': label, 'value': value,
                             'unit': unit, 'kind': reading_type, 'source': 'HWiNFO', 'sampledAt': stamp * 1000})
    return readings


def read_memory():
    if os.name != 'nt':
        raise ValueError('HWiNFO requires Windows')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenFileMappingW.restype = wintypes.HANDLE
    kernel.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    kernel.MapViewOfFile.restype = ctypes.c_void_p
    kernel.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenFileMappingW(4, False, 'Global\\HWiNFO_SENS_SM2')
    if not handle:
        raise ValueError('Open HWiNFO Sensors and enable shared memory')
    mutex, view, acquired = None, None, False
    try:
        mutex = kernel.OpenMutexW(0x100001, False, 'Global\\HWiNFO_SM2_MUTEX')
        if not mutex or kernel.WaitForSingleObject(mutex, 50) not in {0, 0x80}:
            raise ValueError('Sensor source is busy or unavailable')
        acquired = True
        view = kernel.MapViewOfFile(handle, 4, 0, 0, HEADER.size)
        if not view:
            raise ValueError('Cannot read sensor header')
        header = ctypes.string_at(view, HEADER.size)
        length = layout(header)[-1]
        kernel.UnmapViewOfFile(view)
        view = kernel.MapViewOfFile(handle, 4, 0, 0, length)
        if not view:
            raise ValueError('Incomplete sensor mapping')
        data = ctypes.string_at(view, length)
        if data[:HEADER.size] != header:
            raise ValueError('Sensor source changed while reading')
        return data
    finally:
        if view:
            kernel.UnmapViewOfFile(view)
        if acquired:
            kernel.ReleaseMutex(mutex)
        if mutex:
            kernel.CloseHandle(mutex)
        kernel.CloseHandle(handle)


class ThermalMonitor:
    def __init__(self, path=None, reader=read_memory):
        self.path = Path(path) if path else None
        self.reader = reader
        self.lock = threading.RLock()
        self.settings = {'enabled': False, 'cpuTemperature': None, 'cpuThrottle': None,
                         'gpuThrottle': None, 'fans': [], 'drives': []}
        self.inventory = []
        self.reason = 'Extra sensors off'
        if self.path and self.path.is_file():
            try:
                if self.path.stat().st_size <= 16384:
                    self.settings = self.validate(json.loads(self.path.read_text(encoding='utf-8')))
            except (OSError, ValueError, TypeError):
                pass

    @staticmethod
    def validate(settings):
        if not isinstance(settings, dict) or set(settings) != {'enabled', 'cpuTemperature', 'cpuThrottle', 'gpuThrottle', 'fans', 'drives'}:
            raise ValueError('Invalid sensor settings')
        import re
        valid_id = lambda value: isinstance(value, str) and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}', value)
        if type(settings['enabled']) is not bool:
            raise ValueError('Invalid sensor settings')
        if any(settings[k] is not None and not valid_id(settings[k]) for k in ('cpuTemperature', 'cpuThrottle', 'gpuThrottle')):
            raise ValueError('Invalid sensor identity')
        for key in ('fans', 'drives'):
            values = settings[key]
            if not isinstance(values, list) or len(values) > 16 or not all(valid_id(v) for v in values) or len(set(values)) != len(values):
                raise ValueError('Invalid sensor list')
        return {**settings, 'fans': list(settings['fans']), 'drives': list(settings['drives'])}

    def configure(self, settings):
        settings = self.validate(settings)
        with self.lock:
            by_id = {r['id']: r for r in self.inventory if time.time() * 1000 - r['sampledAt'] <= 5000}
            for key, kind in [('cpuTemperature', 'temperature'), ('cpuThrottle', 'flag'), ('gpuThrottle', 'flag'),
                              ('fans', 'fan'), ('drives', 'temperature')]:
                ids = settings[key] if isinstance(settings[key], list) else [settings[key]]
                for identity in ids:
                    previous = self.settings[key] if isinstance(self.settings[key], list) else [self.settings[key]]
                    if settings['enabled'] and identity and identity not in previous and (identity not in by_id or by_id[identity]['kind'] != kind):
                        raise HTTPException(409, 'Choose a current sensor with the correct unit.')
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temp = self.path.with_suffix('.tmp')
                temp.write_text(json.dumps(settings), encoding='utf-8')
                temp.replace(self.path)
            self.settings = settings
            if not settings['enabled']:
                self.inventory = []
            return self.snapshot()

    def sample(self):
        with self.lock:
            if not self.settings['enabled']:
                self.inventory, self.reason = [], 'Extra sensors off'
            else:
                try:
                    self.inventory = parse_memory(self.reader())
                    self.reason = 'Connected' if self.inventory else 'No supported sensors reported'
                except (OSError, ValueError, struct.error):
                    self.inventory = []
                    self.reason = 'Sensor source unavailable. Check HWiNFO Sensors and shared memory.'
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            current = {r['id']: r for r in self.inventory if 0 <= time.time() * 1000 - r['sampledAt'] <= 5000}
            def reading(key):
                value = current.get(self.settings[key])
                kind = 'temperature' if key == 'cpuTemperature' else 'flag'
                return value if value and value['kind'] == kind else None
            return {'enabled': self.settings['enabled'], 'available': bool(current), 'reason': self.reason,
                    'cpuTemperature': reading('cpuTemperature'), 'cpuThrottle': reading('cpuThrottle'),
                    'gpuThrottle': reading('gpuThrottle'),
                    'fans': [current[i] for i in self.settings['fans'] if i in current and current[i]['kind'] == 'fan'],
                    'drives': [current[i] for i in self.settings['drives'] if i in current and current[i]['kind'] == 'temperature']}

    def discovery(self):
        with self.lock:
            return {'settings': dict(self.settings), 'readings': list(self.inventory), **self.snapshot()}
