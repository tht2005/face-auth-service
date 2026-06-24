import os
import sqlite3
from dotenv import load_dotenv
import numpy as np
import jwt
import datetime
import secrets
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from backend.vault import encrypt_vector, decrypt_vector

load_dotenv()

KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private_key.pem")
PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, "public_key.pem")

def get_rsa_keys():
    if not os.path.exists(KEYS_DIR):
        os.makedirs(KEYS_DIR, exist_ok=True)
    
    if not os.path.exists(PRIVATE_KEY_PATH) or not os.path.exists(PUBLIC_KEY_PATH):
        # Generate new keys
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        with open(PRIVATE_KEY_PATH, "wb") as f:
            f.write(private_pem)
        with open(PUBLIC_KEY_PATH, "wb") as f:
            f.write(public_pem)
            
    # Load keys
    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key_bytes = f.read()
    with open(PUBLIC_KEY_PATH, "rb") as f:
        public_key_bytes = f.read()
        
    return private_key_bytes, public_key_bytes

# Load RSA Key Pair
PRIVATE_KEY, PUBLIC_KEY = get_rsa_keys()
JWT_ALGORITHM = "RS256"

def get_db_connection():
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    return sqlite3.connect(db_path)

def init_db():
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(50) UNIQUE NOT NULL,
        full_name VARCHAR(100) NOT NULL,
        face_embedding_encrypted TEXT NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS used_nonces (
        nonce TEXT PRIMARY KEY,
        expires_at TIMESTAMP NOT NULL
    );
    """)
    conn.commit()
    cursor.close()
    conn.close()

def register(username, fullname, face_emb):
    """
    Registers a new user by encrypting their face embedding via Vault,
    and storing credentials in SQLite.
    """
    encrypted_str = encrypt_vector(face_emb)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
        INSERT INTO users (username, full_name, face_embedding_encrypted)
        VALUES (?, ?, ?);
        """
        cursor.execute(query, (username, fullname, encrypted_str))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError(f"Username '{username}' is already registered.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def cosine_sim(a, b):
    return a.dot(b) / (np.linalg.norm(a) * np.linalg.norm(b))

def check_user_status(username: str):
    """
    Checks if a user exists in the database and is active.
    Raises NameError if user not found, and PermissionError if account is locked.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT is_active FROM users WHERE username = ?;"
    cursor.execute(query, (username,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    if not result:
        raise NameError(f"User with username '{username}' not found!")
    
    is_active = result[0]
    if not is_active:
        raise PermissionError(f"Account '{username}' is locked!")

def validation(username, current_face_emb):
    """
    Validates a live face embedding against the database template.
    Returns (is_match, full_name, similarity).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT face_embedding_encrypted, is_active, full_name FROM users WHERE username = ?;"
    cursor.execute(query, (username,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    if not result:
        raise NameError(f"User with username '{username}' not found!")
    
    encrypted_str, is_active, full_name = result
    if not is_active:
        raise PermissionError(f"Account '{username}' is locked!")

    saved_face_emb = decrypt_vector(encrypted_str)
    sim = cosine_sim(current_face_emb, saved_face_emb)
    THRESHOLD = 0.6
    
    print(f"[DEBUG] cos simi = {sim}")
    
    is_match = sim > THRESHOLD
    return is_match, full_name, float(sim)

def create_jwt_token(username: str, fullname: str) -> str:
    """
    Generates a secure JSON Web Token valid for 1 hour signed with RSA private key.
    """
    payload = {
        "sub": username,
        "name": fullname,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str) -> dict:
    """
    Decodes and validates a JWT token using RSA public key.
    """
    try:
        return jwt.decode(token, PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid session token.")

def create_challenge_token(username: str, gesture: str = "NORMAL") -> str:
    """
    Generates a cryptographically signed challenge token valid for 60 seconds.
    Includes the requested dynamic active liveness gesture.
    """
    payload = {
        "sub": username,
        "nonce": secrets.token_hex(16),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60),
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "type": "challenge",
        "gesture": gesture
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm=JWT_ALGORITHM)

def check_and_use_nonce(nonce: str, expires_at_timestamp: float) -> bool:
    """
    Checks if a nonce has already been used.
    If it is new, inserts it and returns True.
    If it has already been used, returns False.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Cleanup expired nonces first to prevent database bloat
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute("DELETE FROM used_nonces WHERE expires_at < ?;", (now_str,))
        
        # Check if current nonce is used
        cursor.execute("SELECT nonce FROM used_nonces WHERE nonce = ?;", (nonce,))
        if cursor.fetchone():
            return False
            
        # Insert nonce
        expires_dt = datetime.datetime.fromtimestamp(expires_at_timestamp, datetime.timezone.utc)
        cursor.execute(
            "INSERT INTO used_nonces (nonce, expires_at) VALUES (?, ?);",
            (nonce, expires_dt.isoformat())
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def verify_challenge_token(token: str, expected_username: str) -> dict:
    """
    Decodes and verifies the challenge token signature, expiration, type, and username.
    Also checks that the nonce is single-use to prevent replay attacks.
    Returns the decoded token payload.
    """
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Biometric challenge token expired. Please try scanning again.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid challenge token.")
        
    if payload.get("type") != "challenge":
        raise ValueError("Incorrect token type presented.")
        
    if payload.get("sub") != expected_username:
        raise ValueError("Challenge token username mismatch.")
        
    nonce = payload.get("nonce")
    exp = payload.get("exp")
    if not nonce or not exp:
        raise ValueError("Malformed challenge token payload.")
        
    if not check_and_use_nonce(nonce, exp):
        raise ValueError("Challenge token replay detected (token has already been used).")
        
    return payload

