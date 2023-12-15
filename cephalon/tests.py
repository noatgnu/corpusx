import json
import httpx
from django.core.files.base import ContentFile
from django.test import TestCase, Client
from django.test.client import MULTIPART_CONTENT, encode_multipart, BOUNDARY
from django.contrib.auth.models import User

import hashlib
# Create your tests here.

def add_test_user():
    user = User.objects.get_or_create(username="testuser")
    user = user[0]
    user.set_password("testpassword")
    user.save()
    return user

class ProjectModelTestCase(TestCase):
    def setUp(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})

    def test_project_model_upload(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})
        d = self.client.post('/api/projects', {"name": "test", "description": "test", "hash": "test", "metadata": {}, "global_id": "test"}, content_type="application/json")
        assert d.status_code == 200
        assert d.json()["name"] == "test"
        assert d.json()["description"] == "test"
        assert d.json()["hash"] == "test"
        assert d.json()["metadata"] == {}
        assert d.json()["global_id"] == "test"
        assert d.json()["id"] != None


class FileModelTestCase(TestCase):
    def setUp(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})
        self.d = self.add_test_project()

    def test_file_model_upload(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})
        filecontent = b"test"
        file = ContentFile(filecontent, name="test.tsv")
        hasher = hashlib.sha1()
        for chunk in iter(lambda: file.read(4096), b""):
            hasher.update(chunk)
        file.seek(0)
        hash = hasher.hexdigest()
        e = self.client.post(
            f'/api/projects/{self.d.json()["id"]}/files',
            {"description": "test", "hash": hash, "metadata": json.dumps(dict(test="test")), "file_type": "tsv", "file": file, "file_category": "other"},
            content_type=MULTIPART_CONTENT,
        )
        print(e.content)
        assert e.status_code == 200
        assert e.json()["name"] == "test.tsv"
        assert e.json()["description"] == "test"
        assert e.json()["hash"] == hash
        assert e.json()["metadata"] == {"test": "test"}
        assert e.json()["file_type"] == "tsv"
        assert e.json()["id"] != None

    def add_test_project(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})
        d = self.client.post('/api/projects', {"name": "test", "description": "test", "hash": "test", "metadata": {},
                                               "global_id": "test"}, content_type="application/json")
        assert d.status_code == 200
        assert d.json()["name"] == "test"
        assert d.json()["description"] == "test"
        assert d.json()["hash"] == "test"
        assert d.json()["metadata"] == {}
        assert d.json()["global_id"] == "test"
        assert d.json()["id"] != None
        return d

class ChunkedUploadTestCase(TestCase):
    def setUp(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})

    def test_chunked_upload(self):
        user = add_test_user()
        self.client = Client(headers={"AUTHORIZATION": f"Bearer {user.auth_token.key}"})
        filecontent = b"test"
        file = ContentFile(filecontent, name="test.tsv")
        hasher = hashlib.sha1()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
        file.seek(0)
        hash = hasher.hexdigest()
        # initiate chunked upload
        d = self.client.post(f'/api/files/chunked', {"file_category": "other", "filename": "test.tsv", "size": len(filecontent), "data_hash": hash}, content_type="application/json")
        assert d.status_code == 200
        assert d.json()["filename"] == "test.tsv"
        assert d.json()["total_size"] == len(filecontent)
        assert d.json()["upload_id"] != None
        assert d.json()["offset"] == 0
        assert d.json()["chunk_size"] == 1024 * 1024
        assert d.json()["status"] == "pending"
        assert d.json()["file_id"] == None

        # upload chunks
        offset = 0
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            c = ContentFile(chunk, name="test.tsv")
            e = self.client.post(f'/api/files/chunked/{d.json()["upload_id"]}', {"offset": offset, "chunk": c}, content_type=MULTIPART_CONTENT)
            assert e.status_code == 200
            assert e.json()["filename"] == "test.tsv"
            assert e.json()["total_size"] == len(filecontent)
            assert e.json()["upload_id"] != None
            assert e.json()["offset"] == offset + len(chunk)
            if e.json()["status"] == "complete":
                assert e.json()["total_size"] == e.json()["offset"]
            else:
                offset = e.json()["offset"]
