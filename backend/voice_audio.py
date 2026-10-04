"""Enumerate real capture inputs; never default to Windows Stereo Mix."""
import hashlib


def enumerate_in_child(connection):
    # PortAudio caches devices at initialization. A fresh process sees hot-plugged inputs.
    try:
        connection.send([{'id': device['id'], 'name': device['name']} for device in inputs()])
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
