"""Personal data is restricted to the approved direct-loopback owner over HTTPS."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..security import require_origin
from .google import GoogleError
from .profile import Profile
from .memory import Fact
from .sheets import SheetRegistration


class ClientImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contents: SecretStr = Field(max_length=10000)


class Enabled(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool


class SheetRange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    range: str | None = Field(default=None, min_length=1, max_length=220)


class TabPage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    offset: int = Field(default=0, ge=0, le=100000)


class SheetSearch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    query: str = Field(default='', max_length=100)
    pageToken: str | None = Field(default=None, min_length=1, max_length=2048)


class SheetValues(SheetRange):
    model_config = ConfigDict(extra='forbid', strict=True)
    values: list[list[str | int | float | bool | None]] = Field(min_length=1, max_length=100)


def assistant_router(service, owner, authenticate):
    def private(request: Request, device=Depends(owner)):
        if request.url.scheme != 'https':
            raise HTTPException(426, 'Use the HTTPS dashboard for personal assistant access.')
        return device

    router = APIRouter(prefix='/api/assistant', dependencies=[Depends(private)])

    def authorized(request):
        try:
            private(request, owner(request, authenticate(request)))
            return True
        except HTTPException:
            return False

    def call(function, *args):
        try:
            return function(*args)
        except GoogleError as error:
            raise HTTPException(error.status, str(error)) from None
        except (OSError, ValueError, TypeError):
            raise HTTPException(503, 'Private assistant storage or the Google response is unavailable.') from None

    @router.get('/status')
    def status():
        return service.status()

    @router.post('/enabled')
    def enabled(body: Enabled, request: Request):
        require_origin(request)
        service.stop_voice()
        return call(service.enable, body.enabled)

    @router.put('/google/client')
    def client(body: ClientImport, request: Request):
        require_origin(request)
        service.stop_voice()
        return call(service.configure, body.contents.get_secret_value())

    @router.post('/google/connect')
    def connect(request: Request):
        require_origin(request)
        service.stop_voice()
        return call(service.begin, lambda: authorized(request))

    @router.delete('/google/connection')
    def disconnect(request: Request):
        require_origin(request)
        service.stop_voice()
        return call(service.disconnect)

    @router.delete('/google/client')
    def remove_client(request: Request):
        require_origin(request)
        service.stop_voice()
        return call(service.disconnect, True)

    @router.get('/profile')
    def profile():
        return call(service.profile.get).model_dump()

    @router.put('/profile')
    def save_profile(body: Profile, request: Request):
        require_origin(request)
        service.stop_voice()
        with service.lock:
            service._cancel()  # discard any agenda built with the earlier preferences
            return call(service.profile.save, body).model_dump()

    @router.delete('/profile')
    def forget_profile(request: Request):
        require_origin(request)
        service.stop_voice()
        with service.lock:
            service._cancel()
            call(service.profile.clear)
        return {'ok': True, 'message': 'Personal preferences forgotten.'}

    @router.post('/today')
    def today(request: Request):
        require_origin(request)
        result = call(service.today)
        private(request, owner(request, authenticate(request)))
        return result

    def changed(request):
        require_origin(request)
        service.stop_voice()  # remove stale private context from the isolated worker before editing

    def mutate(request, function, *args):
        changed(request)
        with service.lock:
            service._cancel()
            return call(function, *args)

    @router.get('/memory')
    def memory():
        return call(service.inspect_memory)

    @router.put('/memory/cloud')
    def cloud(body: Enabled, request: Request):
        mutate(request, service.memory.set_cloud, body.enabled)
        return {'ok': True}

    @router.post('/memory')
    def add_memory(body: Fact, request: Request):
        return {'id': mutate(request, service.memory.save, body.text)}

    @router.put('/memory/{identity}')
    def edit_memory(identity: str, body: Fact, request: Request):
        return {'id': mutate(request, service.memory.save, body.text, identity)}

    @router.delete('/memory')
    def clear_memory(request: Request):
        mutate(request, service.memory.delete)
        return {'ok': True}

    @router.delete('/memory/{identity}')
    def forget_memory(identity: str, request: Request):
        mutate(request, service.memory.delete, identity)
        return {'ok': True}

    @router.get('/sheets')
    def sheets():
        with service.lock:
            service.sheets.expire()
            account = service.vault.get('account')
            return {'sheets': service.sheets.all(account['id']) if account else [],
                    'discoveryEnabled': service.sheets.discovery_enabled(account['id']) if account else False,
                    'discoveryReady': service.status()['sheetSearchReady'],
                    'proposals': list(service.sheets.proposals.values())}

    @router.put('/sheets/discovery')
    def sheet_discovery(body: Enabled, request: Request):
        mutate(request, lambda: service.sheets.set_discovery(service.account_id(), body.enabled))
        return {'ok': True, 'enabled': body.enabled}

    @router.post('/sheets/search')
    def search_sheets(body: SheetSearch, request: Request):
        require_origin(request)
        result = call(service.search_sheets, body.query, body.pageToken, lambda: authorized(request))
        private(request, owner(request, authenticate(request)))
        return result

    @router.post('/sheets')
    def register_sheet(body: SheetRegistration, request: Request):
        changed(request)
        with service.lock:
            service._cancel()
            return {'id': call(service.sheets.register, call(service.account_id), body)}

    @router.delete('/sheets/{identity}')
    def remove_sheet(identity: str, request: Request):
        changed(request)
        with service.lock:
            service._cancel()
            call(service.sheets.delete, call(service.account_id), identity)
        return {'ok': True}

    @router.post('/sheets/{identity}/read')
    def read_sheet(identity: str, request: Request, body: SheetRange | None = None):
        require_origin(request)
        result = call(service.sheet_read, identity, lambda: authorized(request), body.range if body else None)
        private(request, owner(request, authenticate(request)))
        return result

    @router.post('/sheets/{identity}/tabs')
    def sheet_tabs(identity: str, request: Request, body: TabPage | None = None):
        require_origin(request)
        result = call(service.sheet_tabs, identity, lambda: authorized(request), body.offset if body else 0)
        private(request, owner(request, authenticate(request)))
        return result

    @router.post('/sheets/{identity}/propose')
    def propose_sheet(identity: str, body: SheetValues, request: Request):
        require_origin(request)
        return call(service.sheet_propose, identity, body.values, body.range)

    @router.delete('/sheet-proposals/{identity}')
    def discard_sheet(identity: str, request: Request):
        require_origin(request)
        with service.lock:
            service.sheets.proposals.pop(identity, None)
        return {'ok': True}

    @router.post('/sheet-proposals/{identity}/apply')
    def apply_sheet(identity: str, request: Request):
        require_origin(request)
        service.stop_voice()
        result = call(service.sheet_apply, identity, lambda: authorized(request))
        private(request, owner(request, authenticate(request)))
        return result

    return router
