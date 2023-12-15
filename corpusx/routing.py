from django.urls import re_path

from corpusx.consumers import InterServerCommunicationConsumer

websocket_urlpatterns = [
    re_path(r'ws/interchange/(?P<interchange>\w+)/(?P<server_id>\w+)/$', InterServerCommunicationConsumer.as_asgi()),
]