"""Bounded private artifacts; no caller paths, commands or external resources."""
import base64
from html import escape
import json
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..security import require_origin

FORMATS = {'html', 'js', 'css', 'markdown', 'txt', 'json', 'csv', 'pdf'}
ARTIFACT_NAMES = {'create_artifact', 'list_artifacts', 'open_artifact'}
ID = re.compile(r'^[0-9a-f]{24}$')
PREVIEW_CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
               "style-src 'unsafe-inline'; img-src data:; font-src data:; media-src data:; "
               "connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; "
               "form-action 'none'; base-uri 'none'; frame-ancestors 'self'")


def artifact_tools():
    def spec(name, description, fields):
        return {'type': 'function', 'name': name, 'description': description, 'strict': True,
                'parameters': {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}}
    return [spec('create_artifact', 'Create one requested artifact. HTML must be complete and self-contained with inline CSS/JavaScript: no external resources, network requests, forms, frames, popups, downloads or top navigation. PDF content uses plain text, # headings, - bullets and pipe tables, never HTML/code; it is rendered locally. Other formats are downloadable source/data, not executed. At most 100000 content characters, or 20000 for PDF. Return the real ID and offer/open the result; never claim unsupported binary files were created.',
                 {'title': {'type': 'string'}, 'format': {'type': 'string', 'enum': sorted(FORMATS)}, 'content': {'type': 'string'}}),
            spec('list_artifacts', 'List the twenty most recent private artifacts with IDs and formats. Discover existing artifacts before reopening them; no arbitrary file reads.', {}),
            spec('open_artifact', 'Open a just-created or listed artifact in the dashboard preview. Only the returned ID is accepted; no path, URL, browser or command arguments.', {'id': {'type': 'string'}})]


def validate(arguments):
    if not isinstance(arguments, dict) or set(arguments) != {'title', 'format', 'content'}:
        raise ValueError('Invalid artifact fields.')
    title, kind, content = arguments['title'], arguments['format'], arguments['content']
    if not isinstance(title, str) or not title.strip() or len(title) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in title):
        raise ValueError('Use a short printable artifact title.')
    if not isinstance(kind, str) or kind not in FORMATS or not isinstance(content, str) or not content.strip():
        raise ValueError('Invalid artifact format or content.')
    if len(content) > (20000 if kind == 'pdf' else 100000) or any(ord(c) < 32 and c not in '\n\r\t' for c in content):
        raise ValueError('Artifact is too large or contains control characters.')
    if kind == 'json':
        try:
            json.loads(content)
        except (ValueError, RecursionError):
            raise ValueError('Invalid or deeply nested JSON artifact.') from None
    return title.strip(), kind, content


def prepare_artifact(arguments):
    """Run in the model child only. Model-supplied PDF bytes are never accepted."""
    title, kind, content = validate(arguments)
    if kind != 'pdf':
        return {'title': title, 'format': kind, 'content': content}
    from .artifact_pdf import render_pdf
    return {'title': title, 'format': kind, 'content': content,
            'pdf': base64.b64encode(render_pdf(title, content)).decode('ascii')}


class ArtifactStore:
    def __init__(self, history):
        self.history = history
        with history.lock, history.db:
            history.db.execute('CREATE TABLE IF NOT EXISTS artifacts '
                               '(id TEXT PRIMARY KEY,title TEXT NOT NULL,format TEXT NOT NULL,created REAL NOT NULL,content BLOB NOT NULL)')

    @staticmethod
    def metadata(row):
        return {key: row[key] for key in ('id', 'title', 'format', 'created')}

    def all(self):
        with self.history.lock:
            return [self.metadata(row) for row in self.history.db.execute('SELECT id,title,format,created FROM artifacts ORDER BY created DESC LIMIT 20')]

    def get(self, identity):
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            raise HTTPException(404, 'Artifact unavailable.')
        with self.history.lock:
            row = self.history.db.execute('SELECT * FROM artifacts WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise HTTPException(404, 'Artifact was removed or is no longer available.')
            return dict(row)

    def create(self, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('Invalid artifact.')
        raw = {key: value for key, value in arguments.items() if key != 'pdf'}
        title, kind, content = validate(raw)
        if kind == 'pdf':
            if not isinstance(arguments.get('pdf'), str) or len(arguments['pdf']) > 350000:
                raise ValueError('PDF rendering is unavailable.')
            data = base64.b64decode(arguments['pdf'], validate=True)
            if not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):
                raise ValueError('PDF rendering failed.')
        else:
            if 'pdf' in arguments:
                raise ValueError('Unexpected PDF data.')
            data = content.encode('utf-8')
        if len(data) > 256000:
            raise ValueError('Artifact exceeds the private storage limit.')
        artifact = {'id': secrets.token_hex(12), 'title': title, 'format': kind, 'created': time.time()}
        with self.history.lock, self.history.db:
            self.history.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?)',
                                    (artifact['id'], title, kind, artifact['created'], data))
            self.history.db.execute('DELETE FROM artifacts WHERE id NOT IN (SELECT id FROM artifacts ORDER BY created DESC LIMIT 20)')
        return {'ok': True, 'id': artifact['id'], 'artifact': artifact,
                'message': f'Created {title}. Open it in Artifacts.'}

    def dispatch(self, name, arguments, navigate):
        if name == 'create_artifact':
            return self.create(arguments)
        if name == 'list_artifacts' and arguments == {}:
            return {'ok': True, 'artifacts': self.all(), 'message': 'Saved artifacts checked.'}
        if name == 'open_artifact' and isinstance(arguments, dict) and set(arguments) == {'id'}:
            artifact = self.metadata(self.get(arguments['id']))
            if navigate is None:
                return {'ok': False, 'message': 'Artifact preview is unavailable.'}
            result = navigate('artifacts', artifact=artifact['id'])
            return {**result, 'artifact': artifact}
        raise ValueError('Invalid artifact operation.')

    def delete(self, identity):
        self.get(identity)
        with self.history.lock, self.history.db:
            self.history.db.execute('DELETE FROM artifacts WHERE id=?', (identity,))


def artifacts_router(store, voice, assistant, authenticate, owner):
    def access(request: Request, device=Depends(authenticate)):
        if request.url.scheme != 'https':
            raise HTTPException(426, 'Use HTTPS to view artifacts.')
        if not assistant.unlocked():
            raise HTTPException(409, 'Unlock the PC to view artifacts.')
        return device

    router = APIRouter(prefix='/api/artifacts', dependencies=[Depends(access)])

    @router.get('')
    def listing():
        return store.all()

    @router.get('/{identity}/preview')
    def preview(identity: str):
        item = store.get(identity)
        if item['format'] == 'pdf':
            return Response(item['content'], media_type='application/pdf',
                            headers={'Content-Security-Policy': "default-src 'none'; frame-ancestors 'self'"})
        document = item['content'].decode('utf-8') if item['format'] == 'html' else (
            '<!doctype html><meta charset="utf-8"><style>body{font:16px/1.6 monospace;padding:24px;'
            'color:#e8edf5;background:#10151d}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>'
            + escape(item['content'].decode('utf-8')) + '</pre>')
        return Response(document, media_type='text/html', headers={'Content-Security-Policy': PREVIEW_CSP})

    @router.get('/{identity}/download')
    def download(identity: str):
        item = store.get(identity)
        extension = 'md' if item['format'] == 'markdown' else item['format']
        filename = (re.sub(r'[^a-zA-Z0-9_-]+', '-', item['title']).strip('-')[:60] or 'artifact') + '.' + extension
        return Response(item['content'], media_type='application/pdf' if extension == 'pdf' else 'application/octet-stream',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    @router.delete('/{identity}', dependencies=[Depends(owner)])
    def remove(identity: str, request: Request):
        require_origin(request)
        voice.stop()
        with voice.lock:
            store.delete(identity)
        return {'ok': True}

    return router
