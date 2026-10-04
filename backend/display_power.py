"""Fixed display requests and a temporary awake lease, owned by one Windows thread."""
import ctypes
from ctypes import wintypes
from concurrent.futures import Future
import os
import queue
import threading
import time
from .monitor_power import MonitorPower

CONTINUOUS, SYSTEM, DISPLAY = 0x80000000, 1, 2


class DetailedReason(ctypes.Structure):
    _fields_ = [('module', wintypes.HMODULE), ('id', wintypes.ULONG),
                ('count', wintypes.ULONG), ('strings', ctypes.POINTER(wintypes.LPWSTR))]


class ReasonValue(ctypes.Union):
    _fields_ = [('detailed', DetailedReason), ('simple', wintypes.LPWSTR)]


class ReasonContext(ctypes.Structure):
    _fields_ = [('version', wintypes.ULONG), ('flags', wintypes.DWORD), ('reason', ReasonValue)]


class WindowsDisplay:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows display control unavailable')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        self.kernel.SetThreadExecutionState.restype = wintypes.DWORD
        self.kernel.PowerCreateRequest.argtypes = [ctypes.POINTER(ReasonContext)]
        self.kernel.PowerCreateRequest.restype = wintypes.HANDLE
        for name in ('PowerSetRequest', 'PowerClearRequest'):
            function = getattr(self.kernel, name)
            function.argtypes = [wintypes.HANDLE, ctypes.c_int]
            function.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.request = None
        self.monitors = MonitorPower()

    def hold(self, enabled):
        if enabled:
            if self.request is not None:
                return
            reason = ReasonContext(0, 1, ReasonValue(simple='G16 Rest mode or armed alarm keeps the dashboard available'))
            request = self.kernel.PowerCreateRequest(ctypes.byref(reason))
            if not request or request == ctypes.c_void_p(-1).value:
                raise OSError('Awake request failed')
            active = []
            try:
                # SystemRequired alone permits desktop-process suspension on Modern Standby.
                # ExecutionRequired keeps this process running with the display powered off.
                for kind in (0, 1, 3):
                    if not self.kernel.PowerSetRequest(request, kind):
                        raise OSError('Awake request failed')
                    active.append(kind)
                if not self.kernel.SetThreadExecutionState(CONTINUOUS | SYSTEM | DISPLAY):
                    raise OSError('Awake request failed')
                self.request = request
            except OSError:
                for kind in reversed(active):
                    self.kernel.PowerClearRequest(request, kind)
                self.kernel.CloseHandle(request)
                raise
        else:
            request, self.request = self.request, None
            if request is not None:
                for kind in (3, 1, 0):
                    self.kernel.PowerClearRequest(request, kind)
                self.kernel.CloseHandle(request)
            if not self.kernel.SetThreadExecutionState(CONTINUOUS):
                raise OSError('Awake request failed')

    def display(self, on, expires):
        self.monitors.display(on, expires)

    def probe(self):
        return len(self.monitors.inventory())

    def close(self):
        self.monitors.close()
        self.hold(False)


class DisplayPower:
    def __init__(self, factory=WindowsDisplay):
        self.factory = factory
        self.available = os.name == 'nt'
        self.jobs = queue.Queue(maxsize=16)
        self.lock = threading.Lock()
        self.thread = None
        self.held = False
        self.closed = False

    def _run(self):
        native = None
        try:
            native = self.factory()
            while True:
                action, value, future, expires = self.jobs.get()
                if action == 'close':
                    break
                if time.monotonic() > expires or future.cancelled():
                    continue
                try:
                    result = True
                    if action == 'hold':
                        if value != self.held:
                            native.hold(value)
                            self.held = value
                    elif action == 'probe':
                        result = native.probe()
                    else:
                        native.display(value, expires)
                    if not future.done():
                        future.set_result(result)
                except OSError:
                    if not future.done():
                        future.set_exception(OSError('Windows display request unavailable'))
        except OSError:
            # Queued calls time out instead of claiming control succeeded.
            pass
        finally:
            if native is not None:
                try:
                    native.close()
                except OSError:
                    pass
            self.held = False

    def _call(self, action, value, timeout=5):
        with self.lock:
            if self.closed:
                raise OSError('Display control stopped')
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, daemon=True, name='display-power')
                self.thread.start()
            future = Future()
            try:
                self.jobs.put_nowait((action, value, future, time.monotonic() + timeout))
            except queue.Full:
                raise OSError('Display control is busy') from None
        try:
            return future.result(timeout=timeout+.5)
        except TimeoutError:
            future.cancel()
            raise OSError('Display control did not respond') from None

    def hold(self, enabled):
        if enabled == self.held:
            return True
        return self._call('hold', enabled)

    def probe(self):
        return self._call('probe', None, timeout=20)

    def off(self):
        return self._call('display', False)

    def wake(self):
        return self._call('display', True)

    def close(self):
        with self.lock:
            self.closed = True
            while True:
                try:
                    _, _, future, _ = self.jobs.get_nowait()
                except queue.Empty:
                    break
                if future is not None and not future.done():
                    future.set_exception(OSError('Display control stopped'))
            if self.thread and self.thread.is_alive():
                try:
                    self.jobs.put_nowait(('close', None, None, 0))
                except queue.Full:
                    return
                self.thread.join(timeout=6)
