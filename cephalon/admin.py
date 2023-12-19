from django.contrib import admin

from cephalon.models import APIKey, Project, ProjectFile


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
