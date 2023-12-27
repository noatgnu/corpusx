from scheduler import job

from cephalon.models import ProjectFile, Project, SearchResult


@job
def remove_file_not_associated_with_any_project():
    ProjectFile.objects.filter(project=None).delete()

@job
def remove_temporary_project():
    Project.objects.filter(temporary=True).delete()

