import re
import uuid
from io import BytesIO

import httpx
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVectorField, SearchVector
from django.contrib.postgres.indexes import GinIndex
from cephalon.utils import create_signed_token, decode_signed_token, create_api_key, verify_api_key
from django.conf import settings
import hashlib

# Create your models here.
class Project(models.Model):
    """
    A Model to store project data
    """
    name = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    hash = models.TextField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    global_id = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    temporary = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects", blank=True, null=True)
    encrypted = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created_at} {self.description}"

    def __repr__(self):
        return f"{self.name} {self.created_at}"

    def calculate_project_hash(self):
        hasher = hashlib.sha1()
        for file in self.files.all():
            with open(file.file.path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
        return hasher.hexdigest()

    def update_project_hash(self):
        self.hash = self.calculate_project_hash()
        self.save()


class ProjectFile(models.Model):
    """
    A model to store file data
    """
    name = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    hash = models.TextField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    path = models.JSONField(blank=True, null=True)
    file_type_choices = [
        ("csv", "csv"),
        ("tsv", "tsv"),
        ("txt", "tabulated text"),
        ("json", "json"),
        ("other", "other")
    ]
    file_type = models.CharField(max_length=5, choices=file_type_choices, default="tsv")
    file_category_choices = [
        ("unprocessed", "unprocessed"),
        ("searched", "searched"),
        ("differential_analysis", "differential_analysis"),
        ("sample_annotation", "sample_annotation"),
        ("comparison_matrix", "comparison_matrix"),
        ("other", "other")
        ]
    file_category = models.CharField(max_length=30, choices=file_category_choices, default="other")
    file = models.FileField(upload_to="cephalon/files/", blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files", blank=True, null=True)
    load_file_content = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created_at} {self.description}"

    def __repr__(self):
        return f"{self.name} {self.created_at}"

    def delete(self, using=None, keep_parents=False):
        self.file.delete()
        super().delete(using=using, keep_parents=keep_parents)

    def save(self, *args, **kwargs):
        # calculate sha1 hash of file
        return super().save(*args, **kwargs)

    def save_altered(self, *args, **kwargs):
        # calculate sha1 hash of file
        if self.file:
            hasher = hashlib.sha1()
            with open(self.file.path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            hash = hasher.hexdigest()
            if hash != self.hash:
                self.hash = hash
                if self.load_file_content:
                    self.load_file()

        return super().save(*args, **kwargs)

    def load_file(self):
        with open(self.file.path, "rt") as f:
            content = f.read()
            content = re.split(r"[\s\n\t]", content)
            # segment file content into chunks ensure that the segment won't cut off a word by 200*200 words
            for i in range(0, len(content), 200 * 200):
                if i + 200 * 200 > len(content):
                    ProjectFileContent.objects.create(project_file=self, data=" ".join(content[i:]))
                else:
                    ProjectFileContent.objects.create(project_file=self, data=" ".join(content[i:i + 200 * 200]))

    def remove_file_content(self):
        self.content.all().delete()

    def check_file_permission(self, api_key=None):
        if api_key.access_all:
            return True
        else:
            project_access = api_key.access_topics.all().values_list("projects", flat=True)
            if self.project.id in project_access:
                return True
            else:
                return False

    async def send_to_remote(self, api_key):
        """
        a method to send file to remote server
        """
        if self.check_file_permission(api_key):
            file = await self.upload_chunked_file(api_key)
            return file
        else:
            return None


    async def upload_chunked_file(self, api_key):
        decoded_api_key = api_key.decrypt_remote_api_key()
        host = f"{api_key.remote_pair.protocol}://{api_key.remote_pair.hostname}:{api_key.remote_pair.port}"
        async with httpx.AsyncClient(headers={"X-API-Key": decoded_api_key}) as client:
            d = await client.post(f"{host}/api/files/chunked", json={
                            "filename": self.name,
                            "size": self.file.size,
                            "data_hash": self.hash,
                            "file_category": self.file_category
                        })
            upload_id = d.json()["upload_id"]
            with self.file.open("rb") as f:
                offset = 0
                while True:
                    chunk = f.read(d.json()["chunk_size"])
                    if not chunk:
                        break
                    chunk_file = BytesIO(chunk)
                    progress = await client.post(f"{host}/api/files/chunked/{upload_id}",
                                                 data={"offset": offset}, files={"chunk": chunk_file})
                    if progress.json()["status"] == "complete":
                        break
                    else:
                        offset = progress.json()["offset"]
                result = client.post(f"{host}/api/files/chunked/{upload_id}/complete", json={"create_file": True})
                return result.json()


class ProjectFileContent(models.Model):
    """
    A model to store data of textfiles directly in the database
    """
    data = models.TextField(blank=True, null=True)
    project_file = models.ForeignKey(ProjectFile, on_delete=models.CASCADE, related_name="content", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    search_vector = SearchVectorField(null=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"
        indexes = [
            GinIndex(fields=["search_vector"])
        ]

    def __str__(self):
        return f"Content of {self.project_file.name} {self.created_at}"

    def __repr__(self):
        return f"Content of {self.project_file.name} {self.created_at}"


class Token(models.Model):
    """
    A model to store user unique auth token
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_token")
    name = models.TextField(blank=True, null=True)
    key = models.TextField(unique=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.user.username} {self.created}"

    def __repr__(self):
        return f"{self.user.username} {self.created}"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    def generate_key(self) -> str:
        return create_signed_token({"username": self.user.username}, settings.SECRET_KEY)

    def verify_key(self, key: str) -> bool:
        if key == self.key:
            try:
                payload = decode_signed_token(key, settings.SECRET_KEY)
                if payload["username"] == self.user.username:
                    return True
                else:
                    return False
            except Exception as e:
                return False
        else:
            return False

class APIKey(models.Model):
    """
    A model to store API keys generated for other apps or users to communicate to this instance
    """
    name = models.TextField(blank=True, null=True)
    key = models.TextField(unique=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    expiry = models.DateTimeField(blank=True, null=True)
    expired = models.BooleanField(default=False)
    public_key = models.TextField(blank=True, null=True)
    access_all = models.BooleanField(default=False)
    access_topics = models.ManyToManyField("Topic", blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys", blank=True, null=True)
    project = models.ManyToManyField(Project, blank=True)
    pyres = models.ManyToManyField("Pyre", blank=True)
    remote_pair = models.OneToOneField("APIKeyRemote", on_delete=models.CASCADE, related_name="local_pair", blank=True, null=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created}"

    def __repr__(self):
        return f"{self.name} {self.created}"

    def verify_key(self, key: str) -> bool:
        return verify_api_key(key, self.key)

    def create_api_key(self):
        key = create_api_key()
        self.key = key[0]
        self.save()
        return key[1]

    def receive_remote_api_key(self, key: str):
        encrypted_key = create_signed_token({"key": key}, settings.SECRET_KEY)
        self.remote_pair = APIKeyRemote.objects.create(key=encrypted_key, hostname="localhost", protocol="http", port=8000)

    def decrypt_remote_api_key(self):
        return decode_signed_token(self.remote_pair.key, settings.SECRET_KEY)["key"]

    def get_associated_projects(self):
        """
        a method to get a list of all projects that this api key has access to also add project that is not directly associated to the key but is available through a topic
        """
        projects = self.project.all()
        for topic in self.access_topics.all():
            projects = projects.union(topic.projects.all())
        return projects

    def get_all_files(self):
        """
        a method to get a list of all files that this api key has access to also add files that is not directly associated to the key but is available through a topic
        """
        projects = self.get_associated_projects().values_list("id", flat=True)
        files = ProjectFile.objects.filter(project_id__in=projects)
        return files


class APIKeyRemote(models.Model):
    """
    A model to store API keys generated for this instance to communicate to other instances
    """
    name = models.TextField(blank=True, null=True)
    key = models.TextField(unique=True)
    created = models.DateTimeField(auto_now_add=True)
    hostname = models.TextField(blank=True, null=True)
    protocol = models.TextField(blank=True, null=True)
    port = models.IntegerField(blank=True, null=True)


    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created} for {self.hostname}"

    def __repr__(self):
        return f"{self.name} {self.created} for {self.hostname}"



class ChunkedUpload(models.Model):
    """
    A model to store chunked file uploads set default chunk size to 1megabyte
    """
    upload_id = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    filename = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to="cephalon/files/chunks/", blank=True, null=True)
    offset = models.BigIntegerField(default=0)
    hash = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_category = models.TextField(blank=True, null=True)
    chunk_size = models.BigIntegerField(default=1024 * 1024)
    total_size = models.BigIntegerField(blank=True, null=True)
    status_choices = [
        ("pending", "pending"),
        ("in_progress", "in_progress"),
        ("complete", "complete"),
    ]
    status = models.CharField(max_length=11, choices=status_choices, default="pending")

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.filename} {self.created_at}"

    def __repr__(self):
        return f"{self.filename} {self.created_at}"

    def delete(self, using=None, keep_parents=False):
        self.file.delete()
        super().delete(using=using, keep_parents=keep_parents)

class Topic(models.Model):
    """
    A model to store the topic or category of a project. One project can be in multiple topics and one topic can have multiple projects. Project can be also used to set permissions for user or api access through topics.
    """
    name = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    projects = models.ManyToManyField(Project, blank=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created_at}"

    def __repr__(self):
        return f"{self.name} {self.created_at}"

class Pyre(models.Model):
    """
    A model to store the name of the websocket interchange that can be used to connect to this server
    """
    name = models.TextField(unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_request_channel_connected_nodes = models.ManyToManyField("WebsocketNode", related_name="file_request_channel", blank=True)
    result_request_channel_connected_nodes = models.ManyToManyField("WebsocketNode", related_name="result_request_channel", blank=True)
    interserver_channel_connected_nodes = models.ManyToManyField("WebsocketNode", related_name="interserver_channel", blank=True)
    search_data_channel_connected_nodes = models.ManyToManyField("WebsocketNode", related_name="search_data_channel", blank=True)
    topics = models.ManyToManyField("Topic", blank=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created_at}"

    def __repr__(self):
        return f"{self.name} {self.created_at}"

    def get_associated_projects(self):
        """
        a method to get a list of all projects that this pyre has access to also add project that is not directly associated to the pyre but is available through a topic
        """
        projects = self.topics.all().values_list("projects", flat=True)
        return projects

    def get_all_files(self):
        """
        a method to get a list of all files that this pyre has access to also add files that is not directly associated to the pyre but is available through a topic
        """
        projects = self.get_associated_projects()
        files = ProjectFile.objects.filter(project_id__in=projects)
        return files


class WebsocketNode(models.Model):
    """
    A model to store the websocket node that is connected to this server
    """
    name = models.TextField(unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True),
    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name="websocket_nodes", blank=True, null=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.name} {self.created_at}"

    def __repr__(self):
        return f"{self.name} {self.created_at}"

class WebsocketSession(models.Model):
    """
    A model to store and associate websocket sessions with users
    """
    session_id = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="websocket_sessions", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed = models.BooleanField(default=True)
    files = models.ManyToManyField(ProjectFile, blank=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.session_id} {self.user} {self.created_at} {self.closed}"

    def __repr__(self):
        return f"{self.session_id} {self.user} {self.created_at} {self.closed}"


class SearchResult(models.Model):
    """
    A model to store search results
    """
    node = models.ForeignKey(WebsocketNode, on_delete=models.CASCADE, related_name="search_results", blank=True, null=True)
    session = models.ForeignKey(WebsocketSession, on_delete=models.CASCADE, related_name="search_results", blank=True, null=True)
    pyre = models.ForeignKey(Pyre, on_delete=models.CASCADE, related_name="search_results", blank=True, null=True)
    client_id = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file = models.FileField(upload_to="cephalon/files/search_results/", blank=True, null=True)
    search_query = models.JSONField(blank=True, null=True)
    search_type = models.TextField(blank=True, null=True)
    search_id = models.TextField(blank=True, null=True)
    search_status_choices = [
        ("pending", "pending"),
        ("in_progress", "in_progress"),
        ("complete", "complete"),
        ("failed", "failed")
    ]
    search_status = models.CharField(max_length=11, choices=search_status_choices, default="pending")
    file_hash = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

    def __str__(self):
        return f"{self.session} {self.created_at} {self.search_status}"

    def __repr__(self):
        return f"{self.session} {self.created_at} {self.search_status}"

    def delete(self, using=None, keep_parents=False):
        self.file.delete()
        super().delete(using=using, keep_parents=keep_parents)

    def verify_file(self):
        hasher = hashlib.sha1()
        with self.file.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        hash = hasher.hexdigest()
        if hash == self.file_hash:
            return True
        else:
            return False

    def update_hash(self):
        hasher = hashlib.sha1()
        with self.file.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        self.file_hash = hasher.hexdigest()
        self.save()

    async def send_to_remote(self, api_key, pyre_name: str, session_id: str, client_id: str, node_id: str):
        """
        A method to send search result to remote server
        """
        search_result = await self.create_remote_result(api_key, pyre_name, session_id, client_id, node_id)
        print(search_result)
        file = await self.upload_chunked_file(api_key, search_result["id"])
        return file

    async def upload_chunked_file(self, api_key, search_result_id):
        decoded_api_key = api_key.decrypt_remote_api_key()
        host = f"{api_key.remote_pair.protocol}://{api_key.remote_pair.hostname}:{api_key.remote_pair.port}"
        async with httpx.AsyncClient(headers={"X-API-Key": decoded_api_key}) as client:
            d = await client.post(f"{host}/api/files/chunked", json={
                "filename": self.file.name,
                "size": self.file.size,
                "data_hash": self.file_hash,
                "file_category": "json"
            })
            upload_id = d.json()["upload_id"]
            with self.file.open("rb") as f:
                offset = 0
                while True:
                    chunk = f.read(d.json()["chunk_size"])
                    if not chunk:
                        break
                    chunk_file = BytesIO(chunk)
                    progress = await client.post(f"{host}/api/files/chunked/{upload_id}",
                                                 data={"offset": offset}, files={"chunk": chunk_file})
                    if progress.json()["status"] == "complete":
                        break
                    else:
                        offset = progress.json()["offset"]
                result = await client.post(f"{host}/files/chunked/{upload_id}/complete/search_result/{search_result_id}")
                return result.json()

    async def create_remote_result(self, api_key, pyre_name: str, session_id: str, client_id: str, node_id: str):
        """
        A method to create search result on remote server
        """
        decoded_api_key = api_key.decrypt_remote_api_key()
        host = f"{api_key.remote_pair.protocol}://{api_key.remote_pair.hostname}:{api_key.remote_pair.port}"
        async with httpx.AsyncClient(headers={"X-API-Key": decoded_api_key}) as client:
            result = await client.post(f"{host}/api/search_result", data={
                "pyre_name": pyre_name,
                "session_id": session_id,
                "client_id": client_id,
                "search_query": self.search_query,
                "node_id": node_id
            })
            print(result.content)
            return result.json()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)

@receiver(post_save, sender=APIKey)
def add_public_topic(sender, instance=None, created=False, **kwargs):
    if created:
        instance.access_topics.add(Topic.objects.get(name="public"))
        instance.save()

@receiver(post_save, sender=Pyre)
def add_public_topic_to_pyre(sender, instance=None, created=False, **kwargs):
    if created:
        instance.topics.add(Topic.objects.get(name="public"))
        instance.save()

@receiver(post_save, sender=ProjectFileContent)
def update_search_vector(sender, instance=None, created=False, **kwargs):
    if created:
        instance.search_vector = SearchVector("data")
        instance.save()