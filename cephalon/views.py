import json
import re
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank, SearchHeadline
from django.core.files.base import ContentFile
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from ninja import NinjaAPI, Form, Swagger, File
from ninja.security import django_auth, django_auth_superuser, APIKeyQuery
from ninja.files import UploadedFile
from ninja.pagination import paginate
import hashlib
from cephalon.authentications import AuthBearer, AuthApiKey, AuthApiKeyHeader
from cephalon.models import Project, ProjectFile, ChunkedUpload, ProjectFileContent, WebsocketSession, WebsocketNode, \
    Pyre, SearchResult
from cephalon.schemas import ProjectSchema, ProjectPostSchema, FileSchema, FilePostSchema, ChunkedUploadSchema, \
    HashErrorSchema, ChunkedUploadInitSchema, ChunkedUploadCompleteSchema, BadRequestSchema, SearchResultSchema, \
    SearchResultInitSchema, NotifyFileUploadComplete, NotifyMessageSchema

api = NinjaAPI(docs=Swagger(), title="Cephalon API")


@api.get("/bearer", auth=AuthBearer())
def bearer(request):
    return {"user": request.user.username}


@api.get("/apiquery", auth=[AuthApiKey(), AuthApiKeyHeader() , AuthBearer()])
def apiquery(request):
    return {"api_key": request.auth.key}


@api.get("/projects/{project_id}", response=ProjectSchema)
def get_project(request, project_id: int):
    return Project.objects.get(id=project_id)

@api.patch("/projects/{project_id}", response=ProjectSchema, auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def update_project(request, project_id: int, body: ProjectPostSchema):
    project = Project.objects.get(id=project_id)
    # check what fields are different then update the field
    for field in body.dict().keys():
        if getattr(project, field) != body.dict()[field]:
            setattr(project, field, body.dict()[field])
    project.save()
    return project

@api.post("/projects", response=ProjectSchema, auth=[AuthApiKey(),AuthApiKeyHeader(), AuthBearer()])
def create_project(request, project: ProjectPostSchema):
    return Project.objects.create(**project.dict())


@api.get("/projects", response=list[ProjectSchema])
@paginate
def list_projects(request):
    return Project.objects.all()


@api.get("/projects/{project_id}/files", response=list[FileSchema])
def list_project_files(request, project_id: int):
    project = Project.objects.get(id=project_id)
    return project.files.all()


@api.post("/projects/{project_id}/files", response=FileSchema,
          auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def create_project_file(request, project_id: int, body: FilePostSchema = Form(...), file: UploadedFile = File(...)):
    project = Project.objects.get(id=project_id)
    body.metadata = json.loads(body.metadata)
    hasher = hashlib.sha1()
    for chunk in iter(lambda: file.read(4096), b""):
        hasher.update(chunk)
    hash = hasher.hexdigest()
    if hash != body.hash:
        return {"error": "hash mismatch"}
    file.seek(0)
    return project.files.create(file=file, **body.dict(), name=file.name)

@api.patch("/files/patch/{file_id}", response=FileSchema, auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def update_project_file(request, file_id: int, body: FilePostSchema = Form(...)):
    file = ProjectFile.objects.get(id=file_id)
    body.metadata = json.loads(body.metadata)
    file.metadata = body.metadata
    file.description = body.description
    if body.load_file_content:
        with open(file.file.path, "rt") as f:
            ProjectFileContent.objects.create(project_file=file, data=f.read())
    file.save()
    return file

@api.post("/files/chunked", response=ChunkedUploadSchema, auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def initiate_chunked_upload(request, body: ChunkedUploadInitSchema = Form(...)):
    print(body)
    chunk = ChunkedUpload.objects.create(total_size=body.size, filename=body.filename, hash=body.data_hash, file_category=body.file_category, file=ContentFile(b"", name=body.filename))
    return chunk

@api.post("/files/chunked/{upload_id}", response={200: ChunkedUploadSchema, 400: HashErrorSchema},
          auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def upload_chunk(request, upload_id: str, offset: int = Form(...), chunk: UploadedFile = File(...)):
    chunked_upload = ChunkedUpload.objects.get(upload_id=upload_id)

    with open(chunked_upload.file.path, "ab") as f:
        f.write(chunk.read())


    if chunked_upload.offset + chunk.size > chunked_upload.total_size:
        chunked_upload.offset = chunked_upload.size
    else:
        chunked_upload.offset = offset + chunk.size
    if chunked_upload.offset == chunked_upload.total_size:
        verify_hash = hashlib.sha1()
        chunked_upload.file.seek(0)
        for chunk in iter(lambda: chunked_upload.file.read(4096), b""):
            verify_hash.update(chunk)
        if chunked_upload.hash != verify_hash.hexdigest():
            return 400, {"error": "hash mismatch"}
        chunked_upload.status = "complete"

        return 200, chunked_upload

    else:
        chunked_upload.status = "in_progress"
    chunked_upload.save()
    return 200, chunked_upload

@api.post("/files/chunked/{upload_id}/complete", response={200: FileSchema, 400: BadRequestSchema}, auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def complete_chunked_upload(request, upload_id: str, body: ChunkedUploadCompleteSchema):
    chunked_upload = ChunkedUpload.objects.get(upload_id=upload_id)
    file = None
    project = None
    if body.project_id:
        project = Project.objects.get(id=body.project_id)
    if body.file_id:
        file = ProjectFile.objects.get(id=body.file_id)
        file.file = chunked_upload.file
        file.save()
    if body.create_file:
        file = ProjectFile.objects.create(file=ContentFile(chunked_upload.file.read(),
                                                           name=chunked_upload.filename),
                                          hash=chunked_upload.hash,
                                          name=chunked_upload.filename,
                                          file_category=chunked_upload.file_category,
                                          path=body.path)
        if body.project_id:
            file.project = project
            file.save()
    if (body.file_id or body.create_file) and body.load_file_content:
        file.load_file()
        file.load_file_content = True
        file.save()
    if body.delete:
        chunked_upload = ChunkedUpload.objects.get(upload_id=upload_id)
        chunked_upload.file.delete()
        chunked_upload.delete()
    if file:
        return 200, file
    else:
        return 400, {"error": "bad request"}

@api.delete("/files/{file_id}", response={204: None}, auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def delete_file(request, file_id: int):
    file = ProjectFile.objects.get(id=file_id)
    file.delete()
    return 204, None

@api.get("/files/{file_id}/download", auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def download_file(request, file_id: int):

    file = ProjectFile.objects.get(id=file_id)
    print(file)
    response = HttpResponse(status=200)
    response["Content-Disposition"] = f"attachment; filename={file.name}"
    response["X-Accel-Redirect"] = f"/media/{file.file.name}"
    return response

@api.get("/files/{file_id}/session/{session_id}/download")
def download_sessional_file(request, file_id: int, session_id: str):
    file = ProjectFile.objects.get(id=file_id)
    session = WebsocketSession.objects.get(session_id=session_id)

    if file in session.files.all():
        response = HttpResponse(status=200)
        response["Content-Disposition"] = f"attachment; filename={file.name}"
        response["X-Accel-Redirect"] = f"/media/{file.file.name}"
        return response
    else:
        return HttpResponse(status=403)

@api.get("/search/project/{query}", response=list[ProjectSchema], auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def search_project(request, query: str):
    #vector = SearchVector("name", "description", "metadata", "files__name", weight="B") + SearchVector("files__description", "files__content__data", weight="A")
    #query = SearchQuery(query)
    # return Project.objects.annotate(rank=SearchRank(vector, query)).order_by("-rank")
    #vector = SearchVector("name", "description", "metadata", "files__name", weight="B") + SearchVector(
    #    "files__description", "files__content__data", weight="A")
    #Project.objects.filter(files__content__data__search="test")
    q = SearchQuery(query, search_type="phrase")
    v = SearchVector("files__content__data")
    headline = SearchHeadline("files__content__data", q, start_sel="<b>", stop_sel="</b>")

    return Project.objects.annotate(headline=headline, search=v).filter(search=q)

@api.get("/search/file/{query}", response=list[FileSchema], auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
@paginate
def search_file(request, query: str):
    q = SearchQuery(query, search_type="phrase")
    v = SearchVector("content__data")
    headline = SearchHeadline("content__data", q, start_sel="<b>", stop_sel="</b>")
    return ProjectFile.objects.annotate(headline=headline, search=v).filter(search=q)

@api.get("/websockets/session_id", response=str)
def websocket_session_id(request):
    user = request.user
    if user.is_authenticated:
        ws = WebsocketSession.objects.get(user=user)
        if ws.DoesNotExist:
            ws = WebsocketSession.objects.create(user=user)
        return str(ws.session_id)
    else:
        return str(WebsocketSession.objects.create().session_id)

@api.post("/receive_key", auth=[AuthApiKey(), AuthApiKeyHeader()])
def receive_key(request, key: str = Form(...)):
    request.auth.receive_key(key)
    request.auth.save()
    return HttpResponse(status=200)

@api.post("/register_node", auth=[AuthApiKey(), AuthApiKeyHeader()])
def register_node(request, node_name: str = Form(...)):
    nodes = WebsocketNode.objects.filter(name=node_name)
    if nodes:
        node = nodes[0]
        if node.api_key == request.auth:

            return {"id": node.id, "name": node.name}
        else:
            return HttpResponse(status=403)
    else:
        node = WebsocketNode.objects.create(name=node_name, api_key=request.auth)
        return {"id": node.id, "name": node.name}

@api.get("/pyres", response=list[str], auth=[AuthApiKey(), AuthApiKeyHeader(), AuthBearer()])
def get_pyres(request):
    return [i.name for i in Pyre.objects.all()]

@api.get("/pyres/{pyre_name}", auth=[AuthBearer(), AuthApiKey(), AuthApiKeyHeader()])
def get_pyre(request, pyre_name: str):
    pyres = Pyre.objects.filter(name=pyre_name)
    if pyres:
        pyre = pyres[0]
        if request.auth in pyre.apikey_set.all():
            return HttpResponse(status=200)
        else:
            return HttpResponse(status=403)
    return HttpResponse(status=200)

@api.post("/search_result", response=SearchResultSchema, auth=[AuthApiKeyHeader(), AuthApiKey()])
def create_search_result(request, body: SearchResultInitSchema = Form(...)):
    pyres = Pyre.objects.filter(name=body.pyre_name)
    nodes = WebsocketNode.objects.filter(name=body.node_id)
    if pyres and nodes:
        pyre = pyres[0]
        node = nodes[0]
        if request.auth in pyre.apikey_set.all():
            session = WebsocketSession.objects.get(session_id=body.session_id)
            return SearchResult.objects.create(
                pyre=pyre,
                session=session,
                client_id=body.client_id,
                search_query=body.search_query,
                node=node)
    return HttpResponse(status=403)

@api.post("/files/chunked/{upload_id}/complete/search_result/{search_result_id}", response={200: SearchResultSchema, 400: BadRequestSchema}, auth=[AuthApiKey(), AuthApiKeyHeader()])
def complete_chunked_upload_search_result(request, upload_id: str, search_result_id: int):
    chunked_upload = ChunkedUpload.objects.get(upload_id=upload_id)
    search_result = SearchResult.objects.get(id=search_result_id)
    search_result.file = ContentFile(chunked_upload.file.read(), name=chunked_upload.filename)
    search_result.search_status = "complete"
    search_result.save()
    search_result.update_hash()
    channel_layer = get_channel_layer()
    data = {
        'type': 'communication_message',
        'message': {
            'message': "Results found",
            'requestType': "search",
            'senderID': search_result.node.name,
            'targetID': search_result.client_id,
            'channelType': "search-result",
            'data': SearchResultSchema.from_orm(search_result).dict(),
            'sessionID': str(search_result.session.session_id),
            'clientID': search_result.client_id,
            'pyreName': search_result.pyre.name,
        }
    }
    async_to_sync(channel_layer.group_send)(data["message"]["sessionID"] + "_result", data)
    return 200, search_result

@api.get("/search_result/{search_result_id}/{session_id}/download")
def download_searchF_result(request, search_result_id: int, session_id: str):
    search_result = SearchResult.objects.get(id=search_result_id, session__session_id=session_id)
    response = HttpResponse(status=200)
    response["Content-Disposition"] = f"attachment; filename={search_result.file.name}"
    response["X-Accel-Redirect"] = f"/media/{search_result.file.name}"
    return response

@api.post("/notify/file_upload_completed/{session_id}/{client_id}", auth=[AuthApiKey(), AuthApiKeyHeader()])
def notify(request, session_id: str, client_id: str, body: NotifyFileUploadComplete = Form(...)):
    file = ProjectFile.objects.get(id=body.file_id)
    old_file = json.loads(body.old_file)
    channel_layer = get_channel_layer()
    data = {
        'type': 'communication_message',
        'message': {
            'message': "File uploaded",
            'requestType': "file-upload",
            'senderID': body.server_id,
            'targetID': client_id,
            'channelType': "file",
            'data': [old_file, FileSchema.from_orm(file).dict()],
            'sessionID': session_id,
            'clientID': client_id,
            'pyreName': body.pyre_name,
        }
    }
    async_to_sync(channel_layer.group_send)(session_id + "_result", data)
    return HttpResponse(status=200)

@api.post("/notify/message/{session_id}/{client_id}", auth=[AuthApiKey(), AuthApiKeyHeader()])
def notify_message(request, session_id: str, client_id: str, body: NotifyMessageSchema = Form(...)):
    channel_layer = get_channel_layer()
    data = {
        'type': 'communication_message',
        'message': {
            'message': body.message,
            'requestType': body.requestType,
            'senderID': body.senderID,
            'targetID': client_id,
            'channelType': body.channelType,
            'data': body.data,
            'sessionID': session_id,
            'clientID': client_id,
            'pyreName': body.pyreName,
        }
    }
    async_to_sync(channel_layer.group_send)(session_id + "_result", data)
    return HttpResponse(status=200)

