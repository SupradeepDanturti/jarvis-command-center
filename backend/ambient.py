"""One trusted local scene catalog for the display and voice tools."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / 'config' / 'ambient-scenes.json'
ASSET_DIR = ROOT / 'frontend' / 'assets'
MEDIA_EXTENSIONS = {'video/webm': 'webm', 'video/mp4': 'mp4'}


def load_ambient_scenes():
    try:
        if CATALOG_PATH.stat().st_size > 65536:
            return {}
        catalog = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(catalog, dict) or len(catalog) > 32:
        return {}
    result = {}
    for identity, scene in catalog.items():
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', identity) or not isinstance(scene, dict):
            continue
        if set(scene) != {'name', 'description', 'file', 'type', 'credit'}:
            continue
        if any(not isinstance(value, str) for value in scene.values()):
            continue
        if (not 1 <= len(scene['name']) <= 80 or len(scene['description']) > 240 or len(scene['credit']) > 240
            or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,100}', scene['file'])
            or scene['type'] not in MEDIA_EXTENSIONS):
            continue
        assets = [ASSET_DIR / f"{scene['file']}.{extension}"
                  for extension in (MEDIA_EXTENSIONS[scene['type']], 'jpg')]
        if not all(asset.resolve().is_relative_to(ASSET_DIR.resolve()) and asset.is_file() for asset in assets):
            continue
        result[identity] = {**scene, 'number': f'{len(result) + 1:02} /'}
    return result


def ambient_options():
    # The agent receives IDs and descriptions, never media paths or a file-access capability.
    return [{'id': identity, 'name': scene['name'], 'description': scene['description']}
            for identity, scene in load_ambient_scenes().items()]


def ambient_script():
    return 'const ambientScenes=' + json.dumps(load_ambient_scenes()) + ';\n'
