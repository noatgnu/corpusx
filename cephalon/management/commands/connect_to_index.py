import json
import os

import httpx
from django.core.management.base import BaseCommand
from websockets.sync.client import connect

from cephalon.models import Project, ProjectFile


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


class Command(BaseCommand):
    """
    A command to open a websocket connection to the index server.
    """
    def add_arguments(self, parser):
        parser.add_argument('host', type=str, help='Host of the index server')
        parser.add_argument('port', type=str, help='Port of the index server')
        parser.add_argument('server_id', type=str, help='Server ID of the current server')
        parser.add_argument('interchange', type=str, help='Interchange name of the index server')
        parser.add_argument('api_key', type=str, help='API key of the index server')

    def handle(self, *args, **options):
        with connect(f"ws://{options['host']}:{options['port']}/ws/interchange/{options['interchange']}/{options['server_id']}/", additional_headers={
            "Origin": f"http://{options['host']}:{options['port']}",
        }) as websocket:
            while True:
                message = input("Enter message: ")
                websocket.send(json.dumps({
                    "message": message,
                    "requestType": "test",
                    "senderID": options['server_id']
                }))
                result = websocket.recv()
                data = json.loads(result)
                print(data['message'])