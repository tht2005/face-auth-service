import os
import json
import numpy as np
import hvac
import base64
from dotenv import load_dotenv

load_dotenv()

VAULT_URL = os.getenv("VAULT_URL")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
KEY_NAME = os.getenv("VAULT_KEY_NAME")

client = hvac.Client(url=VAULT_URL, token=VAULT_TOKEN)

if not client.is_authenticated():
    raise ConnectionError("Can not connect to vault!")

def encrypt_vector(vec):
    vec_str = json.dumps(vec.tolist())
    base64_data = base64.b64encode(vec_str.encode('utf-8')).decode('utf-8')
    encrypt_result = client.secrets.transit.encrypt_data(
        name=KEY_NAME,
        plaintext=base64_data)
    ciphertext = encrypt_result['data']['ciphertext']
    return ciphertext

def decrypt_vector(ciphertext):
    decrypt_result = client.secrets.transit.decrypt_data(
        name=KEY_NAME,
        ciphertext=ciphertext)
    base64_data = decrypt_result['data']['plaintext']
    vec_str = base64.b64decode(base64_data.encode('utf-8')).decode('utf-8')
    return np.array(json.loads(vec_str))

