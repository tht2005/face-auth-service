import os
import psycopg2
from dotenv import load_dotenv
import numpy as np
import jwt
import datetime
from backend.vault import encrypt_vector, decrypt_vector

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "supersecretjwtkey123!")
JWT_ALGORITHM = "HS256"

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "ekyc_matrix"),
        user=os.getenv("DB_USER", "ekyc_admin"),
        password=os.getenv("DB_PASSWORD", "SuperStrongPass!No1")
    )

def register(username, fullname, face_emb):
    """
    Registers a new user by encrypting their face embedding via Vault,
    and storing credentials in PostgreSQL.
    """
    encrypted_str = encrypt_vector(face_emb)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
        INSERT INTO users (username, full_name, face_embedding_encrypted)
        VALUES (%s, %s, %s);
        """
        cursor.execute(query, (username, fullname, encrypted_str))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def cosine_sim(a, b):
    return a.dot(b) / (np.linalg.norm(a) * np.linalg.norm(b))

def validation(username, current_face_emb):
    """
    Validates a live face embedding against the database template.
    Returns (is_match, full_name, similarity).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT face_embedding_encrypted, is_active, full_name FROM users WHERE username = %s;"
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
    Generates a secure JSON Web Token valid for 1 hour.
    """
    payload = {
        "sub": username,
        "name": fullname,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str) -> dict:
    """
    Decodes and validates a JWT token. Returns the payload dictionary.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid session token.")
