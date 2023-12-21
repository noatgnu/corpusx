from django.contrib.auth.hashers import make_password
from ninja.security import HttpBearer, APIKeyQuery, APIKeyHeader
from cephalon.models import Token, APIKey
from cephalon.utils import Sha512ApiKeyHasher

class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            t = Token.objects.get(key=token)
            request.user = t.user
            return t
        except Token.DoesNotExist:
            return None


class AuthApiKey(APIKeyQuery):
    param_name = "api_key"

    def authenticate(self, request, key):
        try:
            hashed_key = make_password(key, hasher=Sha512ApiKeyHasher())
            return APIKey.objects.get(key=hashed_key)
        except APIKey.DoesNotExist:
            pass


class AuthApiKeyHeader(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        try:
            hashed_key = make_password(key, hasher=Sha512ApiKeyHasher())
            api_key = APIKey.objects.get(key=hashed_key)
            return api_key
        except APIKey.DoesNotExist:
            pass

