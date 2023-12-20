from django.core.management.base import BaseCommand

class Command(BaseCommand):
    """
    A command that sends an API key to the index server
    """

    def add_arguments(self, parser):
        parser.add_argument('host', type=str, help='Host of the index server')
        parser.add_argument('port', type=int, help='Port of the index server')
        parser.add_argument('remote_api_key', type=str, help='API key to be sent to the index server')
        parser.add_argument('connect_api_key', type=str, help='API key to be used to connect to the index server')
        parser.add_argument('server_id', type=str, help='ID of the server')

    def handle(self, *args, **options):
        pass