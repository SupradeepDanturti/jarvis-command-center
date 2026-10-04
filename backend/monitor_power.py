"""Fixed DDC/CI power values for attached monitors; never Windows system sleep."""
import ctypes
from ctypes import wintypes
import re
import time


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [('handle', wintypes.HANDLE), ('description', wintypes.WCHAR * 128)]


class MonitorPower:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.dx = ctypes.WinDLL('dxva2', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
            wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        self.user.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), self.callback_type, wintypes.LPARAM]
        self.user.EnumDisplayMonitors.restype = wintypes.BOOL
        signatures = {
            'GetNumberOfPhysicalMonitorsFromHMONITOR': [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)],
            'GetPhysicalMonitorsFromHMONITOR': [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PhysicalMonitor)],
            'GetCapabilitiesStringLength': [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)],
            'CapabilitiesRequestAndCapabilitiesReply': [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD],
            'GetVCPFeatureAndVCPFeatureReply': [wintypes.HANDLE, wintypes.BYTE, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)],
            'SetVCPFeature': [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD],
            'DestroyPhysicalMonitor': [wintypes.HANDLE],
        }
        for name, arguments in signatures.items():
            function = getattr(self.dx, name)
            function.argtypes, function.restype = arguments, wintypes.BOOL
        self.handles = []
        self.off_handles = []
        self.targets, self.prepared_at = [], 0

    @staticmethod
    def supports_power(capabilities):
        # Require an explicit power mode enumeration with On (01) and soft Off (04).
        match = re.search(r'(?i)(?<![0-9a-f])d6\s*\(\s*([0-9a-f\s]+)\)', capabilities)
        return bool(match and {'01', '04'} <= set(match[1].lower().split()))

    def discover(self):
        if self.off_handles:
            return
        self.close()
        logical = []
        callback = self.callback_type(lambda handle, _dc, _rect, _data: logical.append(handle) is None)
        if not self.user.EnumDisplayMonitors(None, None, callback, 0):
            raise OSError('Monitor discovery unavailable')
        for monitor in logical[:16]:
            count = wintypes.DWORD()
            if not self.dx.GetNumberOfPhysicalMonitorsFromHMONITOR(monitor, ctypes.byref(count)) or not 1 <= count.value <= 16:
                continue
            physical = (PhysicalMonitor * count.value)()
            if self.dx.GetPhysicalMonitorsFromHMONITOR(monitor, count, physical):
                self.handles.extend(item.handle for item in physical)

    def inventory(self):
        """Read-only capability probe, also used immediately before a requested power-off."""
        if self.off_handles:
            return list(self.off_handles)
        self.discover()
        supported = []
        for handle in self.handles:
            length, current = wintypes.DWORD(), wintypes.DWORD()
            if not self.dx.GetCapabilitiesStringLength(handle, ctypes.byref(length)) or not 1 <= length.value <= 16384:
                continue
            text = ctypes.create_string_buffer(length.value)
            if (self.dx.CapabilitiesRequestAndCapabilitiesReply(handle, text, length)
                and self.supports_power(text.value.decode('ascii', errors='ignore'))
                and self.dx.GetVCPFeatureAndVCPFeatureReply(handle, 0xd6, None, ctypes.byref(current), None)
                and current.value == 1):
                supported.append(handle)
        self.targets, self.prepared_at = supported, time.monotonic()
        return supported

    def display(self, on, expires):
        if on:
            failed = []
            for handle in self.off_handles:
                if not self.dx.SetVCPFeature(handle, 0xd6, 1):
                    failed.append(handle)
            self.off_handles = failed
            if failed:
                raise OSError('Monitor wake unavailable; use the monitor power button')
            return
        if self.off_handles:
            return
        # Slow dock capability reads belong to the separate, read-only prepare step.
        # Never start an off command after a browser timed out during discovery.
        targets = self.targets if time.monotonic()-self.prepared_at < 60 else []
        if not targets:
            raise OSError('No supported DDC/CI monitor')
        if time.monotonic() >= expires:
            raise OSError('Monitor request expired')
        for handle in targets:
            if time.monotonic() >= expires or not self.dx.SetVCPFeature(handle, 0xd6, 4):
                # Restore already-dispatched monitors on partial failure; retain failed handles.
                try:
                    self.display(True, expires)
                except OSError:
                    pass
                raise OSError('Monitor power-off unavailable')
            self.off_handles.append(handle)

    def close(self):
        # Shutdown requests restoration only for displays explicitly turned off by this object.
        try:
            self.display(True, float('inf'))
        except OSError:
            pass
        for handle in self.handles:
            self.dx.DestroyPhysicalMonitor(handle)
        self.handles, self.off_handles = [], []
        self.targets, self.prepared_at = [], 0
