import json

import httpx
from django.core.management.base import BaseCommand
import websockets

import asyncio

from cephalon.models import ProjectFile, APIKeyRemote, APIKey
from cephalon.schemas import FileSchema
from corpusx.consumers import CurrentCorpusX, RemoteCorpusX

corpusx_dict = {
    "send": RemoteCorpusX("http://localhost:8000", "test"),
    "receive": RemoteCorpusX("http://localhost:8001", "test")
}


class Command(BaseCommand):
    """
    A command to open a websocket connection to the index server.
    """


    async def connect_to_server(self, options, channel_type="initial"):
        async for websocket in websockets.connect(f"{self.protocol.replace('http', 'ws')}://{self.hostname}:{self.port}/ws/{channel_type}/{options['interchange']}/{options['server_id']}/", extra_headers={
            "Origin": f"{self.protocol}://{self.hostname}:{self.port}",
            "X-API-Key": self.decoded_api_key
        }):
            current = CurrentCorpusX(self.api_key, perspective="node")
            try:
                async for message in websocket:
                    message = json.loads(message)
                    print(message)
                    if message["message"].startswith("welcome"):
                        corpusx_dict[channel_type] = RemoteCorpusX(f"{self.protocol}://{self.hostname}:{self.port}", self.decoded_api_key)

                    if channel_type=="search":
                        if message["targetID"] == options["server_id"]:
                            current.search_enqueue.delay(
                                current,
                                query=message["data"],
                                pyre_name=message["pyreName"],
                                session_id=message["sessionID"],
                                node_id=options["server_id"],
                                client_id=message["clientID"], server_id=options["server_id"])
                            # test_p = await current.search(term=message["data"]["term"], description=message["data"]["description"])
                            # print(test_p)
                            # if len(test_p) == 0:
                            #     await websocket.send(json.dumps({
                            #         "message": "No results found",
                            #         "requestType": "search-result",
                            #         "senderID": options["server_id"],
                            #         "targetID": "host",
                            #         "channelType": channel_type,
                            #         "sessionID": message["sessionID"],
                            #         "data": [],
                            #         "clientID": message["clientID"]
                            #     }))
                            # else:
                            #     await websocket.send(json.dumps({
                            #         "message": f"Results found {len(test_p)}",
                            #         "requestType": "search-result",
                            #         "senderID": options["server_id"],
                            #         "targetID": "host",
                            #         "channelType": channel_type,
                            #         "sessionID": message["sessionID"],
                            #         "data": test_p,
                            #         "clientID": message["clientID"]
                            #     }))
                    elif channel_type=="file_request":
                        if message["targetID"] == options["server_id"]:
                            old_file = await ProjectFile.objects.aget(id=message["data"]["id"])
                            remote = RemoteCorpusX(f"{self.protocol}://{self.hostname}:{self.port}", self.decoded_api_key)
                            file = await remote.upload_chunked_file(old_file)
                            await websocket.send(json.dumps({
                                "message": "File uploaded",
                                "requestType": "file-upload",
                                "senderID": options["server_id"],
                                "targetID": "host",
                                "channelType": channel_type,
                                "sessionID": message["sessionID"],
                                "data": [FileSchema.from_orm(old_file).dict(), file],
                                "clientID": message["clientID"]
                            }))

            except websockets.ConnectionClosed:
                continue
    async def connect(self, options):
        await asyncio.gather(self.connect_to_server(options, channel_type="initial"), self.connect_to_server(options, channel_type="search"), self.connect_to_server(options, channel_type="file_request"))

    def add_arguments(self, parser):
        #parser.add_argument('host', type=str, help='Host of the index server')
        #parser.add_argument('port', type=str, help='Port of the index server')
        parser.add_argument('server_id', type=str, help='Server ID of the current server')
        parser.add_argument('interchange', type=str, help='Interchange name of the index server')
        #parser.add_argument('api_key', type=str, help='API key of the index server')
        parser.add_argument('api_key_name', type=str, help='Stored API key name')

    def handle(self, *args, **options):
        # with httpx.Client(headers={"X-API-Key": options['api_key']}) as client:
        #     print(f"http://{options['host']}:{options['port']}/api/register_node")
        #     res = client.post(f"http://{options['host']}:{options['port']}/api/register_node", data={"node_name": options['server_id']})
        #     if res.status_code == 200:
        #         loop = asyncio.get_event_loop()
        #         asyncio.set_event_loop(loop)
        #         loop.run_until_complete(self.connect(options))
        #     else:
        #         print("Error registering node")
        self.api_key = APIKey.objects.get(name=options["api_key_name"])
        self.remote_api_key = self.api_key.remote_pair
        self.protocol = self.remote_api_key.protocol
        self.hostname = self.remote_api_key.hostname
        self.port = self.remote_api_key.port
        self.decoded_api_key = self.api_key.decrypt_remote_api_key()

        with httpx.Client(headers={"X-API-Key": self.decoded_api_key}) as client:
            res = client.post(f"{self.remote_api_key.protocol}://{self.remote_api_key.hostname}:{self.remote_api_key.port}/api/register_node", data={"node_name": options['server_id']})
            if res.status_code == 200:
                loop = asyncio.get_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.connect(options))
            else:
                print("Error registering node")