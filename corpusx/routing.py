from django.urls import re_path

from corpusx.consumers import InterServerCommunicationConsumer, SearchDataConsumer, UserSendConsumer, UserResultConsumer

websocket_urlpatterns = [
    re_path(r'ws/initial/(?P<interchange>\w+)/(?P<server_id>\w+)/$', InterServerCommunicationConsumer.as_asgi()),
    re_path(r'ws/search/(?P<interchange>\w+)/(?P<server_id>\w+)/$', SearchDataConsumer.as_asgi()),
    re_path(r'ws/user/send/(?P<session_id>[\w\-]+)/(?P<client_id>[\w\-]+)/$', UserSendConsumer.as_asgi()),
    re_path(r'ws/user/results/(?P<session_id>[\w\-]+)/(?P<client_id>[\w\-]+)/$', UserResultConsumer.as_asgi()),
]