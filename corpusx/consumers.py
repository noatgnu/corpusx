import json
from datetime import datetime

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from django.contrib.postgres.search import SearchQuery, SearchHeadline, SearchVector

from cephalon.models import ProjectFile
from cephalon.schemas import FileSchema


@database_sync_to_async
def search_project_file(term: str):
    query = SearchQuery(term, search_type="websearch")
    files = ProjectFile.objects.annotate(
        search=SearchVector('content__data'),
        headline=SearchHeadline("content__data",
                                query,
                                start_sel="<b>", stop_sel="</b>")
    ).filter(search=query)

    return [FileSchema.from_orm(i).dict() for i in files]


class InterServerCommunicationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        print(self.scope)
        await self.channel_layer.group_add(self.interchange, self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.interchange, {
                'type': 'communication_message',
                'message': {
                    'message': f"welcome {self.server_id}",
                    'requestType': "welcome",
                    'senderID': "host",
                    'targetID': self.server_id,
                    'channelType': "initial",
                    'data': {}
                }
            })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.interchange, self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        await self.channel_layer.group_send(
            self.interchange,
            {
                'type': 'communication_message',
                'message': {
                    'message': data['message'],
                    'requestType': data['requestType'],
                    'senderID': data['senderID'],
                    'targetID': data['senderID'],
                    'channelType': "initial",
                    'data': {}
                }
            }
        )

    async def communication_message(self, event):
        data = event['message']
        print(self.scope)
        await self.send(text_data=json.dumps({
            'message': data['message'],
            'senderID': self.server_id,
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "initial",
            'data': data['data']
        }))


class SearchDataConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        await self.channel_layer.group_add(self.interchange+"_search", self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.interchange+"_search", {
                'type': 'communication_message',
                'message': {
                    'message': f"welcome {self.server_id}",
                    'requestType': "welcome",
                    'senderID': "host",
                    'targetID': self.server_id,
                    'channelType': "search",
                    'data': {}
                }
            })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.interchange+"_search", self.channel_name)
        pass

    async def receive_json(self, content, **kwargs):
        print(content)
        await self.channel_layer.group_send(
            self.interchange+"_search",
            {
                'type': 'communication_message',
                'message': {
                    'message': content['message'],
                    'requestType': content['requestType'],
                    'senderID': content['senderID'],
                    'targetID': content['senderID'],
                    'channelType': "search",
                    'data': {}
                }
            }
        )

    async def communication_message(self, event):
        data = event['message']
        await self.send_json({
            'message': data['message'],
            'senderID': self.server_id,
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "search",
            'data': data['data']
        })


class UserSendConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.client_id = self.scope['url_route']['kwargs']['client_id']

        await self.channel_layer.group_add(self.session_id+"_send", self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.session_id+"_send", {
                'type': 'communication_message',
                'message': {
                    'message': f"welcome {self.client_id}",
                    'requestType': "welcome",
                    'senderID': "host",
                    'targetID': self.client_id,
                    'channelType': "user-send",
                    'data': {}
                }
            })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.session_id+"_send", self.channel_name)

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        if data['requestType'] == "user-search-query":
            result = await search_project_file(data['message'])
            await self.channel_layer.group_send(
                self.session_id+"_result",
                {
                    'type': 'communication_message',
                    'message': {
                        'message': "Result found.",
                        'requestType': "user-result",
                        'senderID': "host",
                        'targetID': self.client_id,
                        'channelType': "user-result",
                        'data': result
                    }
                }
            )
        else:
            await self.channel_layer.group_send(
                self.session_id+"_send",
                {
                    'type': 'communication_message',
                    'message': {
                        'message': data['message'],
                        'requestType': data['requestType'],
                        'senderID': self.client_id,
                        'targetID': data['targetID'],
                        'channelType': "user-send",
                        'data': {}
                    }
                }
            )

    async def communication_message(self, event):
        data = event['message']
        await self.send(text_data=json.dumps({
            'message': data['message'],
            'senderID': data['senderID'],
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "user-send",
            'data': data['data']
        }))


class UserResultConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.client_id = self.scope['url_route']['kwargs']['client_id']

        await self.channel_layer.group_add(self.session_id+"_result", self.channel_name)
        await self.accept()
        await self.channel_layer.group_send(self.session_id+"_result", {
                'type': 'communication_message',
                'message': {
                    'message': f"welcome {self.client_id}",
                    'requestType': "welcome",
                    'senderID': "host",
                    'targetID': self.client_id,
                    'channelType': "user-result",
                    'data': {}
                }
            })


    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.session_id+"_result", self.channel_name)

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        await self.channel_layer.group_send(
            self.session_id+"_result",
            {
                'type': 'communication_message',
                'message': {
                    'message': data['message'],
                    'requestType': data['requestType'],
                    'senderID': self.client_id,
                    'targetID': data['targetID'],
                    'channelType': "user-result",
                    'data': {}
                }
            }
        )

    async def communication_message(self, event):
        data = event['message']
        await self.send(text_data=json.dumps({
            'message': data['message'],
            'senderID': data['senderID'],
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "user-result",
            'data': data['data']
        }))