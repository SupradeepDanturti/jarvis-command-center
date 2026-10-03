from fastapi.testclient import TestClient
from backend.onboarding import create_onboarding
from backend.tls import ensure_tls


def test_setup_only_serves_public_certificate_and_guidance(tmp_path):
    ensure_tls(tmp_path, [('Wi-Fi','192.168.2.12')])
    with TestClient(create_onboarding(tmp_path, 18761)) as client:
        assert client.get('/').status_code == 200
        response = client.get('/G16-Dashboard-CA.cer')
        assert response.status_code == 200
        assert response.content == (tmp_path/'G16 Dashboard CA.cer').read_bytes()
        for path in ['/api/apps', '/api/pair', '/api/system', '/server-key.pem', '/ca-key.dpapi', '/static/../ca-key.dpapi']:
            assert client.get(path).status_code == 404
