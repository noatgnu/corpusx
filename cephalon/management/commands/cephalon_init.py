from django.core.management.base import BaseCommand

from cephalon.models import Topic, Pyre


class Command(BaseCommand):
    """
    A command to initialize some options for the database.
    """

    def handle(self, *args, **options):
        Topic.objects.get_or_create(name="public")
        Pyre.objects.get_or_create(name="public")
