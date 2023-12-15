import json
from datetime import datetime

from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer


class InterServerCommunicationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        await self.channel_layer.group_add(self.interchange, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.interchange, self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        print(self.interchange)
        await self.channel_layer.group_send(
            self.interchange,
            {
                'type': 'communication_message',
                'message': {
                    'message': data['message'],
                    'requestType': data['requestType'],
                    'senderID': data['senderName']
                }
            }
        )

    async def communication_message(self, event):
        data = event['message']
        await self.send(text_data=json.dumps({
            'message': data['message'],
            'senderID': self.server_id,
            'requestType': data['requestType']
        }))
