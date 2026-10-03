"""Public certificate download only. No credentials, telemetry, or controls."""
import html
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from .connection_info import network_addresses


def create_onboarding(tls_directory, dashboard_port):
    directory = Path(tls_directory)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get('/', response_class=HTMLResponse)
    def index():
        certificate = x509.load_pem_x509_certificate((directory / 'ca.pem').read_bytes())
        fingerprint = certificate.fingerprint(hashes.SHA256()).hex().upper()
        addresses = network_addresses()
        ip = addresses[0][1] if addresses else 'localhost'
        url = html.escape(f'https://{ip}:{dashboard_port}')
        return f'''<!doctype html><html lang="en"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>G16 · Tablet setup</title><style>body{{background:#0b0e14;color:#e8edf5;font:16px/1.7 system-ui;max-width:600px;margin:50px auto;padding:24px}}h1{{color:#bbf780}}a{{color:#bbf780}}.button{{display:block;padding:16px;border:1px solid #bbf780;border-radius:10px;text-align:center;margin:24px 0;text-decoration:none}}code{{overflow-wrap:anywhere}}li{{margin:14px 0}}small{{color:#a5b0c2}}</style>
        <h1>Set up your Redmi.</h1><p>One certificate install. One laptop approval. Then automatic connection.</p>
        <a class="button" href="/G16-Dashboard-CA.cer">Download G16 Dashboard CA.cer</a>
        <ol><li>Download the certificate, or copy it from your laptop using USB.</li>
        <li>In tablet Settings, search for <b>CA certificate</b> and install the downloaded file as a CA certificate.</li>
        <li>Open <a href="{url}">{url}</a> and request browser approval.</li>
        <li>On the laptop, open System → Approved devices and match the fingerprint shown on the tablet before approving.</li></ol>
        <p><b>Verify the certificate:</b> compare its SHA-256 fingerprint in the tablet's certificate details with the trusted connection text file on your laptop. A USB transfer avoids relying on this HTTP download.</p>
        <small>Expected certificate SHA-256:<br><code>{fingerprint}</code></small>
        <p><small>This setup page has no login, recovery code, readings, or Windows controls. Your dashboard uses encrypted HTTPS.</small></p></html>'''

    @app.get('/G16-Dashboard-CA.cer')
    def certificate():
        return FileResponse(directory / 'G16 Dashboard CA.cer',
                            media_type='application/x-x509-ca-cert', filename='G16 Dashboard CA.cer')

    return app
