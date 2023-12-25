import json
import uuid
from typing import Optional

from django.db.models import Q
from ninja import Schema, UploadedFile, Form, FilterSchema

from cephalon.models import Project

class BadRequestSchema(Schema):
    error: str

class ProjectSchema(Schema):
    id: int
    name: str
    description: str
    hash: str
    metadata: dict
    global_id: str
    headline: Optional[str] = None

class ProjectPostSchema(Schema):
    name: str
    description: str
    hash: str
    metadata: dict
    global_id: str

class FileSchema(Schema):
    id: int
    name: str
    description: Optional[str] = None
    hash: str
    metadata: Optional[dict] = None
    file_type: str
    file: str
    file_category: str
    path: Optional[list[str]] = []
    headline: Optional[str] = None
    project_id: Optional[int] = None

class FilePostSchema(Schema):
    description: str
    hash: str
    metadata: str
    file_type: str
    file_category: str
    load_file_content: Optional[bool] = False

class ChunkedUploadSchema(Schema):
    filename: str
    total_size: int
    upload_id: uuid.UUID
    offset: int
    chunk_size: int
    status: str
    file_id: Optional[int] = None

class HashErrorSchema(Schema):
    error: str

class ChunkedUploadInitSchema(Schema):
    filename: str
    file_category: str
    size: int
    data_hash: str

class ChunkedUploadCompleteSchema(Schema):
    file_id: Optional[int] = None
    delete: Optional[bool] = False
    create_file: Optional[bool] = False
    load_file_content: Optional[bool] = False
    project_id: Optional[int] = None
    path: Optional[tuple[str, ...]] = []

class SearchResultSchema(Schema):
    id: int
    pyre_id: int
    session_id: Optional[int] = None
    client_id: Optional[str] = None
    search_query: str

class SearchResultInitSchema(Schema):
    pyre_name: str
    session_id: str
    client_id: str
    search_query: str
    node_id: str

class NotifyFileUploadComplete(Schema):
    file_id: int
    pyre_name: str
    server_id: str
    old_file: str
