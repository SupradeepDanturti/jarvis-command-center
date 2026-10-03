"""Windowless Windows startup entry point with bounded local logs."""
import argparse
import asyncio
from contextlib import suppress
import ctypes
from ctypes import wintypes
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


class LogStream:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, text):
        if text.strip():
            self.logger.log(self.level, text.rstrip())
        return len(text)

    def flush(self):
        for handler in self.logger.handlers:
            handler.flush()

    def isatty(self):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18761)
    parser.add_argument('--setup-port', type=int, default=18760)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')
    if not 1024 <= args.setup_port <= 65535 or args.setup_port == args.port:
        parser.error('Setup port must be between 1024 and 65535 and different from the dashboard port.')

    # Task Scheduler also ignores duplicate starts. The mutex covers direct starts.
    mutex = None
    kernel32 = None
    if os.name == 'nt':
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        key = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16]
        mutex = kernel32.CreateMutexW(None, False, f'Local\\G16CommandCenter-{key}')
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(mutex)
            return

    try:
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        state = ROOT / '.state/private'
        state.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(state / 'server.log', maxBytes=2_000_000,
                                      backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger = logging.getLogger('g16.startup')
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        sys.stdout = LogStream(logger, logging.INFO)
        sys.stderr = LogStream(logger, logging.ERROR)
        for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
            uvicorn_logger = logging.getLogger(name)
            uvicorn_logger.handlers = [handler]
            uvicorn_logger.propagate = False
            uvicorn_logger.setLevel(logging.INFO)
        logger.info('Starting G16 Command Center on port %s', args.port)
        import uvicorn
        from backend.connection_info import write_connection_files
        tls_directory = state / 'tls'
        secure = (tls_directory / 'ca.pem').exists()
        if secure:
            from backend.tls import ensure_tls
            ensure_tls(tls_directory)

        async def publish(server):
            while not server.started:
                await asyncio.sleep(0.2)
            while True:
                try:
                    code = (state / 'pairing-code.txt').read_text(encoding='utf-8').strip()
                    if secure and await asyncio.to_thread(ensure_tls, tls_directory):
                        server.config.ssl.load_cert_chain(str(tls_directory / 'server.pem'), str(tls_directory / 'server-key.pem'))
                    fingerprint = None
                    if secure:
                        from cryptography import x509
                        from cryptography.hazmat.primitives import hashes
                        fingerprint = x509.load_pem_x509_certificate((tls_directory / 'ca.pem').read_bytes()).fingerprint(hashes.SHA256()).hex().upper()
                    results = await asyncio.to_thread(write_connection_files, code, args.port, scheme='https' if secure else 'http', setup_port=args.setup_port if secure else None, fingerprint=fingerprint)
                    for destination, error in results:
                        if error:
                            logger.warning('Cannot update connection file %s: %s', destination, error)
                        else:
                            logger.info('Updated connection file %s', destination)
                except Exception:
                    logger.exception('Could not refresh connection instructions; retrying shortly')
                await asyncio.sleep(30)

        async def serve():
            tls_options = {'ssl_certfile': str(tls_directory / 'server.pem'),
                           'ssl_keyfile': str(tls_directory / 'server-key.pem')} if secure else {}
            server = uvicorn.Server(uvicorn.Config('backend.main:app', host='0.0.0.0',
                                    port=args.port, access_log=False, log_config=None,
                                    proxy_headers=False, **tls_options))
            publisher = asyncio.create_task(publish(server))
            setup_server = None
            setup_task = None
            if secure:
                from backend.onboarding import create_onboarding
                class SetupServer(uvicorn.Server):
                    def capture_signals(self):
                        return suppress()
                setup_server = SetupServer(uvicorn.Config(create_onboarding(tls_directory, args.port),
                             host='0.0.0.0', port=args.setup_port, access_log=False, log_config=None, proxy_headers=False))
                async def run_setup():
                    try:
                        await setup_server.serve()
                    except SystemExit:
                        logger.error('Certificate setup port is unavailable; the HTTPS dashboard remains active.')
                setup_task = asyncio.create_task(run_setup())
            try:
                await server.serve()
            finally:
                publisher.cancel()
                with suppress(asyncio.CancelledError):
                    await publisher
                if setup_server:
                    setup_server.should_exit = True
                    await setup_task

        asyncio.run(serve())
    except Exception:
        if 'logger' in locals():
            logger.exception('Dashboard startup failed')
        raise
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)


if __name__ == '__main__':
    main()
