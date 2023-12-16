import json
from datetime import datetime

from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer


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
                    'senderID': "host"
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
                    'targetID': data['senderID']
                }
            }
        )

    async def communication_message(self, event):
        data = event['message']
        print(self.scope)
        await self.send(text_data=json.dumps({
            'message': data['message'],
            'senderID': self.server_id,
            'requestType': data['requestType']
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
                    'senderID': "host"
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
                    'targetID': content['senderID']
                }
            }
        )

    async def communication_message(self, event):
        data = event['message']
        print(self.scope)
        await self.send_json({
            'message': data['message'],
            'senderID': self.server_id,
            'requestType': data['requestType']
        })