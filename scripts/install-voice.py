"""Install only Jarvis and wake-word runtime models, never another assistant UI."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / '.state/private/voice/models'
JARVIS = 'https://huggingface.co/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/medium/'
WAKE = 'https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/'
JARVIS_WAKE = 'https://raw.githubusercontent.com/fwartner/home-assistant-wakewords-collection/8bcd2f20bb7b76c351b2eff871fa1ce873fe9be2/'
FILES = {'jarvis-medium.onnx': JARVIS + 'jarvis-medium.onnx',
         'jarvis-medium.onnx.json': JARVIS + 'jarvis-medium.onnx.json',
         'jarvis_v1.onnx': JARVIS_WAKE + 'en/jarvis/jarvis_v1.onnx',
         'jarvis-wake-LICENSE.txt': JARVIS_WAKE + 'LICENSE',
         'melspectrogram.onnx': WAKE + 'melspectrogram.onnx',
         'embedding_model.onnx': WAKE + 'embedding_model.onnx'}
SHA256 = {
    'jarvis-medium.onnx': '3f6534bd4050931b4c7d16ef777bafa2d90eb1e7baa8af9358623ffe609506da',
    'jarvis-medium.onnx.json': 'f2c2d77f64ed6e771fc7d2defa59cd47d6bd03c3e7602c732d63ea46954f2553',
    'jarvis_v1.onnx': '32171d04d3e4b6fdb8907412ab060c486a2b0a8bc6cff0703212a812b5dd5056',
    'jarvis-wake-LICENSE.txt': 'd0355b2ffd8e81211b62e9529518b26e2e6f048c220809ea675142bcf40367fa',
    'melspectrogram.onnx': 'ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f',
    'embedding_model.onnx': '70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f',
}


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in FILES.items():
        destination = DESTINATION / name
        if not destination.is_file():
            print(f'Downloading {name}', flush=True)
            temporary = destination.with_suffix(destination.suffix + '.part')
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'G16-Command-Center/1.0'})
                with urllib.request.urlopen(request, timeout=30) as source, temporary.open('wb') as output:
                    total = 0
                    while block := source.read(1024 * 1024):
                        total += len(block)
                        if total > 100_000_000:
                            raise ValueError('Unexpected model size.')
                        output.write(block)
                if temporary.stat().st_size < 100:
                    raise ValueError('Incomplete model download.')
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256[name]:
                    raise ValueError(f'Unexpected checksum for {name}.')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != SHA256[name]:
            raise ValueError(f'Unexpected checksum for installed {name}.')
        manifest[name] = {'source': url, 'sha256': digest,
                          'bytes': destination.stat().st_size}
    (DESTINATION / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Local voice models are ready. No microphone or OpenAI connection was started.')


if __name__ == '__main__':
    main()
