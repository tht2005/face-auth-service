import os
import sys
import time
import json
import sqlite3
import unittest
import requests
import jwt
import numpy as np
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Configuration
API_URL = "http://localhost:8000"
DB_PATH = "backend/ekyc_matrix.db"
IMAGE_PATH = "sample_face.png"
PRIVATE_KEY_PATH = "backend/keys/private_key.pem"

class SecurityTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure API server is reachable
        try:
            requests.get(API_URL)
        except requests.exceptions.ConnectionError:
            raise unittest.SkipTest(f"FastAPI server is not running at {API_URL}. Please start it first.")

        # Read Server Private Key
        if not os.path.exists(PRIVATE_KEY_PATH):
            raise unittest.SkipTest(f"Server private key not found at {PRIVATE_KEY_PATH}. Run server once to generate it.")
            
        with open(PRIVATE_KEY_PATH, "rb") as f:
            cls.server_private_key = f.read()

        # Load environment file to read Vault credentials if needed
        cls.vault_url = "http://localhost:8200"
        cls.vault_token = None
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        if k == "VAULT_URL":
                            cls.vault_url = v
                        elif k == "VAULT_TOKEN":
                            cls.vault_token = v

    def cleanup_user(self, username):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
        conn.commit()
        cursor.close()
        conn.close()

    def get_challenge_token(self, username, required_gesture="NORMAL"):
        url = f"{API_URL}/api/auth/challenge"
        # Since gesture selection is random, loop until we get the requested gesture
        for _ in range(30):
            r = requests.get(url, params={"username": username})
            if r.status_code == 200:
                data = r.json()
                if data.get("gesture") == required_gesture:
                    return data.get("challenge_token")
            time.sleep(0.02)
        return None


class TestB1ChallengeResponseAndReplay(SecurityTestBase):
    """
    Bảng 6: Kiểm thử Giao thức Challenge-Response & Chống Phát lại (Replay)
    """
    def setUp(self):
        self.username = "test_b1_user"
        self.victim = "test_b1_victim"
        self.cleanup_user(self.username)
        self.cleanup_user(self.victim)
        
        # Register test_b1_user
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.username, "full_name": "B1 Test User", "liveness_enabled": "false"}
            requests.post(f"{API_URL}/api/register", data=data, files=files)
            
        # Register test_b1_victim
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.victim, "full_name": "B1 Victim User", "liveness_enabled": "false"}
            requests.post(f"{API_URL}/api/register", data=data, files=files)

    def tearDown(self):
        self.cleanup_user(self.username)
        self.cleanup_user(self.victim)

    def test_1_1_username_mismatch(self):
        # Case 1.1: Username mismatch (Use attacker's token to login to victim's account)
        token = self.get_challenge_token(self.username, "NORMAL")
        self.assertIsNotNone(token)
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            # Log in as victim user but use attacker's token
            data = {"username": self.victim, "challenge_token": token, "liveness_enabled": "false"}
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("username mismatch", r.text.lower())

    def test_1_2_rogue_token(self):
        # Case 1.2: Rogue Token (Token signed with an untrusted key)
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rogue_pem = rogue_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        payload = {
            "sub": self.username,
            "nonce": os.urandom(16).hex(),
            "exp": int(time.time()) + 60,
            "iat": int(time.time()),
            "type": "challenge",
            "gesture": "NORMAL"
        }
        rogue_token = jwt.encode(payload, rogue_pem, algorithm="RS256")
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.username, "challenge_token": rogue_token, "liveness_enabled": "false"}
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid challenge token", r.text.lower())

    def test_1_3_challenge_timeout(self):
        # Case 1.3: Challenge Timeout (Use expired challenge token)
        expired_payload = {
            "sub": self.username,
            "nonce": os.urandom(16).hex(),
            "exp": int(time.time()) - 10, # Expired 10s ago
            "iat": int(time.time()) - 70,
            "type": "challenge",
            "gesture": "NORMAL"
        }
        expired_token = jwt.encode(expired_payload, self.server_private_key, algorithm="RS256")
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.username, "challenge_token": expired_token, "liveness_enabled": "false"}
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("expired", r.text.lower())

    def test_1_4_replay_attack(self):
        # Case 1.4: Replay Attack (Send same token twice)
        token = self.get_challenge_token(self.username, "NORMAL")
        self.assertIsNotNone(token)
        
        # Request 1 (Consumes nonce)
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.username, "challenge_token": token, "liveness_enabled": "false"}
            r1 = requests.post(f"{API_URL}/api/login", data=data, files=files)
        
        # Request 2 (Replay)
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.username, "challenge_token": token, "liveness_enabled": "false"}
            r2 = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r2.status_code, 400)
        self.assertIn("replay detected", r2.text.lower())


class TestB2BiometricLivenessDetection(SecurityTestBase):
    """
    Bảng 7: Kiểm thử Cơ chế Phát hiện Giả mạo Sinh trắc (Liveness Detection)
    """
    def setUp(self):
        self.username = "test_b2_user"
        self.cleanup_user(self.username)
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": self.username, "full_name": "B2 Test User", "liveness_enabled": "false"}
            requests.post(f"{API_URL}/api/register", data=data, files=files)

    def tearDown(self):
        self.cleanup_user(self.username)

    def test_2_1_print_attack_spoof(self):
        # Case 2.1: Print Attack (Laplacian variance check failure)
        # We simulate a low-texture print spoof by setting the Laplacian minimum threshold extremely high (e.g. 10000.0)
        token = self.get_challenge_token(self.username, "NORMAL")
        self.assertIsNotNone(token)
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {
                "username": self.username, 
                "challenge_token": token, 
                "liveness_enabled": "true",
                "min_laplacian": 10000.0 # Extreme threshold
            }
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("texture too flat/blurry", r.text.lower())

    def test_2_2_screen_spoof_fft(self):
        # Case 2.2: Digital Screen Attack (FFT pattern check failure)
        # We simulate Moiré screen scanning patterns by setting max_fft to -1.0 (impossible to satisfy)
        token = self.get_challenge_token(self.username, "NORMAL")
        self.assertIsNotNone(token)
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {
                "username": self.username, 
                "challenge_token": token, 
                "liveness_enabled": "true",
                "max_fft": -1.0 # Extreme threshold
            }
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("unnatural high-frequency patterns", r.text.lower())

    def test_2_3_screen_glare(self):
        # Case 2.3: Screen Specular Glare (HSV glare check failure)
        # We simulate screen reflection glare by setting max_glare to -1.0 (impossible to satisfy)
        token = self.get_challenge_token(self.username, "NORMAL")
        self.assertIsNotNone(token)
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {
                "username": self.username, 
                "challenge_token": token, 
                "liveness_enabled": "true",
                "max_glare": -1.0 # Extreme threshold
            }
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("specular glare detected", r.text.lower())

    def test_2_4_gesture_mismatch(self):
        # Case 2.4: Active Gesture Mismatch
        # We request a challenge token that requires LOOK_LEFT
        token = self.get_challenge_token(self.username, "LOOK_LEFT")
        self.assertIsNotNone(token)
        
        # We upload a frontal face (sample_face.png), which does not match LOOK_LEFT
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {
                "username": self.username, 
                "challenge_token": token, 
                "liveness_enabled": "true"
            }
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        self.assertEqual(r.status_code, 400)
        self.assertIn("turn your head to the left", r.text.lower())


class TestB3JWTSessionAndNetwork(SecurityTestBase):
    """
    Bảng 8: Kịch bản kiểm thử Quản lý Phiên Đăng nhập & Xác thực JWT
    """
    def test_3_1_session_timeout(self):
        # Case 3.1: Session Timeout (Expired Session Token)
        payload = {
            "sub": "test_user",
            "name": "Test User",
            "exp": int(time.time()) - 10, # Expired 10s ago
            "iat": int(time.time()) - 3610
        }
        expired_session_token = jwt.encode(payload, self.server_private_key, algorithm="RS256")
        
        headers = {"Authorization": f"Bearer {expired_session_token}"}
        r = requests.get(f"{API_URL}/api/verify", headers=headers)
        
        self.assertEqual(r.status_code, 401)
        self.assertIn("expired", r.text.lower())

    def test_3_2_jwt_manipulation(self):
        # Case 3.2: JWT Payload Manipulation
        # Kẻ tấn công sửa đổi sub sang admin và ký bằng khóa riêng giả mạo
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rogue_pem = rogue_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        payload = {
            "sub": "admin",
            "name": "Administrator (Fake)",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        manipulated_token = jwt.encode(payload, rogue_pem, algorithm="RS256")
        
        headers = {"Authorization": f"Bearer {manipulated_token}"}
        r = requests.get(f"{API_URL}/api/verify", headers=headers)
        
        self.assertEqual(r.status_code, 401)
        self.assertIn("invalid session token", r.text.lower())

    def test_3_3_asymmetric_validation(self):
        # Case 3.3: Asymmetric Validation
        # 1. Tải Public Key từ server
        r = requests.get(f"{API_URL}/api/certs")
        self.assertEqual(r.status_code, 200)
        public_key_pem = r.json().get("public_key")
        self.assertIsNotNone(public_key_pem)
        
        # 2. Tạo một token hợp lệ
        payload = {
            "sub": "bruce_wayne",
            "name": "Bruce Wayne",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        token = jwt.encode(payload, self.server_private_key, algorithm="RS256")
        
        # 3. Verify locally sử dụng public key tải về
        decoded = jwt.decode(token, public_key_pem, algorithms=["RS256"])
        self.assertEqual(decoded.get("sub"), "bruce_wayne")
        self.assertEqual(decoded.get("name"), "Bruce Wayne")

    def test_3_4_mitm_substitution(self):
        # Case 3.4: MITM Substitution
        # Giả lập kẻ tấn công đánh chặn public key và thay bằng public key giả của chúng (rogue public key)
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rogue_private_pem = rogue_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        rogue_public_pem = rogue_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Kẻ tấn công tạo token mạo danh và ký bằng khóa riêng giả
        payload = {
            "sub": "admin",
            "name": "Administrator (Fake)",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        token = jwt.encode(payload, rogue_private_pem, algorithm="RS256")
        
        # Client nhận được khóa công khai giả mạo (được tráo đổi trên đường truyền)
        swapped_public_pem = rogue_public_pem
        
        # Client xác thực token sử dụng khóa giả mạo -> sẽ BỊ LỪA chấp nhận token
        decoded = jwt.decode(token, swapped_public_pem, algorithms=["RS256"])
        self.assertEqual(decoded.get("sub"), "admin")


class TestB4DatabaseAndVaultKMS(SecurityTestBase):
    """
    Bảng 9: Kịch bản kiểm thử An toàn Cơ sở dữ liệu & Quản lý Khóa (Vault KMS)
    """
    def test_4_1_identity_collision(self):
        # Case 4.1: Identity Collision (Register duplicate user)
        username = "collision_user"
        self.cleanup_user(username)
        
        # Register first time
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": username, "full_name": "Legit User", "liveness_enabled": "false"}
            r1 = requests.post(f"{API_URL}/api/register", data=data, files=files)
        self.assertEqual(r1.status_code, 200)
        
        # Register second time (Collision)
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": username, "full_name": "Attacker Overwrite", "liveness_enabled": "false"}
            r2 = requests.post(f"{API_URL}/api/register", data=data, files=files)
            
        self.assertEqual(r2.status_code, 400)
        self.assertIn("already registered", r2.text.lower())
        self.cleanup_user(username)

    def test_4_2_data_leakage(self):
        # Case 4.2: Data Leakage (Read DB directly)
        username = "leak_test_user"
        self.cleanup_user(username)
        
        # Register user
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": username, "full_name": "Leak User", "liveness_enabled": "false"}
            requests.post(f"{API_URL}/api/register", data=data, files=files)
            
        # Connect directly to DB and fetch
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT face_embedding_encrypted FROM users WHERE username = ?;", (username,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        self.assertIsNotNone(row)
        encrypted_embedding = row[0]
        # Chứng minh dữ liệu đã được mã hóa ở định dạng Vault (bắt đầu bằng vault:v1:)
        self.assertTrue(encrypted_embedding.startswith("vault:v1:"))
        self.cleanup_user(username)

    def test_4_3_vault_token_compromise(self):
        # Case 4.3: Vault Token Compromise (Online Decryption using Vault Client)
        if not self.vault_token:
            raise unittest.SkipTest("VAULT_TOKEN not configured in .env for direct Vault API validation.")
            
        username = "compromise_test_user"
        self.cleanup_user(username)
        
        # 1. Register user
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": username, "full_name": "Compromise User", "liveness_enabled": "false"}
            requests.post(f"{API_URL}/api/register", data=data, files=files)
            
        # 2. Get encrypted embedding from DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT face_embedding_encrypted FROM users WHERE username = ?;", (username,))
        ciphertext = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        # 3. Call Vault decryption REST API directly using compromised token
        headers = {"X-Vault-Token": self.vault_token}
        r = requests.post(
            f"{self.vault_url}/v1/transit/decrypt/transit-key",
            headers=headers,
            json={"ciphertext": ciphertext}
        )
        self.assertEqual(r.status_code, 200)
        
        # 4. Decode base64 to retrieve list
        plaintext_b64 = r.json()['data']['plaintext']
        import base64
        vec_str = base64.b64decode(plaintext_b64).decode('utf-8')
        embedding = json.loads(vec_str)
        
        self.assertIsInstance(embedding, list)
        self.assertEqual(len(embedding), 512)
        self.cleanup_user(username)

    def test_4_4_key_export_attempt(self):
        # Case 4.4: Master Key Export Attempt
        if not self.vault_token:
            raise unittest.SkipTest("VAULT_TOKEN not configured in .env for Vault export check.")
            
        headers = {"X-Vault-Token": self.vault_token}
        r = requests.get(
            f"{self.vault_url}/v1/transit/export/encryption-key/transit-key",
            headers=headers
        )
        # Vault must refuse to export the transit-key (returns 400 Bad Request)
        self.assertEqual(r.status_code, 400)
        self.assertIn("not exportable", r.text.lower())

    def test_4_5_account_lockout(self):
        # Case 4.5: Account Lockout
        username = "locked_test_user"
        self.cleanup_user(username)
        
        # 1. Register user
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": username, "full_name": "Locked User", "liveness_enabled": "false"}
            requests.post(f"{API_URL}/api/register", data=data, files=files)
            
        # 2. Lock user in DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?;", (username,))
        conn.commit()
        cursor.close()
        conn.close()
        
        # 3. Attempt challenge & login
        token = self.get_challenge_token(username, "NORMAL")
        self.assertIsNotNone(token)
        
        with open(IMAGE_PATH, "rb") as f:
            files = {"file": ("face.png", f, "image/png")}
            data = {"username": username, "challenge_token": token, "liveness_enabled": "false"}
            r = requests.post(f"{API_URL}/api/login", data=data, files=files)
            
        # Should return 403 Forbidden
        self.assertEqual(r.status_code, 403)
        self.assertIn("locked", r.text.lower())
        self.cleanup_user(username)


if __name__ == "__main__":
    unittest.main()
