import json

import httpx
from django.core.management.base import BaseCommand
import websockets

import asyncio

from cephalon.models import ProjectFile
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
        async for websocket in websockets.connect(f"ws://{options['host']}:{options['port']}/ws/{channel_type}/{options['interchange']}/{options['server_id']}/", extra_headers={
            "Origin": f"http://{options['host']}:{options['port']}", "X-API-Key": options['api_key']
        }):
            current = CurrentCorpusX()
            try:
                async for message in websocket:
                    message = json.loads(message)
                    print(message)
                    if message["message"].startswith("welcome"):
                        corpusx_dict[channel_type] = RemoteCorpusX(f"http://{options['host']}:{options['port']}", options['api_key'])

                    if channel_type=="search":
                        if message["targetID"] == options["server_id"]:
                            test_p = await current.search(message["data"]["term"], message["data"]["description"])
                            await websocket.send(json.dumps({
                                "message": "Results found",
                                "requestType": "search-result",
                                "senderID": options["server_id"],
                                "targetID": "host",
                                "channelType": channel_type,
                                "sessionID": message["sessionID"],
                                "data": test_p,
                                "clientID": message["clientID"]
                            }))
                    elif channel_type=="file_request":
                        if message["targetID"] == options["server_id"]:
                            old_file = await ProjectFile.objects.aget(id=message["data"]["id"])
                            remote = RemoteCorpusX(f"http://{options['host']}:{options['port']}", options['api_key'])
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
        parser.add_argument('host', type=str, help='Host of the index server')
        parser.add_argument('port', type=str, help='Port of the index server')
        parser.add_argument('server_id', type=str, help='Server ID of the current server')
        parser.add_argument('interchange', type=str, help='Interchange name of the index server')
        parser.add_argument('api_key', type=str, help='API key of the index server')

    def handle(self, *args, **options):
        with httpx.Client(headers={"X-API-Key": options['api_key']}) as client:
            print(f"http://{options['host']}:{options['port']}/api/register_node")
            res = client.post(f"http://{options['host']}:{options['port']}/api/register_node", data={"node_name": options['server_id']})
            if res.status_code == 200:
                loop = asyncio.get_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.connect(options))
            else:
                print("Error registering node")