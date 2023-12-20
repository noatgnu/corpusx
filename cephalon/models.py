import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from cephalon.utils import create_signed_token, decode_signed_token, create_api_key, verify_api_key
from django.conf import settings


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
        ("txt", "space separated text"),
        ("json", "json"),
        ("other", "other")
    ]
    file_type = models.CharField(max_length=5, choices=file_type_choices, default="tsv")
    file_category = models.TextField(blank=True, null=True)
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

class ProjectFileContent(models.Model):
    """
    A model to store data of textfiles directly in the database
    """
    data = models.TextField(blank=True, null=True)
    project_file = models.ForeignKey(ProjectFile, on_delete=models.CASCADE, related_name="content", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        app_label = "cephalon"

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




@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)

