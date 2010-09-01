

import base64
import hashlib
import uuid


def generate_mac(secret, data):
    return hashlib.sha1(
        hashlib.sha1(
            secret + data
        ).digest()
    ).digest()[:16]


def authenticate_mac(secret, data, mac):
    return generate_mac(secret, data) == mac


def b64encode(string):
    return base64.b64encode(string, '-_').strip('=')


def b64decode(string):
    string += "=" * ((8 - len(string) % 8) % 8)
    return base64.b64decode(string, '-_')


def uid():
    return b64encode(uuid.uuid4().bytes)

