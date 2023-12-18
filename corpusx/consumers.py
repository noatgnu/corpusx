import json
from datetime import datetime
from io import BytesIO

import httpx
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from django.contrib.postgres.search import SearchQuery, SearchHeadline, SearchVector

from cephalon.models import ProjectFile, Project, WebsocketSession
from cephalon.schemas import FileSchema


class RemoteFileConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        await self.channel_layer.group_add(self.interchange+"_file_request", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.interchange+"_file_request", self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        if data["requestType"] == "user-file-request":
            await self.channel_layer.group_send(
                self.interchange+"_file",
                {
                    'type': 'communication_message',
                    'message': {
                        'message': data['message'],
                        'requestType': data['requestType'],
                        'senderID': data['senderID'],
                        'targetID': data['targetID'],
                        'channelType': "file",
                        'data': data['data'],
                        'clientID': data["clientID"],
                        'sessionID': data["sessionID"]
                    }
                }
            )
        elif data["requestType"] == "file-upload":
            if data["data"]:
                current = CurrentCorpusX()
                file = await current.add_file(data["data"][1]["id"], data["sessionID"])
                data["data"][1] = FileSchema.from_orm(file).dict()
                await self.channel_layer.group_send(
                    data["sessionID"]+"_result",
                    {
                        'type': 'communication_message',
                        'message': {
                            'message': data['message'],
                            'requestType': data['requestType'],
                            'senderID': data['senderID'],
                            'targetID': data['clientID'],
                            'channelType': "result",
                            'data': data['data'],
                            'clientID': data["clientID"],
                            'sessionID': data["sessionID"]
                        }
                    }
                )

    async def communication_message(self, event):
        data = event['message']
        print(data)
        await self.send(text_data=json.dumps({
            'message': data['message'],
            'senderID': data['senderID'],
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "file",
            'data': data['data'],
            'clientID': data["clientID"],
            'sessionID': data["sessionID"]
        }))
class RemoteResultConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        await self.channel_layer.group_add(self.interchange+"_result", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.interchange+"_result", self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        await self.channel_layer.group_send(
            data["sessionID"]+"_result",
            {
                'type': 'communication_message',
                'message': {
                    'message': data['message'],
                    'requestType': data['requestType'],
                    'senderID': data['senderID'],
                    'targetID': data['clientID'],
                    'channelType': "result",
                    'data': data['data']
                }
            }
        )

class InterServerCommunicationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        print(self.scope)
        await self.channel_layer.group_add(self.interchange, self.channel_name)
        await self.accept()

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

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.interchange+"_search", self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        if data["requestType"] == "search":
            await self.channel_layer.group_send(
                self.interchange+"_search",
                {
                    'type': 'communication_message',
                    'message': {
                        'message': data['message'],
                        'requestType': data['requestType'],
                        'senderID': "host",
                        'targetID': "test_server",
                        'channelType': "search",
                        'data': data['data'],
                        'clientID': data["clientID"],
                        'sessionID': data["sessionID"]
                    }
                }
            )
        elif data["requestType"] == "search-result":
            await self.channel_layer.group_send(
                data["sessionID"]+"_result",
                {
                    'type': 'communication_message',
                    'message': {
                        'message': data['message'],
                        'requestType': data['requestType'],
                        'senderID': data['senderID'],
                        'targetID': data['clientID'],
                        'channelType': "user-result",
                        'data': data['data'],
                        'clientID': data["clientID"],
                        'sessionID': data["sessionID"]
                    }
                }
            )

    async def communication_message(self, event):
        data = event['message']
        print(data)
        await self.send_json({
            'message': data['message'],
            'senderID': data['senderID'],
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "search",
            'data': data['data'],
            'clientID': data["clientID"],
            'sessionID': data["sessionID"]
        })


class UserSendConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.client_id = self.scope['url_route']['kwargs']['client_id']

        await self.channel_layer.group_add(self.session_id+"_send", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.session_id+"_send", self.channel_name)

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        if data['requestType'] == "user-search-query":
            current = CurrentCorpusX()

            result = await current.search(data['data']['term'], data['data']['description'], self.session_id)

            await self.channel_layer.group_send(
                self.session_id+"_result",
                {
                    'type': 'communication_message',
                    'message': {
                        'message': "Result found.",
                        'requestType': "search",
                        'senderID': "host",
                        'targetID': self.client_id,
                        'channelType': "user-result",
                        'data': result,
                        'sessionID': self.session_id
                    }
                }
            )
            await self.channel_layer.group_send("public" + "_search", {
                'type': 'communication_message',
                'message': {
                    'message': data['message'],
                    'requestType': data['requestType'],
                    'senderID': "host",
                    'targetID': "test_server",
                    'channelType': "search",
                    'data': data['data'],
                    'clientID': self.client_id,
                    'sessionID': self.session_id
                }
            })
        elif data['requestType'] == "user-file-request":
            await self.channel_layer.group_send(
                "public"+"_file_request", {
                    'type': 'communication_message',
                    'message': {
                        'message': data['message'],
                        'requestType': data['requestType'],
                        'senderID': "host",
                        'targetID': "test_server",
                        'channelType': "file_request",
                        'data': data['data'],
                        'clientID': self.client_id,
                        'sessionID': self.session_id
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
        current = CurrentCorpusX()
        await current.remove_session(self.session_id)
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


class CurrentCorpusX:
    @database_sync_to_async
    def search(self, term: str, description: str = "", session_id: str = ""):
        query = SearchQuery(term, search_type="phrase")
        files = ProjectFile.objects.annotate(
            search=SearchVector('content__data'),
            headline=SearchHeadline("content__data",
                                    query,
                                    start_sel="<b>", stop_sel="</b>")
        ).filter(search=query)
        if description != '':
            files = files.filter(description__icontains=description)
        if session_id != '':
            ws = WebsocketSession.objects.get(session_id=session_id)
            ws.files.set(files)
            ws.save()
        return [FileSchema.from_orm(i).dict() for i in files]

    @database_sync_to_async
    def remove_session(self, session_id: str):
        ws = WebsocketSession.objects.get(session_id=session_id)
        ws.delete()

    @database_sync_to_async
    def add_file(self, file_id: int, session_id: str):
        file = ProjectFile.objects.get(id=file_id)
        ws = WebsocketSession.objects.get(session_id=session_id)
        ws.files.add(file)
        ws.save()
        return file

class RemoteCorpusX:
    def __init__(self, url: str, api_key: str):
        self.url = url
        self.api_key = api_key
        self.client = httpx.AsyncClient(headers={"X-API-Key": f"{self.api_key}"})

    def create_project(self, project: Project):
        project = self.client.post(f"{self.url}/api/projects")
        return project

    def update_project(self, project: Project):
        project = self.client.patch(f"{self.url}/api/projects/{project.id}", json=project)
        return project

    def get_project(self, project_id: int):
        project = self.client.get(f"{self.url}/api/projects/{project_id}")
        return project

    def list_projects(self):
        projects = self.client.get(f"{self.url}/api/projects")
        return projects

    async def upload_chunked_file(self, file: ProjectFile, project: Project = None):
        d = await self.client.post(f"{self.url}/api/files/chunked", json={
                        "filename": file.name,
                        "size": file.file.size,
                        "data_hash": file.hash,
                        "file_category": file.file_category
                    })
        upload_id = d.json()["upload_id"]
        with open(file.file.path, "rb") as f:
            offset = 0
            while True:
                chunk = f.read(d.json()["chunk_size"])
                if not chunk:
                    break
                chunk_file = BytesIO(chunk)
                progress = await self.client.post(f"{self.url}/api/files/chunked/{upload_id}",
                                             data={"offset": offset}, files={"chunk": chunk_file})
                if progress.json()["status"] == "complete":
                    break
                else:
                    offset = progress.json()["offset"]
            result = await self.client.post(f"{self.url}/api/files/chunked/{upload_id}/complete", json={"create_file": True})
            return result.json()