"""Read installed app icons locally; no browser-provided file paths or remote fetches."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import zlib


def png_chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def desktop_icon(target):
    class FileInfo(ctypes.Structure):
        _fields_ = [('icon', wintypes.HANDLE), ('index', ctypes.c_int), ('attributes', wintypes.DWORD),
                    ('display', wintypes.WCHAR*260), ('type', wintypes.WCHAR*80)]

    class BitmapHeader(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                    ('imageSize', wintypes.DWORD), ('x', wintypes.LONG), ('y', wintypes.LONG),
                    ('colors', wintypes.DWORD), ('important', wintypes.DWORD)]

    shell, user, gdi = ctypes.WinDLL('shell32'), ctypes.WinDLL('user32'), ctypes.WinDLL('gdi32')
    shell.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(FileInfo), wintypes.UINT, wintypes.UINT]
    shell.SHGetFileInfoW.restype = ctypes.c_size_t
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]; gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]; gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]; gdi.DeleteDC.argtypes = [wintypes.HDC]
    user.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
    user.DestroyIcon.argtypes = [wintypes.HICON]
    info = FileInfo()
    if not shell.SHGetFileInfoW(str(target), 0, ctypes.byref(info), ctypes.sizeof(info), 0x100) or not info.icon:
        return None
    dc = bitmap = previous = None
    try:
        dc = gdi.CreateCompatibleDC(None)
        header = BitmapHeader(ctypes.sizeof(BitmapHeader), 64, -64, 1, 32, 0, 64*64*4, 0, 0, 0, 0)
        pixels = ctypes.c_void_p()
        bitmap = gdi.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(pixels), None, 0)
        if not dc or not bitmap or not pixels.value:
            return None
        previous = gdi.SelectObject(dc, bitmap)
        if not user.DrawIconEx(dc, 0, 0, info.icon, 64, 64, 0, None, 3):
            return None
        data = ctypes.string_at(pixels, 64*64*4)
        rows = bytearray()
        for y in range(64):
            rows.append(0)
            for x in range(64):
                b, g, r, a = data[(y*64+x)*4:(y*64+x)*4+4]
                # Shell icons use premultiplied BGRA; PNG stores straight RGBA.
                if 0 < a < 255:
                    r, g, b = [min(255, round(c*255/a)) for c in (r, g, b)]
                rows.extend((r, g, b, a))
        return b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 6, 0, 0, 0)) + png_chunk(b'IDAT', zlib.compress(rows)) + png_chunk(b'IEND', b'')
    finally:
        if previous and dc: gdi.SelectObject(dc, previous)
        if bitmap: gdi.DeleteObject(bitmap)
        if dc: gdi.DeleteDC(dc)
        user.DestroyIcon(info.icon)


def installed_icon(app):
    if app.get('kind') == 'packaged':
        root = Path(app.get('packageRoot', '')).resolve()
        path = Path(app.get('logo') or '').resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != '.png' or not path.is_file() or path.stat().st_size > 512_000:
            return None
        data = path.read_bytes()
        if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
            return None
        width, height = struct.unpack('>II', data[16:24])
        return data if 0 < width <= 1024 and 0 < height <= 1024 else None
    return desktop_icon(app['target'])
