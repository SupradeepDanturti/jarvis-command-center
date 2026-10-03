"""Local connection instructions for the desktop and Downloads; never served by HTTP."""
from datetime import datetime
import os
from pathlib import Path
import socket
import time

import psutil

FILE_NAME = 'G16 Command Center.txt'
HEADER = 'G16 COMMAND CENTER'


def connection_directories():
    import winreg
    home = Path.home()
    directories = []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
        for name, fallback in [('Desktop', home / 'Desktop'),
                               ('{374DE290-123F-4565-9164-39C4925E467B}', home / 'Downloads')]:
            try:
                value = winreg.QueryValueEx(key, name)[0]
                directories.append(Path(os.path.expandvars(value)))
            except OSError:
                directories.append(fallback)
    return list(dict.fromkeys(directories))


def network_addresses():
    stats = psutil.net_if_stats()
    addresses = []
    for adapter, entries in psutil.net_if_addrs().items():
        if adapter not in stats or not stats[adapter].isup:
            continue
        for entry in entries:
            if entry.family == socket.AF_INET and not entry.address.startswith(('127.', '169.254.')):
                addresses.append((adapter, entry.address))
    return sorted(addresses, key=lambda entry: ('wi-fi' not in entry[0].lower() and 'wifi' not in entry[0].lower(), entry[0]))


def connection_text(code, port, addresses, scheme='http', setup_port=None, fingerprint=None):
    lines = [HEADER, '', 'Connect your Redmi tablet to the same Wi-Fi as the laptop.', '',
             'TABLET ADDRESS:']
    lines.extend(f'{scheme}://{ip}:{port}  ({adapter})' for adapter, ip in addresses)
    if not addresses:
        lines.append('Waiting for Wi-Fi. This file updates automatically after connecting.')
    lines.extend(['', f'LAPTOP SETUP / RECOVERY CODE: {code}', '', f'Laptop address: {scheme}://localhost:{port}', '',
                  'The server runs silently after you sign into Windows.',
                  'Approve new browsers from System > Approved devices on the laptop.',
                  'Approved browsers reconnect without a code, including after server restarts.',
                  'For HTTPS on the Redmi, install G16 Dashboard CA.cer as a CA certificate once.',
                  'The recovery code changes on restart; approved devices stay approved for 180 days.',
                  'This file also updates when your network address changes.'])
    if setup_port is not None:
        lines += ['', 'TABLET CERTIFICATE DOWNLOAD (setup only, no dashboard controls):']
        lines += [f'http://{ip}:{setup_port}' for _, ip in addresses]
    if fingerprint:
        lines += ['', 'Verify the tablet CA certificate SHA-256 against this trusted laptop value:', fingerprint]
    return '\n'.join(lines) + '\n'


def write_connection_files(code, port, directories=None, addresses=None, scheme='http', setup_port=None, fingerprint=None):
    directories = connection_directories() if directories is None else directories
    addresses = network_addresses() if addresses is None else addresses
    text = connection_text(code, port, addresses, scheme, setup_port, fingerprint)
    results = []
    for directory in directories:
        destination = Path(directory) / FILE_NAME
        try:
            existing = destination.read_text(encoding='utf-8') if destination.exists() else ''
            if existing and not existing.startswith(HEADER + '\n'):
                raise FileExistsError('A different file already has this name; it was not replaced.')
            if existing.split('\nUpdated:')[0] == text:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix('.txt.tmp')
            temporary.write_text(text + '\nUpdated: ' + datetime.now().astimezone().isoformat(timespec='seconds') + '\n', encoding='utf-8')
            # Windows antivirus/indexing can briefly hold a newly written file.
            for attempt in range(6):
                try:
                    temporary.replace(destination)
                    break
                except OSError as error:
                    if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 5:
                        raise
                    time.sleep(0.05 * 2 ** attempt)
            results.append((destination, None))
        except OSError as error:
            results.append((destination, str(error)))
    return results
