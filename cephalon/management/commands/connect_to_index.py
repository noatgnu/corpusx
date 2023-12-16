import json

import httpx
from channels.db import database_sync_to_async
from django.contrib.postgres.search import SearchVector, SearchHeadline, SearchQuery
from django.core.management.base import BaseCommand
import websockets

from cephalon.models import Project, ProjectFile
import asyncio

from cephalon.schemas import FileSchema


class RemoteCorpusX:
    def __init__(self, url: str, api_key: str):
        self.url = url
        self.api_key = api_key
        self.client = httpx.Client(headers={"X-API-Key": f"{self.api_key}"})

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

    def upload_chunked_file(self, file: ProjectFile, project: Project):
        d = self.client.post(f"{self.url}/api/files/chunked", json={
                        "filename": file.name,
                        "size": file.file.size,
                        "data_hash": file.hash,
                        "file_category": file.file_category
                    })
        d = d.json()
        with open(file.file.path, "rb") as f:
            while True:
                chunk = f.read(d.json()["chunk_size"])
                if not chunk:
                    break

class CurrentCorpusX:
    @database_sync_to_async
    def search(self, term: str):
        query = SearchQuery(term, search_type="phrase")
        files = ProjectFile.objects.annotate(
            search=SearchVector('content__data'),
            headline=SearchHeadline("content__data",
                                    query,
                                    start_sel="<b>", stop_sel="</b>")
        ).filter(search=query)

        return [FileSchema.from_orm(i).dict() for i in files]

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
                    if message["message"].startswith("welcome"):
                        corpusx_dict[channel_type] = RemoteCorpusX(f"http://{options['host']}:{options['port']}", options['api_key'])
                        await websocket.send(json.dumps({
                            "message": "hello",
                            "requestType": "hello",
                            "senderID": options["server_id"],
                            "targetID": "host"
                        }))

                    if channel_type=="search":
                        test_p = await current.search("lrrk2")
                        await websocket.send(json.dumps({
                            "message": test_p,
                            "requestType": "search",
                            "senderID": options["server_id"],
                            "targetID": "host"
                        }))
                        if message["targetID"] == options["server_id"]:
                            if message["requestType"] == "search":
                                current.search(message["message"])

                    print(message)
            except websockets.ConnectionClosed:
                continue
    async def connect(self, options):
        await asyncio.gather(self.connect_to_server(options, channel_type="initial"), self.connect_to_server(options, channel_type="search"))

    def add_arguments(self, parser):
        parser.add_argument('host', type=str, help='Host of the index server')
        parser.add_argument('port', type=str, help='Port of the index server')
        parser.add_argument('server_id', type=str, help='Server ID of the current server')
        parser.add_argument('interchange', type=str, help='Interchange name of the index server')
        parser.add_argument('api_key', type=str, help='API key of the index server')

    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.connect(options))