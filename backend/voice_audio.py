"""Enumerate real capture inputs; never default to Windows Stereo Mix."""
import hashlib


def enumerate_in_child(connection, output=False):
    # PortAudio caches devices at initialization. A fresh process sees hot-plugged inputs.
    try:
        connection.send([{'id': device['id'], 'name': device['name']} for device in (outputs() if output else inputs())])
    except Exception:
        connection.send([])
    finally:
        connection.close()


def inputs():
    import sounddevice as sd
    result = []
    for index, device in enumerate(sd.query_devices()):
        if not device['max_input_channels']:
            continue
        name = device['name']
        if any(term in name.lower() for term in ('stereo mix', 'sound mapper', 'primary sound', 'pc speaker', 'loopback')):
            continue
        # MME permits the 16 kHz mono stream required by the wake model, without resampling.
        host = sd.query_hostapis(device['hostapi'])['name']
        if host != 'MME':
            continue
        try:
            sd.check_input_settings(device=index, channels=1, dtype='int16', samplerate=16000)
        except Exception:
            continue
        identity = hashlib.sha256(f'{host}|{name}'.encode()).hexdigest()[:20]
        result.append({'id': identity, 'name': name, 'index': index})
    return result


def resolve_input(selected=None):
    devices = inputs()
    if selected:
        choice = next((device for device in devices if device['id'] == selected), None)
        if not choice:
            raise ValueError('Selected microphone is unavailable.')
        return choice
    if not devices:
        raise ValueError('No suitable microphone is available.')
    return next((device for device in devices if 'microphone array' in device['name'].lower()), devices[0])


def outputs():
    """Concrete speaker endpoints, independent of the Windows default/headphones."""
    import sounddevice as sd
    result = []
    for index, device in enumerate(sd.query_devices()):
        name = device['name']
        if not device['max_output_channels'] or 'speaker' not in name.lower():
            continue
        if any(word in name.lower() for word in ('headphone', 'mapper', 'primary', 'pc speaker')):
            continue
        host = sd.query_hostapis(device['hostapi'])['name']
        if host != 'MME':
            continue
        try:
            sd.check_output_settings(device=index, channels=1, dtype='int16', samplerate=22050)
        except Exception:
            continue
        identity = hashlib.sha256(f'output|{host}|{name}'.encode()).hexdigest()[:20]
        result.append({'id': identity, 'name': name, 'index': index})
    return result


def resolve_output(selected=None):
    devices = outputs()
    if selected:
        choice = next((device for device in devices if device['id'] == selected), None)
        if not choice:
            raise ValueError('Selected speaker is unavailable. Choose a connected speaker.')
        return choice
    if not devices:
        raise ValueError('No speaker output is available. Headphones will not be used.')
    return next((device for device in devices if 'realtek' in device['name'].lower()), devices[0])


def play_on_speaker(audio, device, allowed):
    """Use the explicit endpoint and check cancellation/lock between PCM chunks."""
    import sounddevice as sd
    import wave
    audio.seek(0)
    with wave.open(audio, 'rb') as wav:
        if wav.getsampwidth() != 2:
            raise ValueError('Unsupported voice sample format.')
        if not allowed():
            return
        with sd.RawOutputStream(device=device['index'], samplerate=wav.getframerate(),
                                channels=wav.getnchannels(), dtype='int16') as stream:
            while allowed():
                chunk = wav.readframes(2048)
                if not chunk:
                    break
                stream.write(chunk)
