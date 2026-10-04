"""Offline native wake check: synthetic in-memory speech, no microphone or playback."""
import io
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import numpy as np
    from scipy.signal import resample_poly
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    from openwakeword.model import Model
    from backend.voice_wake import WAKE_MODEL, WAKE_THRESHOLD

    directory = ROOT / '.state/private/voice/models'
    voice = PiperVoice.load(directory / 'jarvis-medium.onnx')
    wake = Model(wakeword_models=[str(directory / WAKE_MODEL)], inference_framework='onnx',
                 melspec_model_path=str(directory / 'melspectrogram.onnx'),
                 embedding_model_path=str(directory / 'embedding_model.onnx'))
    positive = ['Jarvis.', 'Jarvis!', 'Hey Jarvis.']
    negative = ['Hello.', 'Harvest.', 'Are you jealous?', 'Good evening, sir.',
                'Please wake up.', 'Turn the volume down.']
    scores = []
    for text in positive + negative:
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            voice.synthesize_wav(text, wav, SynthesisConfig(noise_scale=0, noise_w_scale=0))
        audio.seek(0)
        with wave.open(audio, 'rb') as wav:
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32)
            rate = wav.getframerate()
        samples = np.concatenate([np.zeros(16000), resample_poly(pcm, 16000, rate),
                                  np.zeros(24000)]).clip(-32768, 32767).astype(np.int16)
        wake.reset()
        peak = max(max(wake.predict(samples[i:i+1280]).values(), default=0)
                   for i in range(0, len(samples)-1280, 1280))
        scores.append(peak)
    assert min(scores[:len(positive)]) >= WAKE_THRESHOLD, 'Synthetic Jarvis activation missed.'
    assert max(scores[len(positive):]) < WAKE_THRESHOLD, 'Synthetic negative activated.'
    print(f'Native Jarvis wake passed: {len(positive)} positive / {len(negative)} negative clips; '
          f'min positive {min(scores[:len(positive)]):.4f}, max negative {max(scores[len(positive):]):.4f}. '
          'No microphone, playback, cloud request or audio file.')


if __name__ == '__main__':
    main()
