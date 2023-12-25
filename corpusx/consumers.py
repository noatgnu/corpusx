import io
import json
from datetime import datetime
from io import BytesIO

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.files import File
from django.core.files.base import ContentFile
from django_rq import job

import httpx
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from django.contrib.postgres.search import SearchQuery, SearchHeadline, SearchVector

from cephalon.models import ProjectFile, Project, WebsocketSession, Pyre, WebsocketNode, APIKey, SearchResult
from cephalon.schemas import FileSchema, SearchResultSchema


class RemoteFileConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        self.current = CurrentCorpusX()
        await self.current.add_node_to_pyre(self.interchange, self.server_id, "file_request")
        await self.channel_layer.group_add(self.interchange+self.server_id+"_file_request", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.current.remove_node_from_pyre(self.interchange, self.server_id, "file_request")
        await self.channel_layer.group_discard(self.interchange+self.server_id+"_file_request", self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        self.current = CurrentCorpusX()
        nodes = await self.current.get_associated_nodes(self.interchange, "file_request")

        if data["requestType"] == "user-file-request":
            if nodes:
                for n in nodes:
                    await self.channel_layer.group_send(
                        self.interchange+n.name+"_file",
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
                                'sessionID': data["sessionID"],
                                'pyreName': self.interchange
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
                            'sessionID': data["sessionID"],
                            'pyreName': self.interchange
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
            'sessionID': data["sessionID"],
            'pyreName': self.interchange
        }))
class RemoteResultConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        self.current = CurrentCorpusX()
        await self.current.add_node_to_pyre(self.interchange, self.server_id, "result")
        await self.channel_layer.group_add(self.interchange+self.server_id+"_result", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.current.remove_node_from_pyre(self.interchange, self.server_id, "result")
        await self.channel_layer.group_discard(self.interchange+self.server_id+"_result", self.channel_name)
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
                    'data': data['data'],
                    'clientID': data["clientID"],
                    'sessionID': data["sessionID"],
                    'pyreName': self.interchange
                }
            }
        )

class InterServerCommunicationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interchange = self.scope['url_route']['kwargs']['interchange']
        self.server_id = self.scope['url_route']['kwargs']['server_id']
        self.current = CurrentCorpusX()
        await self.current.add_node_to_pyre(self.interchange, self.server_id, "interserver")
        await self.channel_layer.group_add(self.interchange+self.server_id, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.current.remove_node_from_pyre(self.interchange, self.server_id, "interserver")
        await self.channel_layer.group_discard(self.interchange+self.server_id, self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)

        await self.channel_layer.group_send(
            self.interchange+self.server_id,
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
        self.current = CurrentCorpusX()
        await self.current.add_node_to_pyre(self.interchange, self.server_id, "search")
        await self.channel_layer.group_add(self.interchange+self.server_id+"_search", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.current.remove_node_from_pyre(self.interchange, self.server_id, "search")
        await self.channel_layer.group_discard(self.interchange+self.server_id+"_search", self.channel_name)
        pass

    async def receive(self, text_data, **kwargs):
        data = json.loads(text_data)
        if data["requestType"] == "search":
            self.current = CurrentCorpusX()
            nodes = await self.current.get_associated_nodes(self.interchange, "search")
            if nodes:
                for n in nodes:
                    await self.channel_layer.group_send(
                        self.interchange+n+"_search",
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
                                'sessionID': data["sessionID"],
                                'pyreName': self.interchange
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
                        'sessionID': data["sessionID"],
                        'pyreName': self.interchange
                    }
                }
            )

    async def communication_message(self, event):
        data = event['message']
        await self.send_json({
            'message': data['message'],
            'senderID': data['senderID'],
            'requestType': data['requestType'],
            'targetID': data['targetID'],
            'channelType': "search",
            'data': data['data'],
            'clientID': data["clientID"],
            'sessionID': data["sessionID"],
            'pyreName': self.interchange
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
            current = CurrentCorpusX(perspective="host")
            current.search_enqueue.delay(current, data['data'], pyre_name=data['pyreName'], session_id=self.session_id, client_id=self.client_id)
            # result = await current.search(term=data['data']['term'], description=data['data']['description'], session_id=self.session_id, pyre_name=data['pyreName'])
            # if len(result) == 0:
            #     message = "No results found"
            # else:
            #     message = f"Results found {len(result)}"
            # await self.channel_layer.group_send(
            #     self.session_id+"_result",
            #     {
            #         'type': 'communication_message',
            #         'message': {
            #             'message': message,
            #             'requestType': "search",
            #             'senderID': "host",
            #             'targetID': self.client_id,
            #             'channelType': "user-result",
            #             'data': result,
            #             'sessionID': self.session_id,
            #             'clientID': self.client_id,
            #             'pyreName': data['pyreName'],
            #         }
            #     }
            # )

            self.current = CurrentCorpusX()
            nodes = await self.current.get_associated_nodes("public", "file_request")
            print(nodes)
            if nodes:
                for n in nodes:
                    await self.channel_layer.group_send("public"+n.name + "_search", {
                        'type': 'communication_message',
                        'message': {
                            'message': data['message'],
                            'requestType': data['requestType'],
                            'senderID': "host",
                            'targetID': n.name,
                            'channelType': "search",
                            'data': data['data'],
                            'clientID': self.client_id,
                            'sessionID': self.session_id,
                            'pyreName': data['pyreName'],
                        }
                    })
        elif data['requestType'] == "user-file-request":
            self.current = CurrentCorpusX()
            nodes = await self.current.get_associated_nodes("public", "file_request")
            for n in nodes:
                await self.channel_layer.group_send(
                    "public"+n.name+"_file_request", {
                        'type': 'communication_message',
                        'message': {
                            'message': data['message'],
                            'requestType': data['requestType'],
                            'senderID': "host",
                            'targetID': n.name,
                            'channelType': "file_request",
                            'data': data['data'],
                            'clientID': self.client_id,
                            'sessionID': self.session_id,
                            'pyreName': data['pyreName'],
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
                        'data': {},
                        'sessionID': self.session_id,
                        'clientID': self.client_id,
                        'pyreName': data['pyreName'],
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
            'data': data['data'],
            'sessionID': self.session_id,
            'clientID': self.client_id,
            'pyreName': data['pyreName'],
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
                    'data': {},
                    'sessionID': self.session_id,
                    'clientID': self.client_id,
                    'pyreName': "public",
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
                    'data': {},
                    'sessionID': self.session_id,
                    'clientID': self.client_id,
                    'pyreName': data['pyreName'],
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
            'data': data['data'],
            'sessionID': self.session_id,
            'clientID': self.client_id,
            'pyreName': data['pyreName'],
        }))


class CurrentCorpusX:

    def __init__(self, api_key: APIKey = None, session_id: str = None, client_id: str = None, pyre_name: str = None, perspective: str = 'host'):
        self.api_key = api_key
        self.session_id = session_id
        self.client_id = client_id
        self.pyre_name = pyre_name
        self.perspective = perspective

    @job
    def search_enqueue(self, query: dict, pyre_name: str = "", session_id: str = "", node_id: str = "", client_id: str = "", server_id: str = ""):
        data = async_to_sync(self.search)(query["term"], pyre_name, query["description"], session_id)
        grouped_data = {}
        for i in data:
            if i["id"] not in grouped_data:
                grouped_data[i["id"]] = []
            grouped_data[i["id"]].append(i)
        exported_data = [{"id": i, "data": grouped_data[i]} for i in grouped_data]
        json_data = json.dumps(exported_data)
        pyre = Pyre.objects.get(name=pyre_name)
        session = None
        if session_id:
            if self.perspective == "host":
                session = WebsocketSession.objects.get(session_id=session_id)
        node = None
        if node_id:
            if self.perspective == "host":
                node = WebsocketNode.objects.get(name=node_id)

        result = {}
        if len(data) == 0:
            message = "No results found"
        else:
            message = f"Results found {len(exported_data)}"
            data_file = SearchResult.objects.create(
                pyre=pyre,
                session=session,
                node=node,
                client_id=client_id,
                search_query=json.dumps(query),
                file=ContentFile(io.StringIO(json_data).read().encode(), name=f"{query['term']}.json"),
                search_status="complete"
            )
            data_file.update_hash()

            result = SearchResultSchema.from_orm(data_file).dict()
            if self.perspective == "node":
                result = async_to_sync(data_file.send_to_remote)(self.api_key, pyre_name, session_id, client_id, server_id)

        if session_id and client_id:
            if self.perspective == "host":
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(session_id + "_result", {
                        'type': 'communication_message',
                        'message': {
                            'message': message,
                            'requestType': "search",
                            'senderID': "host",
                            'targetID': client_id,
                            'channelType': "user-result",
                            'data': result,
                            'sessionID': session_id,
                            'clientID': client_id,
                            'pyreName': pyre_name,
                        }
                    })
            # elif self.perspective == "node" and websocket and server_id:
            #
            #     async_to_sync(websocket.send)(json.dumps({
            #         'message': message,
            #         'requestType': "search-result",
            #         'senderID': server_id,
            #         'targetID': "host",
            #         'channelType': "search",
            #         'data': result,
            #         'sessionID': session_id,
            #         'clientID': client_id,
            #         'pyreName': pyre_name,
            #     }))
        return json_data

    @database_sync_to_async
    def search(self, term: str, pyre_name: str = "", description: str = "", session_id: str = ""):
        query = SearchQuery(term, search_type="phrase")
        if self.api_key:
            files = self.api_key.get_all_files().all()
        elif pyre_name != "":
            pyre = Pyre.objects.get(name=pyre_name)
            files = pyre.get_all_files()
        else:
            files = ProjectFile.objects.all()

        files = files.filter(content__search_vector=query).annotate(headline=SearchHeadline('content__data', query, start_sel="<b>", stop_sel="</b>")).distinct()
        if description != '':
            files = files.filter(description__icontains=description)
        if self.perspective == "host":
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

    @database_sync_to_async
    def add_node_to_pyre(self, pyre_name: str, node_name: str, channel_name: str):
        pyre = Pyre.objects.get(name=pyre_name)
        node = WebsocketNode.objects.get(name=node_name)
        if channel_name == "file_request":

            if node not in pyre.file_request_channel_connected_nodes.all():
                pyre.file_request_channel_connected_nodes.add(node)
        elif channel_name == "search":
            if node not in pyre.search_data_channel_connected_nodes.all():
                pyre.search_data_channel_connected_nodes.add(node)
        elif channel_name == "result":
            if node not in pyre.result_channel_connected_nodes.all():
                pyre.result_channel_connected_nodes.add(node)
        elif channel_name == "interserver":
            if node not in pyre.interserver_channel_connected_nodes.all():
                pyre.interserver_channel_connected_nodes.add(node)
        pyre.save()
        print(f"Added {node} to {pyre} {channel_name}")

    @database_sync_to_async
    def remove_node_from_pyre(self, pyre_name: str, node_name: str, channel_name: str):
        pyre = Pyre.objects.get(name=pyre_name)
        node = WebsocketNode.objects.get(name=node_name)
        if channel_name == "file_request":
            if node in pyre.file_request_channel_connected_nodes.all():
                pyre.file_request_channel_connected_nodes.remove(node)
        elif channel_name == "search":
            if node in pyre.search_data_channel_connected_nodes.all():
                pyre.search_data_channel_connected_nodes.remove(node)
        elif channel_name == "result":
            if node in pyre.result_channel_connected_nodes.all():
                pyre.result_channel_connected_nodes.remove(node)
        elif channel_name == "interserver":
            if node in pyre.interserver_channel_connected_nodes.all():
                pyre.interserver_channel_connected_nodes.remove(node)
        pyre.save()

    @database_sync_to_async
    def get_associated_nodes(self, pyre_name: str, channel_name: str) -> list[WebsocketNode]|None:
        pyre = Pyre.objects.get(name=pyre_name)
        if channel_name == "file_request":
            nodes = list(pyre.file_request_channel_connected_nodes.all())
        elif channel_name == "search":
            nodes = list(pyre.search_data_channel_connected_nodes.all())
        elif channel_name == "result":
            nodes = list(pyre.result_channel_connected_nodes.all())
        elif channel_name == "interserver":
            nodes = list(pyre.interserver_channel_connected_nodes.all())
        else:
            nodes = []
        return nodes

    @job
    def upload_project_file(self, file: ProjectFile, session_id, client_id, pyre_name, server_id):
        file = async_to_sync(file.send_to_remote)(self.api_key)
        httpx.post(f"{self.api_key.remote_pair.protocol}://{self.api_key.remote_pair.hostname}:{self.api_key.remote_pair.port}/api/notify/file_upload_completed/{session_id}/{client_id}", data={
            "file_id": file["id"],
            "pyre_name": pyre_name,
            "server_id": server_id,
            "old_file": FileSchema.from_orm(file).dict()
        })
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
        d = await self.client.post(f"{self.url}/api/files/chunked", data={
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