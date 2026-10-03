"""Latest browser display sizes, kept briefly in memory for layout diagnostics."""
import threading
import time


class DisplayReports:
    def __init__(self, retention=300, capacity=128):
        self.retention = retention
        self.capacity = capacity
        self.reports = {}
        self.lock = threading.RLock()

    def _prune(self):
        cutoff = time.time() - self.retention
        self.reports = {key: value for key, value in self.reports.items()
                        if value['reported_at'] > cutoff}

    def record(self, device_id, details):
        with self.lock:
            self._prune()
            if device_id not in self.reports and len(self.reports) >= self.capacity:
                oldest = min(self.reports, key=lambda key: self.reports[key]['reported_at'])
                del self.reports[oldest]
            self.reports[device_id] = {**details, 'reported_at': time.time()}

    def get(self, device_id):
        with self.lock:
            self._prune()
            report = self.reports.get(device_id)
            return dict(report) if report else None

    def remove(self, device_id):
        with self.lock:
            self.reports.pop(device_id, None)
