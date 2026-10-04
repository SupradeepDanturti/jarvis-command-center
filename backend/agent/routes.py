"""Personal data is restricted to the approved direct-loopback owner over HTTPS."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..security import require_origin
from .google import GoogleError
from .profile import Profile


class ClientImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contents: SecretStr = Field(max_length=10000)


class Enabled(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool


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
        return call(service.enable, body.enabled)

    @router.put('/google/client')
    def client(body: ClientImport, request: Request):
        require_origin(request)
        return call(service.configure, body.contents.get_secret_value())

    @router.post('/google/connect')
    def connect(request: Request):
        require_origin(request)
        return call(service.begin, lambda: authorized(request))

    @router.delete('/google/connection')
    def disconnect(request: Request):
        require_origin(request)
        return call(service.disconnect)

    @router.delete('/google/client')
    def remove_client(request: Request):
        require_origin(request)
        return call(service.disconnect, True)

    @router.get('/profile')
    def profile():
        return call(service.profile.get).model_dump()

    @router.put('/profile')
    def save_profile(body: Profile, request: Request):
        require_origin(request)
        with service.lock:
            service._cancel()  # discard any agenda built with the earlier preferences
            return call(service.profile.save, body).model_dump()

    @router.delete('/profile')
    def forget_profile(request: Request):
        require_origin(request)
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

    return router
