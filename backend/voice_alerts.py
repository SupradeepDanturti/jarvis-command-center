"""Local, bounded hardware warnings. Never sends telemetry to a cloud model."""
from datetime import datetime
import math
import json
from pathlib import Path
import time


class HardwareAlerts:
    LIMITS = {'cpu': 90, 'memory': 90, 'gpu': 70}
    COOLDOWN = 3600

    def __init__(self, path=None):
        self.streak = {name: 0 for name in self.LIMITS}
        self.path = Path(path) if path else None
        self.last_alert_wall = None
        if self.path and self.path.exists():
            try:
                value = json.loads(self.path.read_text(encoding='utf-8')).get('lastAlert')
                if type(value) in {int, float} and math.isfinite(value) and value >= 0:
                    self.last_alert_wall = value
            except (OSError, ValueError):
                pass
        self.last_sample = None

    def evaluate(self, snapshot, wall=None):
        wall = time.time() if wall is None else wall
        if not isinstance(snapshot, dict):
            return None
        stamp = snapshot.get('timestamp')
        try:
            sample_time = datetime.fromisoformat(stamp).timestamp()
        except (TypeError, ValueError):
            return None
        if not 0 <= wall - sample_time <= 5:
            self.streak = dict.fromkeys(self.LIMITS, 0)
            return None
        if stamp == self.last_sample:
            return None
        self.last_sample = stamp
        values = {'cpu': (snapshot.get('cpu') or {}).get('usage'),
                  'memory': (snapshot.get('memory') or {}).get('percent'),
                  'gpu': (snapshot.get('gpu') or {}).get('temperature')}
        warnings = []
        cooling = self.last_alert_wall is not None and wall - self.last_alert_wall < self.COOLDOWN
        for name, limit in self.LIMITS.items():
            value = values[name]
            if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= (200 if name == 'gpu' else 100):
                self.streak[name] = 0
                continue
            self.streak[name] = self.streak[name] + 1 if value >= limit else 0
            if self.streak[name] >= 3 and not cooling:
                label = {'cpu': 'processor load', 'memory': 'memory usage', 'gpu': 'GPU temperature'}[name]
                unit = 'degrees Celsius' if name == 'gpu' else 'percent'
                warnings.append(f'{label} is at {round(value)} {unit}')
        if warnings:
            self.last_alert_wall = wall
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'lastAlert': wall}), encoding='utf-8')
                temporary.replace(self.path)
            return 'Sir, ' + '. '.join(warnings) + '. Please keep an eye on it.'
