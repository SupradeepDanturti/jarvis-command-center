"""One shared sampler for all clients; missing sensor values remain null."""
import asyncio
from collections import deque
import csv
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time

import psutil


class Telemetry:
    def __init__(self):
        self.latest = None
        self.history = deque(maxlen=3600)
        self.previous = None
        self.gpu = None
        self.gpu_checked = 0
        self.nvidia = shutil.which("nvidia-smi")
        self.errors = []
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

    def gpu_sample(self):
        if not self.nvidia:
            return None
        try:
            result = subprocess.run([
                self.nvidia, "--query-gpu=name,temperature.gpu,utilization.gpu,clocks.gr,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, check=True)
            row = next(csv.reader(io.StringIO(result.stdout)))
            def number(index):
                try:
                    return float(row[index].strip())
                except ValueError:
                    return None
            return {"name": row[0].strip(), "temperature": number(1), "usage": number(2),
                    "clock": number(3), "memory_used": number(4), "memory_total": number(5),
                    "power": number(6), "source": "nvidia-smi"}
        except (OSError, subprocess.SubprocessError, StopIteration, IndexError):
            return None

    def sample(self):
        now = time.monotonic()
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()
        down = up = read = write = 0
        if self.previous:
            old_time, old_net, old_disk = self.previous
            elapsed = max(now - old_time, 0.01)
            down = max(0, net.bytes_recv - old_net.bytes_recv) / elapsed
            up = max(0, net.bytes_sent - old_net.bytes_sent) / elapsed
            if disk and old_disk:
                read = max(0, disk.read_bytes - old_disk.read_bytes) / elapsed
                write = max(0, disk.write_bytes - old_disk.write_bytes) / elapsed
        self.previous = now, net, disk
        if now - self.gpu_checked >= 2:
            self.gpu = self.gpu_sample()
            self.gpu_checked = now
        memory = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        frequency = psutil.cpu_freq()
        partitions = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partitions.append({"name": partition.device, "total": usage.total,
                                   "used": usage.used, "free": usage.free, "percent": usage.percent})
            except OSError:
                continue
        ips = []
        for adapter, addresses in psutil.net_if_addrs().items():
            for address in addresses:
                if address.family == socket.AF_INET and not address.address.startswith("127."):
                    ips.append({"adapter": adapter, "ip": address.address})
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "source": "live",
                "cpu": {"usage": psutil.cpu_percent(interval=None),
                        "cores": psutil.cpu_percent(interval=None, percpu=True),
                        "clock": frequency.current if frequency else None,
                        "temperature": None, "power": None},
                "gpu": self.gpu,
                "memory": {"used": memory.used, "total": memory.total, "percent": memory.percent},
                "storage": {"drives": partitions, "read": read, "write": write, "temperature": None},
                "network": {"download": down, "upload": up, "addresses": ips},
                "battery": {"percent": battery.percent, "charging": battery.power_plugged} if battery else None,
                "system": {"hostname": socket.gethostname(), "os": platform.platform(),
                           "uptime": time.time() - psutil.boot_time(), "logical_cores": psutil.cpu_count()},
                "fps": None, "fans": None,
                "integrations": {"windows": "connected", "nvidia": "connected" if self.gpu else "unavailable",
                                 "hwinfo": "not configured", "rtss": "not configured", "obs": "not configured"}}

    async def run(self):
        while True:
            try:
                self.latest = await asyncio.to_thread(self.sample)
                self.history.append(self.latest)
                self.errors = []
            except Exception:
                # Keep the sampler alive and stop serving outdated values as live.
                self.errors = ["Telemetry temporarily unavailable"]
                self.latest = None
            await asyncio.sleep(1)
