from django.contrib import admin
from django_json_widget.widgets import JSONEditorWidget

from django.db import models
from cephalon.models import APIKey, Project, ProjectFile, Pyre, WebsocketNode, Topic, APIKeyRemote, AnalysisGroup


# Register your models here.
class TopicInline(admin.TabularInline):
    model = Topic.projects.through

@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("user", "access_topics", "remote_pair", "expired")
    fields = ("key", "user", "access_topics", "remote_pair", "expired", "expiry", "public_key", "access_all", "pyres")
    readonly_fields = ("key",)
    def access_topics(self, obj):
        return [t for t in obj.topics.all()]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    search_fields = ("name", "description", "hash")
    list_display = ("name", "description", "hash", "global_id")
    fields = ("name", "description", "hash", "metadata", "global_id", "temporary", "user", "encrypted")
    inlines = [
        TopicInline,
    ]
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }



@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    search_fields = ("name", "description", "hash")
    list_display = ("name", "description", "hash", "file_type", "file", "file_category", "path")
    fields = ("name", "description", "file_type", "file_category", "file", "project", 'load_file_content')
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }

    def save_model(self, request, obj, form, change):
        if obj._state.adding:
            obj.save()

        if 'file' in form.changed_data:
            obj.save()
            obj.save_altered()
        if 'load_file_content' in form.changed_data:
            if form.cleaned_data['load_file_content']:
                obj.load_file()
            else:
                obj.remove_file_content()
        super().save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        field = request.GET.get("field_name")
        if field == "searched_file":
            queryset = queryset.filter(file_category="searched")
        elif field == "differential_analysis_file":
            queryset = queryset.filter(file_category="differential_analysis")
        elif field == "sample_annotation_file":
            queryset = queryset.filter(file_category="sample_annotation")
        elif field == "comparison_matrix_file":
            queryset = queryset.filter(file_category="comparison_matrix")
        elif field == "unprocessed_file":
            queryset = queryset.filter(file_category="unprocessed")
        elif field == "other_files":
            queryset = queryset.filter(file_category="other")
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct
@admin.register(Pyre)
class PyreAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(WebsocketNode)
class WebsocketNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "api_key")

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "description")

@admin.register(APIKeyRemote)
class APIKeyRemote(admin.ModelAdmin):
    list_display = ("hostname", "protocol", "port")
    readonly_fields = ("key",)
    fields = ("key", "hostname", "protocol", "port")

@admin.register(AnalysisGroup)
class AnalysisGroupAdmin(admin.ModelAdmin):
    autocomplete_fields = ("searched_file", "differential_analysis_file", "sample_annotation_file", "comparison_matrix_file", "unprocessed_file", "other_files")
    list_display = ("searched_file", "differential_analysis_file", "sample_annotation_file")
    fields = ("searched_file", "differential_analysis_file", "sample_annotation_file", "comparison_matrix_file", "unprocessed_file", "other_files")
