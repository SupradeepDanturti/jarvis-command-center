import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID

from backend.tls import ensure_tls


def test_local_ca_reused_and_server_identity_updated(tmp_path):
    tls = tmp_path / 'tls'
    assert ensure_tls(tls, [('Wi-Fi', '192.168.2.12')]) is True
    ca = x509.load_pem_x509_certificate((tls / 'ca.pem').read_bytes())
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    context = ssl.create_default_context(cafile=str(tls / 'ca.pem'))
    context.load_cert_chain(str(tls / 'server.pem'), str(tls / 'server-key.pem'))
    assert ensure_tls(tls, [('Wi-Fi', '192.168.2.12')]) is False
    assert ensure_tls(tls, [('Wi-Fi', '192.168.2.20')]) is True
    assert x509.load_pem_x509_certificate((tls / 'ca.pem').read_bytes()).fingerprint(hashes.SHA256()) == ca.fingerprint(hashes.SHA256())
    cert = x509.load_pem_x509_certificate((tls / 'server.pem').read_bytes())
    assert ExtendedKeyUsageOID.SERVER_AUTH in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert b'BEGIN PRIVATE KEY' not in (tls / 'ca-key.dpapi').read_bytes()
