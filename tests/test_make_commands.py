"""Exercise the Windows command workflow without pip downloads or real PC controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows workflow')
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def command_project(tmp_path):
    root = tmp_path / 'project with spaces'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / 'Makefile', root / 'Makefile')
    shutil.copyfile(ROOT / 'scripts/make.ps1', scripts / 'make.ps1')
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(root / '.venv')], check=True)
    # Only this fixture's Python process sees these fake modules.
    (root / 'pip.py').write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        "p = Path('calls.jsonl')\n"
        "with p.open('a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(int(os.environ.get('QA_PIP_EXIT', '0')))\n", encoding='utf-8')
    (scripts / 'install-voice.py').write_text("from pathlib import Path\nPath('models-called').touch()\n", encoding='utf-8')
    stub = "param([switch]$Lan,[int]$Port,[switch]$NoJarvis,[switch]$NoAssistant)\n@{Lan=[bool]$Lan;Port=$Port;NoJarvis=[bool]$NoJarvis;NoAssistant=[bool]$NoAssistant} | ConvertTo-Json | Set-Content 'options.json'\n"
    for name in ('start', 'install-startup'):
        (scripts / f'{name}.ps1').write_text(stub, encoding='utf-8')
    return root


def command(root, target, *options, env=None):
    make = os.environ.get('G16_MAKE_PATH')
    if make:
        args = [make, target, *options]
    else:
        args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/make.ps1', '-Target', target]
        for option in options:
            key, value = option.split('=', 1)
            args += ['-' + key, value]
    return subprocess.run(args, cwd=root, env={**os.environ, **(env or {})}, capture_output=True, text=True)


def test_install_reuses_environment_and_includes_voice_by_default(command_project):
    root = command_project
    marker = root / '.venv/keep-existing'
    marker.touch()
    result = command(root, 'install')
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
    assert calls == [['install', '-r', 'requirements.txt'], ['install', '-r', 'requirements-voice.txt']]
    assert (root / 'models-called').exists()
    assert marker.exists()


def test_dashboard_only_install_and_native_failure_stop_followup(command_project):
    root = command_project
    result = command(root, 'install', 'JARVIS=0')
    assert result.returncode == 0, result.stderr
    assert not (root / 'models-called').exists()
    result = command(root, 'install', env={'QA_PIP_EXIT': '7'})
    assert result.returncode != 0
    calls = (root / 'calls.jsonl').read_text().splitlines()
    assert len(calls) == 2  # One base install per invocation; failure never installs voice.
    assert not (root / 'models-called').exists()


@pytest.mark.parametrize('target', ['run', 'run-local', 'startup'])
def test_launch_requires_tls_and_passes_independent_options(command_project, target):
    root = command_project
    result = command(root, target)
    assert result.returncode != 0
    assert not (root / 'options.json').exists()
    tls = root / '.state/private/tls'
    tls.mkdir(parents=True)
    (tls / 'server.pem').touch()
    assert command(root, target).returncode != 0  # Both certificate and key are required.
    (tls / 'server-key.pem').touch()
    assert command(root, target).returncode == 0
    defaults = json.loads((root / 'options.json').read_text(encoding='utf-8-sig'))
    assert defaults['Port'] == 18761
    assert defaults['NoJarvis'] is False
    assert defaults['NoAssistant'] is False
    result = command(root, target, 'JARVIS=0', 'ASSISTANT=1', 'PORT=18762')
    assert result.returncode == 0, result.stderr
    options = json.loads((root / 'options.json').read_text(encoding='utf-8-sig'))
    assert options['Port'] == 18762
    assert options['NoJarvis'] is True
    assert options['NoAssistant'] is False
    if target != 'startup':
        assert options['Lan'] is (target == 'run')
