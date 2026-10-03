from unittest.mock import patch

from backend.telemetry import Telemetry


def test_nvidia_unavailable_still_collects_windows_metrics():
    telemetry = Telemetry()
    telemetry.nvidia = None
    sample = telemetry.sample()
    assert sample['gpu'] is None
    assert sample['cpu']['temperature'] is None
    assert sample['fps'] is None
    assert sample['memory']['total'] > 0
    assert sample['network']['download'] >= 0


def test_failed_nvidia_query_isolated():
    telemetry = Telemetry()
    telemetry.nvidia = 'nvidia-smi'
    with patch('backend.telemetry.subprocess.run', side_effect=OSError):
        assert telemetry.gpu_sample() is None


def test_partial_nvidia_sensor_values():
    telemetry = Telemetry()
    telemetry.nvidia = 'nvidia-smi'
    with patch('backend.telemetry.subprocess.run') as run:
        run.return_value.stdout = 'NVIDIA GPU, 58, 42, 1500, 2048, 8192, [N/A]\n'
        gpu = telemetry.gpu_sample()
    assert gpu['usage'] == 42
    assert gpu['memory_total'] == 8192
    assert gpu['power'] is None
