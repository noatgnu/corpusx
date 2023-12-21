from django.contrib import admin

from cephalon.models import APIKey, Project, ProjectFile, Pyre, WebsocketNode, Topic


# Register your models here.
@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "user")

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "hash", "global_id")

@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "hash", "file_type", "file", "file_category", "path")
    fields = ("name", "description", "file_type", "file_category", "file", "project", 'load_file_content')

    def save_model(self, request, obj, form, change):
        if 'file' in form.changed_data:
            obj.save_altered()
        if 'load_file_content' in form.changed_data:
            if form.cleaned_data['load_file_content']:
                obj.load_file()
            else:
                obj.remove_file_content()
        super().save_model(request, obj, form, change)

@admin.register(Pyre)
class PyreAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(WebsocketNode)
class WebsocketNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "api_key")

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "description")