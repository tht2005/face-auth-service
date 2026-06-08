import os
import psycopg2
from dotenv import load_dotenv
from vault import encrypt_vector, decrypt_vector
import numpy as np

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"))

def register(username, fullname, face_emb):
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
    return a.dot(b) / np.linalg.norm(a) / np.linalg.norm(b)

def validation(username, current_face_emb):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT face_embedding_encrypted, is_active FROM users WHERE username = %s;"
    cursor.execute(query, (username,))
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    if not result:
        raise NameError(f"User with username '{username}' not found!")

    encrypted_str, is_active = result
    if not is_active:
        raise PermissionError(f"Account '{username}' is now locked!")

    saved_face_emb = decrypt_vector(encrypted_str)
    distance = np.linalg.norm(current_face_emb - saved_face_emb)
    sim = cosine_sim(current_face_emb, saved_face_emb)
    THRESHOLD = 0.6
    print(f"[DEBUG] distance = {distance}")
    print(f"[DEBUG] cos simi = {sim}")
    return sim > THRESHOLD

