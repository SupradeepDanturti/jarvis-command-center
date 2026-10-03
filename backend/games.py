"""Discover installed games from local launcher records; launch only registered IDs."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import quote

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['Steam', 'Epic Games', 'GOG', 'Riot Games', 'Custom']


def read_json(path):
    try:
        if path.stat().st_size > 2_000_000:
            return {}
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def read_vdf(path):
    try:
        if path.stat().st_size > 2_000_000:
            return {}
        tokens = re.findall(r'"((?:\\.|[^"\\])*)"|([{}])', path.read_text(encoding='utf-8-sig'))
        position = 0

        def block(depth=0):
            nonlocal position
            if depth > 32:
                raise ValueError('VDF too deeply nested')
            result = {}
            while position < len(tokens):
                key, symbol = tokens[position]
                position += 1
                if symbol == '}':
                    return result
                if symbol or position >= len(tokens):
                    raise ValueError('Invalid VDF')
                value, symbol = tokens[position]
                position += 1
                result[key.lower()] = block(depth+1) if symbol == '{' else value.replace('\\\\', '\\').replace('\\"', '"')
            return result

        return block()
    except (OSError, ValueError):
        return {}


def registry_records(key_path):
    if os.name != 'nt':
        return []
    import winreg
    results = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                    values = {}
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        name, value, _ = winreg.EnumValue(key, i)
                        values[name.lower()] = value
                    if values:
                        results.append(values)
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as child:
                            values = {}
                            for j in range(winreg.QueryInfoKey(child)[1]):
                                name, value, _ = winreg.EnumValue(child, j)
                                values[name.lower()] = value
                            if values:
                                results.append(values)
            except OSError:
                continue
    return results


def default_steam_roots():
    roots = {record.get('steampath') or record.get('installpath') for record in registry_records(r'Software\Valve\Steam')}
    for folder in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
        if os.environ.get(folder):
            roots.add(str(Path(os.environ[folder]) / 'Steam'))
    return [Path(value) for value in roots if value]


class GameLibrary:
    def __init__(self, steam_roots=None, epic_dir=None, riot_dir=None, gog_records=None, custom_file=None):
        self.steam_roots = steam_roots
        data = Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData'))
        self.epic_dir = epic_dir or data / 'Epic/EpicGamesLauncher/Data/Manifests'
        self.riot_dir = riot_dir or data / 'Riot Games'
        self.gog_records = gog_records
        self.custom_file = custom_file or ROOT / 'config/games.local.json'
        self.records = {}
        self.scanned = 0
        self.lock = threading.RLock()
        self.warnings = []

    def add(self, launcher, key, name, folder, target, args=None, art_roots=None):
        folder = Path(folder)
        if not folder.is_dir() or not name or not target:
            return
        if not target.startswith(('steam://rungameid/', 'com.epicgames.launcher://apps/')):
            if Path(target).suffix.lower() != '.exe' or not Path(target).is_file():
                return
            if Path(target).name.lower() in {'cmd.exe', 'powershell.exe', 'pwsh.exe', 'wscript.exe', 'cscript.exe', 'mshta.exe'}:
                return
        game_id = launcher.lower().split()[0] + '-' + hashlib.sha256(str(key).encode()).hexdigest()[:16]
        artwork = None
        for root in art_roots or []:
            for suffix in (f'{key}_library_600x900.jpg', f'{key}_header.jpg', f'{key}/library_600x900.jpg'):
                candidate = root / 'appcache/librarycache' / suffix
                if candidate.is_file():
                    artwork = candidate
                    break
            if artwork:
                break
        self.records[game_id] = {'id': game_id, 'name': str(name), 'launcher': launcher,
                                'folder': folder, 'target': target, 'args': args or [], 'artwork': artwork}

    def steam(self):
        roots = self.steam_roots if self.steam_roots is not None else default_steam_roots()
        libraries = set(roots)
        for root in roots:
            for location in ('steamapps/libraryfolders.vdf', 'config/libraryfolders.vdf'):
                for key, value in read_vdf(root / location).get('libraryfolders', {}).items():
                    if key.isdigit():
                        path = value.get('path') if isinstance(value, dict) else value
                        if path:
                            libraries.add(Path(path))
        for library in libraries:
            common = (library / 'steamapps/common').resolve()
            for file in (library / 'steamapps').glob('appmanifest_*.acf'):
                app = read_vdf(file).get('appstate', {})
                app_id, name = app.get('appid', ''), app.get('name', '')
                if not app_id.isdigit() or app_id == '228980' or 'redistributable' in name.lower():
                    continue
                try:
                    if not int(app.get('stateflags', '0')) & 4:
                        continue
                except ValueError:
                    continue
                folder = (common / app.get('installdir', '')).resolve()
                if folder == common or not folder.is_relative_to(common):
                    continue
                self.add('Steam', app_id, name, folder, f'steam://rungameid/{app_id}', art_roots=roots)

    def epic(self):
        for file in self.epic_dir.glob('*.item'):
            app = read_json(file)
            if not isinstance(app, dict):
                continue
            app_id, name = app.get('AppName', ''), app.get('DisplayName', '')
            if not app_id or app.get('bIsIncompleteInstall') or app_id.startswith(('UE_', 'FabPlugin_', 'QuixelBridge_')):
                continue
            if name.lower() in {'unreal engine', 'quixel bridge', 'fab ue plugin'}:
                continue
            identifiers = [app.get('CatalogNamespace'), app.get('CatalogItemId'), app_id]
            key = ':'.join(identifiers) if all(identifiers) else app_id
            target = f'com.epicgames.launcher://apps/{quote(key, safe="")}?action=launch&silent=true'
            folder = app.get('InstallLocation')
            if folder:
                self.add('Epic Games', key, name, folder, target)

    def gog(self):
        records = self.gog_records if self.gog_records is not None else registry_records(r'SOFTWARE\GOG.com\Games')
        for app in records:
            folder = app.get('path')
            exe = app.get('exe')
            if not folder or not exe:
                continue
            target = Path(exe) if Path(exe).is_absolute() else Path(folder) / exe
            self.add('GOG', app.get('gameid', str(target)), app.get('gamename', ''), folder, str(target))

    def riot(self):
        clients = read_json(self.riot_dir / 'RiotClientInstalls.json')
        if not isinstance(clients, dict):
            return
        client = clients.get('rc_default') or clients.get('rc_live')
        if not client or not Path(client).is_file():
            return
        products = {'valorant': ('VALORANT', 'VALORANT.exe'), 'league_of_legends': ('League of Legends', 'LeagueClient.exe')}
        for product, (name, executable) in products.items():
            for patchline in ('live', 'pbe'):
                file = self.riot_dir / f'Metadata/{product}.{patchline}/{product}.{patchline}.product_settings.yaml'
                try:
                    text = file.read_text(encoding='utf-8')
                    match = re.search(r'^product_install_full_path:\s*["\']?([^\r\n"\']+)', text, re.M)
                    if not match:
                        continue
                    folder = Path(match.group(1).strip())
                    installed = folder / ('VALORANT.exe' if product == 'valorant' else executable)
                    if not installed.is_file():
                        continue
                    self.add('Riot Games', product+patchline, name+(' PBE' if patchline == 'pbe' else ''), folder, client,
                             [f'--launch-product={product}', f'--launch-patchline={patchline}'])
                except OSError:
                    continue

    def custom(self):
        entries = read_json(self.custom_file)
        if not isinstance(entries, list):
            return
        for app in entries:
            if isinstance(app, dict) and app.get('target'):
                target = Path(app['target'])
                self.add('Custom', str(target), app.get('name', target.stem), target.parent, str(target), app.get('args', []))

    def scan(self, force=False):
        with self.lock:
            if not force and self.scanned and time.time() - self.scanned < 60:
                return
            self.records = {}
            self.warnings = []
            for label, scanner in [('Steam', self.steam), ('Epic Games', self.epic), ('GOG', self.gog), ('Riot Games', self.riot), ('Custom', self.custom)]:
                try:
                    scanner()
                except (OSError, ValueError, TypeError, AttributeError):
                    self.warnings.append(f'{label} records could not be fully read.')
            self.scanned = time.time()

    def catalog(self, force=False):
        with self.lock:
            self.scan(force)
            games = [{'id': game['id'], 'name': game['name'], 'launcher': game['launcher'],
                      'artwork': f'/api/games/{game["id"]}/artwork' if game['artwork'] else None}
                     for game in sorted(self.records.values(), key=lambda g: g['name'].casefold())]
            return {'games': games, 'sources': SOURCES, 'scanned_at': self.scanned, 'warnings': self.warnings,
                    'note': 'Installed Steam, Epic, GOG and Riot games are detected. Other games can be registered on the laptop.'}

    def launch(self, game_id):
        with self.lock:
            self.scan()
            game = self.records.get(game_id)
            if not game:
                raise HTTPException(404, 'This game is not in the installed library. Refresh the library.')
            if os.name != 'nt':
                raise HTTPException(501, 'Game launching requires Windows.')
            if not game['folder'].is_dir():
                raise HTTPException(409, 'This game is no longer installed. Refresh the library.')
            try:
                if game['target'].startswith(('steam://rungameid/', 'com.epicgames.launcher://apps/')):
                    os.startfile(game['target'])
                else:
                    if not Path(game['target']).is_file():
                        raise FileNotFoundError
                    subprocess.Popen([game['target'], *game['args']], cwd=str(Path(game['target']).parent), shell=False)
            except OSError:
                raise HTTPException(409, 'The game could not be opened. Check its launcher on the laptop.')
            return {'ok': True, 'message': f'Opening {game["name"]}'}

    def artwork(self, game_id):
        with self.lock:
            self.scan()
            game = self.records.get(game_id)
            if not game or not game['artwork'] or not game['artwork'].is_file():
                raise HTTPException(404, 'No local artwork for this game.')
            return game['artwork']
