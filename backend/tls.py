"""Private local HTTPS authority; Windows protects its signing key with DPAPI."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
import shutil
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .connection_info import connection_directories, network_addresses


def dpapi(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, output = Blob(len(data), buffer), Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.data)


def private_bytes(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def ensure_tls(directory, addresses=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_path, ca_key_path = directory / 'ca.pem', directory / 'ca-key.dpapi'
    if ca_path.exists() != ca_key_path.exists():
        raise RuntimeError('Local CA files are incomplete. Restore them rather than silently changing device trust.')
    if not ca_path.exists():
        if os.name != 'nt':
            raise RuntimeError('The local CA setup uses Windows DPAPI.')
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'G16 Command Center Local CA')])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1825))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
        ca_key_path.write_bytes(dpapi(private_bytes(ca_key)))
        ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    else:
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        ca_key = serialization.load_pem_private_key(dpapi(ca_key_path.read_bytes(), decrypt=True), password=None)
    if ca.not_valid_after_utc < now + timedelta(days=14):
        raise RuntimeError('The local CA is expiring; renew device trust explicitly.')
    (directory / 'G16 Dashboard CA.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
    addresses = network_addresses() if addresses is None else addresses
    names = [x509.DNSName('localhost'), x509.DNSName(socket.gethostname().lower()),
             x509.IPAddress(ipaddress.ip_address('127.0.0.1')), x509.IPAddress(ipaddress.ip_address('::1'))]
    names += [x509.IPAddress(ipaddress.ip_address(ip)) for _, ip in addresses]
    sans = x509.SubjectAlternativeName(list(dict.fromkeys(names)))
    cert_path, key_path = directory / 'server.pem', directory / 'server-key.pem'
    if cert_path.exists() and key_path.exists():
        current = x509.load_pem_x509_certificate(cert_path.read_bytes())
        if set(current.extensions.get_extension_for_class(x509.SubjectAlternativeName).value) == set(sans) and current.not_valid_after_utc > now + timedelta(days=14):
            return False
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificate = (x509.CertificateBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'G16 Command Center')]))
                   .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=180))
                   .add_extension(sans, critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                   .sign(ca_key, hashes.SHA256()))
    key_path.write_bytes(private_bytes(key))
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
    return True


def export_public_certificate(directory):
    source = Path(directory) / 'G16 Dashboard CA.cer'
    for target in connection_directories():
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target / source.name)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    tls = root / '.state/private/tls'
    ensure_tls(tls)
    export_public_certificate(tls)
    cert = x509.load_pem_x509_certificate((tls / 'ca.pem').read_bytes())
    print('Certificate:', tls / 'G16 Dashboard CA.cer')
    print('CA SHA-256 fingerprint:', cert.fingerprint(hashes.SHA256()).hex().upper())
