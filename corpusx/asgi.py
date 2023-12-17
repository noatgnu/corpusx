"""
ASGI config for corpusx project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddleware
from django.core.asgi import get_asgi_application

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corpusx.settings')
django_asgi_app = get_asgi_application()

from cephalon.web_socket_authentication import WebsocketInterchangeAPIKeyAuthenticationMiddleware
from corpusx.routing import websocket_urlpatterns


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        WebsocketInterchangeAPIKeyAuthenticationMiddleware(
            URLRouter(
                websocket_urlpatterns
            )
        )
    ),
})