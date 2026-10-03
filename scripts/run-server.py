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
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')

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
        state = ROOT / '.state'
        state.mkdir(exist_ok=True)
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

        async def publish(server):
            while not server.started:
                await asyncio.sleep(0.2)
            while True:
                try:
                    code = (state / 'pairing-code.txt').read_text(encoding='utf-8').strip()
                    results = await asyncio.to_thread(write_connection_files, code, args.port)
                    for destination, error in results:
                        if error:
                            logger.warning('Cannot update connection file %s: %s', destination, error)
                        else:
                            logger.info('Updated connection file %s', destination)
                except Exception:
                    logger.exception('Could not refresh connection instructions; retrying shortly')
                await asyncio.sleep(30)

        async def serve():
            server = uvicorn.Server(uvicorn.Config('backend.main:app', host='0.0.0.0',
                                    port=args.port, access_log=False, log_config=None))
            publisher = asyncio.create_task(publish(server))
            try:
                await server.serve()
            finally:
                publisher.cancel()
                with suppress(asyncio.CancelledError):
                    await publisher

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
