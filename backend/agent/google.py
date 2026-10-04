"""Fixed Google endpoints; credentials never reach the model or browser."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
IDENTITY_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
EVENTS_SCOPE = 'https://www.googleapis.com/auth/calendar.events.readonly'
SHEETS_SCOPE = 'https://www.googleapis.com/auth/spreadsheets'
SCOPES = ('openid', 'email', EVENTS_SCOPE, SHEETS_SCOPE)


class GoogleError(Exception):
    def __init__(self, message='Google could not complete that request. Please try again.', status=502):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GoogleClient:
    def _request(self, endpoint, *, form=None, token=None, query=None, payload=None, method=None):
        # No arbitrary URLs, caller headers, redirects, proxies or automatic retries.
        if endpoint not in {TOKEN_URL, IDENTITY_URL, EVENTS_URL} and not re.fullmatch(r'https://sheets\.googleapis\.com/v4/spreadsheets/[A-Za-z0-9_-]{10,150}/values/[^/?#]+', endpoint):
            raise GoogleError('Unsupported Google operation.', 400)
        url = endpoint + ('?' + urlencode(query) if query else '')
        headers = {'Accept': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = urlencode(form).encode() if form is not None else None
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if payload is not None:
            data = json.dumps(payload, allow_nan=False).encode()
            headers['Content-Type'] = 'application/json'
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(Request(url, data=data, headers=headers, method=method), timeout=10) as response:
                raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise GoogleError('Google returned too much data. Please narrow the request.')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise GoogleError()
            return result
        except HTTPError as error:
            # Never echo provider bodies, URLs, headers, codes or token details.
            error.close()
            if error.code == 401 or endpoint == TOKEN_URL and error.code == 400:
                raise GoogleError('Google sign-in expired or was revoked. Connect again.', 409) from None
            if error.code == 403:
                raise GoogleError('Google denied access. Check the API is enabled and the requested permissions were granted.', 409) from None
            raise GoogleError() from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise GoogleError() from None

    def exchange(self, client, code, redirect, verifier):
        return self._request(TOKEN_URL, form={**client, 'code': code, 'redirect_uri': redirect,
                                             'code_verifier': verifier, 'grant_type': 'authorization_code'})

    def refresh(self, client, refresh_token):
        return self._request(TOKEN_URL, form={**client, 'refresh_token': refresh_token, 'grant_type': 'refresh_token'})

    def identity(self, token):
        return self._request(IDENTITY_URL, token=token)

    def events(self, token, query):
        return self._request(EVENTS_URL, token=token, query=query)

    def sheet_values(self, token, sheet, update=None):
        from .sheets import SheetRegistration, values
        body = SheetRegistration.model_validate({key: sheet[key] for key in ('name', 'spreadsheetId', 'range')})
        endpoint = 'https://sheets.googleapis.com/v4/spreadsheets/' + body.spreadsheetId + '/values/' + quote(body.range, safe='')
        if update is None:
            return self._request(endpoint, token=token, query={'majorDimension': 'ROWS', 'valueRenderOption': 'UNFORMATTED_VALUE'})
        return self._request(endpoint, token=token, method='PUT', query={'valueInputOption': 'RAW'},
                             payload={'range': body.range, 'majorDimension': 'ROWS', 'values': values(update, body.range)})
