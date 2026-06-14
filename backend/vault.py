import os
import json
import numpy as np
import hvac
import base64
from dotenv import load_dotenv

load_dotenv()

VAULT_URL = os.getenv("VAULT_URL", "http://localhost:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
KEY_NAME = os.getenv("VAULT_KEY_NAME", "transit-key")

_client = None

def get_vault_client():
    global _client
    if _client is None:
        if not VAULT_URL or not VAULT_TOKEN:
            raise ValueError("VAULT_URL and VAULT_TOKEN environment variables must be set.")
        
        # Initialize client
        client_instance = hvac.Client(url=VAULT_URL, token=VAULT_TOKEN)
        
        try:
            if not client_instance.is_authenticated():
                raise ConnectionError("Vault client failed to authenticate. Please check your token.")
            _client = client_instance
        except Exception as e:
            raise ConnectionError(f"Could not connect to HashiCorp Vault at {VAULT_URL}: {e}")
            
    return _client

def encrypt_vector(vec: np.ndarray) -> str:
    """
    Serializes a numpy array vector to JSON, encodes it to Base64,
    and encrypts it using the Vault Transit secrets engine.
    """
    client = get_vault_client()
    vec_str = json.dumps(vec.tolist())
    base64_data = base64.b64encode(vec_str.encode('utf-8')).decode('utf-8')
    try:
        encrypt_result = client.secrets.transit.encrypt_data(
            name=KEY_NAME,
            plaintext=base64_data
        )
        return encrypt_result['data']['ciphertext']
    except Exception as e:
        raise RuntimeError(f"Vault encryption failed: {e}")

def decrypt_vector(ciphertext: str) -> np.ndarray:
    """
    Decrypts the ciphertext using Vault Transit secrets engine,
    decodes it from Base64, and parses it back into a numpy array.
    """
    client = get_vault_client()
    try:
        decrypt_result = client.secrets.transit.decrypt_data(
            name=KEY_NAME,
            ciphertext=ciphertext
        )
        base64_data = decrypt_result['data']['plaintext']
        vec_str = base64.b64decode(base64_data.encode('utf-8')).decode('utf-8')
        return np.array(json.loads(vec_str))
    except Exception as e:
        raise RuntimeError(f"Vault decryption failed: {e}")
