from channels.db import database_sync_to_async
from django.contrib.auth.hashers import make_password

from cephalon.models import APIKey
from cephalon.utils import Sha512ApiKeyHasher

@database_sync_to_async
def get_APIKey(key):
    try:
        hashed_key = make_password(key, hasher=Sha512ApiKeyHasher())
        return APIKey.objects.get(key=hashed_key)
    except APIKey.DoesNotExist:
        return None


class WebsocketInterchangeAPIKeyAuthenticationMiddleware:
    """
    Custom authentication for websocket interchange
    """

    def __init__(self,app):
        self.app = app

    async def __call__(self, scope, receive, send):
        for k in scope["headers"]:
            if k[0] == b'x-api-key':
                api_key = k[1].decode("utf-8")
                api_key = await get_APIKey(api_key)
                scope["api_key"] = api_key
                break
        print(scope)
        return await self.app(scope, receive, send)