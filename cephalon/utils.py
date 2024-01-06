import hashlib
import os
import string
from random import choice

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, RSAPrivateKey
from django.contrib.auth.hashers import make_password, BasePasswordHasher
import jwt
from django.utils.crypto import constant_time_compare
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import subprocess
import shlex

import cephalon


class Sha512ApiKeyHasher(BasePasswordHasher):
    """
    Copied from django restframework api key
    An API key hasher using the sha512 algorithm.

    This hasher should *NEVER* be used in Django's `PASSWORD_HASHERS` setting.
    It is insecure for use in hashing passwords, but is safe for hashing
    high entropy, randomly generated API keys.
    """

    algorithm = "sha512"

    def salt(self) -> str:
        """No need for a salt on a high entropy key."""
        return ""

    def encode(self, password: str, salt: str) -> str:
        if salt != "":
            raise ValueError("salt is unnecessary for high entropy API tokens.")
        hash = hashlib.sha512(password.encode()).hexdigest()
        return "%s$$%s" % (self.algorithm, hash)

    def verify(self, password: str, encoded: str) -> bool:
        encoded_2 = self.encode(password, "")
        return constant_time_compare(encoded, encoded_2)


def create_signed_token(payload: dict, secret_key: str):
    """
    Create a signed jwt token using pyjwt and django secret key
    """
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token

def decode_signed_token(token: str, secret_key: str):
    """
    Decode a signed jwt token using pyjwt and django secret key
    """
    payload = jwt.decode(token, secret_key, algorithms=["HS256"])
    return payload

def create_api_key(prefix_length: int = 8, secret_length: int = 32):
    """
    Create an api key
    """
    prefix = "".join([choice(string.ascii_letters) for _ in range(prefix_length)])
    suffix = "".join([choice(string.ascii_letters) for _ in range(secret_length)])
    key = f"{prefix}.{suffix}"
    hashed_key = make_password(key, hasher=Sha512ApiKeyHasher())
    return hashed_key, key

def verify_api_key(key: str, hashed_key: str):
    """
    Verify an api key
    """
    return Sha512ApiKeyHasher().verify(key, hashed_key)


def generate_RSA_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem, public_pem

def generate_AESGCM_key():
    return AESGCM.generate_key(bit_length=256)

def encrypt_AESGCM_key(AESGCM_key: bytes, nonce: bytes, RSA_public_key: RSAPublicKey):
    encrypted_key = RSA_public_key.encrypt(
        AESGCM_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA512(),
            label=None
        )
    )
    encrypted_nonce = RSA_public_key.encrypt(
        nonce,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA512(),
            label=None
        )
    )

    return {
        "encrypted_key": encrypted_key,
        "encrypted_nonce": encrypted_nonce
    }

def decrypt_AESGCM_key(encrypted_AESGCM_key: bytes, encrypted_nonce: bytes, RSA_private_key: RSAPrivateKey):
    decrypted_key = RSA_private_key.decrypt(
        encrypted_AESGCM_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA512(),
            label=None
        )
    )
    decrypted_nonce = RSA_private_key.decrypt(
        encrypted_nonce,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA512(),
            label=None
        )
    )
    return {
        "decrypted_key": decrypted_key,
        "decrypted_nonce": decrypted_nonce
    }

def encrypt_AESGCM(plaintext: bytes, key: bytes):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return ciphertext, nonce

def decrypt_AESGCM(ciphertext: bytes, nonce: bytes, key: bytes):
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext

def search_file(filepath: str, terms: list[str]):
    """
    A function that use search.sh script from cephalon to search for terms in a file
    """
    cephalon_path = os.path.dirname(cephalon.__file__)
    search_sh_path = os.path.join(cephalon_path, "search.sh").replace("\\", "/")
    filepath = filepath.replace('\\', '/')

    result = subprocess.run(['bash', search_sh_path, ','.join(terms), filepath], capture_output=True)
    data = result.stdout.decode("utf-8")
    for i in data.split("\n"):
        if i == "":
            break
        row = i.split(":")
        yield {"term": row[0].strip(), "row": int(row[1].strip())}
