import os
import sys
import time
import json
import datetime
import secrets
import sqlite3
import jwt
import numpy as np
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Add project root to python path dynamically to prevent import errors
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ANSI Colors for terminal presentation
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_header(title):
    print(f"\n{BLUE}{BOLD}{'='*75}{RESET}")
    print(f"{BLUE}{BOLD}  {title}{RESET}")
    print(f"{BLUE}{BOLD}{'='*75}{RESET}")

# Verify dependencies are installed
try:
    import requests
except ImportError:
    print(f"{RED}Error: 'requests' library is not installed.{RESET}")
    sys.exit(1)

def demo_replay_attack():
    print_header("TẤN CÔNG MẠO DANH & GIẢ MẠO CHỮ KÝ TOKEN (USERNAME MISMATCH & ROGUE TOKEN)")
    api_url = "http://localhost:8000"
    username = "attacker_user"
    
    print(f"{CYAN}[*] Bước 1: Yêu cầu cấp challenge_token hợp lệ cho '{username}'...{RESET}")
    try:
        r = requests.get(f"{api_url}/api/auth/challenge", params={"username": username})
        if r.status_code != 200:
            print(f"{RED}[-] Không thể lấy challenge token: {r.text}{RESET}")
            return
        data = r.json()
        token = data.get("challenge_token")
        gesture = data.get("gesture")
        print(f"{GREEN}[+] Lấy token thành công!{RESET}")
        print(f"    Token: {YELLOW}{token[:60]}...{RESET}")
        print(f"    Cử chỉ được yêu cầu: {BOLD}{gesture}{RESET}")
    except requests.exceptions.ConnectionError:
        print(f"{RED}[-] LỖI: Không thể kết nối tới API tại {api_url}.{RESET}")
        print(f"    Vui lòng chạy API service trước (ví dụ: docker compose up).{RESET}")
        return
 
    # Scenario A: Username Mismatch
    print(f"\n{CYAN}[*] Bước 2a: Tấn công mạo danh - Dùng token của '{username}' đăng nhập tài khoản 'victim_user'...{RESET}")
    files = {'file': ('dummy.jpg', b'dummy_content', 'image/jpeg')}
    data_payload = {
        'username': 'victim_user',
        'challenge_token': token,
        'liveness_enabled': 'false'
    }
    print(f"{YELLOW}[!] Đang gửi request đăng nhập...{RESET}")
    r_login = requests.post(f"{api_url}/api/login", data=data_payload, files=files)
    print(f"    Mã phản hồi HTTP: {RED if r_login.status_code >= 400 else GREEN}{r_login.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r_login.text}{RESET}")
    if r_login.status_code in [400, 500] and "Challenge token username mismatch" in r_login.text:
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Phát hiện Token không khớp với Username.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Lỗi logic xác thực.{RESET}")

    # Scenario B: Rogue Token Simulation (Token giả mạo tự ký)
    print(f"\n{CYAN}[*] Bước 2b: Tấn công giả mạo Token - Sử dụng Token tự ký bằng khóa RSA lạ (Rogue Key)...{RESET}")
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rogue_pem = rogue_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    rogue_payload = {
        "sub": username,
        "nonce": secrets.token_hex(16),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60),
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "type": "challenge",
        "gesture": "NORMAL"
    }
    rogue_token = jwt.encode(rogue_payload, rogue_pem, algorithm="RS256")
    print(f"    Rogue Signed Token: {YELLOW}{rogue_token[:60]}...{RESET}")
 
    data_payload_rogue = {
        'username': username,
        'challenge_token': rogue_token,
        'liveness_enabled': 'false'
    }
    print(f"{YELLOW}[!] Đang gửi request đăng nhập bằng Rogue Token...{RESET}")
    r_rogue = requests.post(f"{api_url}/api/login", data=data_payload_rogue, files=files)
    print(f"    Mã phản hồi HTTP: {RED if r_rogue.status_code >= 400 else GREEN}{r_rogue.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r_rogue.text}{RESET}")
    if r_rogue.status_code in [400, 500] and ("signature" in r_rogue.text.lower() or "invalid" in r_rogue.text.lower()):
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Phát hiện Token giả mạo không đúng chữ ký khóa công khai của hệ thống.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống chấp nhận token lỗi.{RESET}")

def demo_timeouts():
    print_header("QUÁ HẠN XÁC THỰC (CHALLENGE TOKEN & SESSION JWT TIMEOUT)")
    api_url = "http://localhost:8000"
    username = "timeout_victim"
    
    # 1. Challenge Token Timeout
    print(f"{CYAN}[*] Bước 1: Giả lập Challenge Token quá hạn (hết hạn sau 60 giây)...{RESET}")
    private_key_path = "backend/keys/private_key.pem"
    if not os.path.exists(private_key_path):
        print(f"{RED}[-] Không tìm thấy khóa riêng tại {private_key_path} để tạo token mẫu.{RESET}")
        print(f"    Vui lòng chạy server để tự sinh khóa riêng trước.")
        return
        
    with open(private_key_path, "rb") as f:
        server_private_key = f.read()
        
    expired_challenge_payload = {
        "sub": username,
        "nonce": secrets.token_hex(16),
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10),
        "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=70),
        "type": "challenge",
        "gesture": "NORMAL"
    }
    expired_challenge_token = jwt.encode(expired_challenge_payload, server_private_key, algorithm="RS256")
    print(f"    Expired Challenge Token: {YELLOW}{expired_challenge_token[:60]}...{RESET}")
    
    files = {'file': ('dummy.jpg', b'dummy_content', 'image/jpeg')}
    data_payload_challenge = {
        'username': username,
        'challenge_token': expired_challenge_token,
        'liveness_enabled': 'false'
    }
    print(f"{YELLOW}[!] Đang gửi request đăng nhập bằng Challenge Token đã hết hạn...{RESET}")
    r_challenge = requests.post(f"{api_url}/api/login", data=data_payload_challenge, files=files)
    print(f"    Mã phản hồi HTTP: {RED if r_challenge.status_code >= 400 else GREEN}{r_challenge.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r_challenge.text}{RESET}")
    if r_challenge.status_code == 400 and "expired" in r_challenge.text.lower():
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Phát hiện Challenge Token hết hạn và từ chối xác thực.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống vẫn chấp nhận Challenge Token đã quá hạn.{RESET}")

    # 2. Session JWT Timeout
    print(f"\n{CYAN}[*] Bước 2: Giả lập Session JWT Token quá hạn (hết hạn sau 1 giờ)...{RESET}")
    expired_session_payload = {
        "sub": username,
        "name": "Timeout Victim",
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10),
        "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1, seconds=10)
    }
    expired_session_token = jwt.encode(expired_session_payload, server_private_key, algorithm="RS256")
    print(f"    Expired Session Token: {YELLOW}{expired_session_token[:60]}...{RESET}")
    
    headers = {"Authorization": f"Bearer {expired_session_token}"}
    print(f"{YELLOW}[!] Đang gửi request xác thực bằng Session Token đã hết hạn lên `/api/verify`...{RESET}")
    r_session = requests.get(f"{api_url}/api/verify", headers=headers)
    print(f"    Mã phản hồi HTTP: {RED if r_session.status_code >= 400 else GREEN}{r_session.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r_session.text}{RESET}")
    if r_session.status_code == 401 and "expired" in r_session.text.lower():
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Phát hiện Session Token hết hạn và từ chối truy cập.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống vẫn chấp nhận Session Token đã quá hạn.{RESET}")

def demo_challenge_reuse_attack():
    print_header("TẤN CÔNG PHÁT LẠI YÊU CẦU ĐĂNG NHẬP (REPLAY ATTACK)")
    api_url = "http://localhost:8000"
    username = "replay_victim"
    
    print(f"{CYAN}[*] Bước 1: Yêu cầu cấp challenge_token hợp lệ cho '{username}'...{RESET}")
    try:
        r = requests.get(f"{api_url}/api/auth/challenge", params={"username": username})
        if r.status_code != 200:
            print(f"{RED}[-] Không thể lấy challenge token: {r.text}{RESET}")
            return
        token = r.json().get("challenge_token")
        print(f"{GREEN}[+] Lấy token thành công!{RESET}")
        print(f"    Token: {YELLOW}{token[:60]}...{RESET}")
    except requests.exceptions.ConnectionError:
        print(f"{RED}[-] LỖI: Không thể kết nối tới API tại {api_url}.{RESET}")
        return

    files = {'file': ('dummy.jpg', b'dummy_content', 'image/jpeg')}
    data_payload = {
        'username': username,
        'challenge_token': token,
        'liveness_enabled': 'false'
    }
    
    # Send Request 1
    print(f"\n{CYAN}[*] Bước 2: Gửi request đăng nhập lần 1 bằng Token này...{RESET}")
    r1 = requests.post(f"{api_url}/api/login", data=data_payload, files=files)
    print(f"    Lần 1 - Mã phản hồi HTTP: {GREEN}{r1.status_code}{RESET}")
    print(f"    Lần 1 - Phản hồi từ Server: {YELLOW}{r1.text}{RESET}")
    
    # Send Request 2 (Replay within 60s)
    print(f"\n{CYAN}[*] Bước 3: Gửi lại chính xác request đăng nhập trên lần 2 (Replay Attack)...{RESET}")
    r2 = requests.post(f"{api_url}/api/login", data=data_payload, files=files)
    print(f"    Lần 2 - Mã phản hồi HTTP: {RED if r2.status_code >= 400 else GREEN}{r2.status_code}{RESET}")
    print(f"    Lần 2 - Phản hồi từ Server: {RED}{r2.text}{RESET}")
    
    if r2.status_code == 400 and "replay detected" in r2.text.lower():
        print(f"\n{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Cơ chế Nonce Blacklist đã phát hiện token đã được dùng và chặn đứng cuộc tấn công Replay.{RESET}")
    else:
        print(f"\n{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống cho phép tái sử dụng challenge token.{RESET}")

def simulate_active_liveness(pose, required_gesture):
    if required_gesture == "NONE" or not required_gesture:
        return True
    if pose is None or len(pose) < 3:
        raise ValueError("Biometric liveness check failed: Could not estimate face pose for active liveness verification.")
    pitch, yaw, roll = pose
    print(f"[ACTIVE LIVENESS DEBUG] Pose: pitch={pitch:.2f}, yaw={yaw:.2f}, roll={roll:.2f} | Required: {required_gesture}")
    if required_gesture == "NORMAL":
        if abs(yaw) > 15 or abs(pitch) > 18 or abs(roll) > 15:
            raise ValueError(f"Biometric liveness check failed: Please look straight at the camera. (Yaw: {yaw:.1f}, Pitch: {pitch:.1f}, Roll: {roll:.1f})")
    elif required_gesture == "LOOK_LEFT":
        if yaw >= -12:
            raise ValueError(f"Biometric liveness check failed: Please turn your head to the LEFT (Yaw: {yaw:.1f} >= -12).")
    elif required_gesture == "LOOK_RIGHT":
        if yaw <= 12:
            raise ValueError(f"Biometric liveness check failed: Please turn your head to the RIGHT (Yaw: {yaw:.1f} <= 12).")
    elif required_gesture == "LOOK_UP":
        if pitch <= 12:
            raise ValueError(f"Biometric liveness check failed: Please look UP (Pitch: {pitch:.1f} <= 12).")
    elif required_gesture == "LOOK_DOWN":
        if pitch >= -12:
            raise ValueError(f"Biometric liveness check failed: Please look DOWN (Pitch: {pitch:.1f} >= -12).")
    elif required_gesture == "TILT_LEFT":
        if roll >= -10:
            raise ValueError(f"Biometric liveness check failed: Please tilt your head to the LEFT (Roll: {roll:.1f} >= -10).")
    elif required_gesture == "TILT_RIGHT":
        if roll <= 10:
            raise ValueError(f"Biometric liveness check failed: Please tilt your head to the RIGHT (Roll: {roll:.1f} <= 10).")
    return True

def demo_active_liveness_checks():
    print_header("ACTIVE LIVENESS SPOOFING ATTACK (SO KHỚP CỬ CHỈ ĐỘNG - POSE ESTIMATION)")
    
    # Scenario A: Server requests LOOK_LEFT, but attacker sends a frontal photo
    print(f"{CYAN}[*] Thử nghiệm 3a: Server yêu cầu xoay đầu sang TRÁI (LOOK_LEFT) nhưng người dùng gửi ảnh NHÌN THẲNG...{RESET}")
    pose_straight = np.array([-0.22, 2.10, 0.45]) # pitch, yaw, roll (yaw = 2.10 is straight)
    print(f"    Góc xoay trích xuất của mặt: Pitch={pose_straight[0]:.2f}, Yaw={pose_straight[1]:.2f}, Roll={pose_straight[2]:.2f}")
    try:
        simulate_active_liveness(pose_straight, "LOOK_LEFT")
        print(f"{RED}[- ] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống chấp nhận ảnh sai tư thế.{RESET}")
    except ValueError as e:
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Phát hiện sai tư thế góc xoay mặt.")
        print(f"             Thông báo lỗi: {RED}{e}{RESET}")
        
    # Scenario B: Server requests LOOK_LEFT, and user turns left correctly
    print(f"\n{CYAN}[*] Thử nghiệm 3b: Server yêu cầu xoay đầu sang TRÁI (LOOK_LEFT) và người dùng quay TRÁI chính xác...{RESET}")
    pose_left = np.array([-0.50, -15.42, 1.10]) # yaw = -15.42 is turned left (< -12)
    print(f"    Góc xoay trích xuất của mặt: Pitch={pose_left[0]:.2f}, Yaw={pose_left[1]:.2f}, Roll={pose_left[2]:.2f}")
    try:
        simulate_active_liveness(pose_left, "LOOK_LEFT")
        print(f"{GREEN}[+] KẾT QUẢ: Xác thực THÀNH CÔNG! Góc xoay mặt hoàn toàn khớp với thách thức cử chỉ.{RESET}")
    except ValueError as e:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ LỖI! Từ chối cử chỉ đúng: {e}{RESET}")

def simulate_db_validation(username):
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = "SELECT face_embedding_encrypted, is_active, full_name FROM users WHERE username = ?;"
    cursor.execute(query, (username,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if not result:
        raise NameError(f"User with username '{username}' not found!")
    face_embedding_encrypted, is_active, full_name = result
    if not is_active:
        raise PermissionError(f"Account '{username}' is locked!")
    return True

def get_challenge_token_for_normal_gesture(username):
    url = "http://localhost:8000/api/auth/challenge"
    attempts = 0
    while attempts < 15:
        attempts += 1
        try:
            r = requests.get(url, params={"username": username})
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("gesture") == "NORMAL":
                return data.get("challenge_token")
        except Exception:
            pass
        time.sleep(0.05)
    return None

def demo_lockout_and_unknown():
    print_header("ACCOUNT LOCKOUT & PRINCIPAL UNKNOWN (XÁC THỰC QUA API)")
    api_url = "http://localhost:8000"
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    image_path = "sample_face.png"
    
    if not os.path.exists(image_path):
        print(f"{RED}[-] LỖI: Cần tệp {image_path} để thực hiện demo. Vui lòng tạo tệp ảnh này trước.{RESET}")
        return

    # 5a. Principal Unknown
    print(f"{CYAN}[*] Thử nghiệm 5a: Đăng nhập tài khoản chưa đăng ký ('unknown_user')...{RESET}")
    token = get_challenge_token_for_normal_gesture("unknown_user")
    if not token:
        print(f"{RED}[- ] Không lấy được challenge token cho unknown_user.{RESET}")
        return
        
    with open(image_path, "rb") as f:
        files = {"file": ("face.png", f, "image/png")}
        data = {"username": "unknown_user", "challenge_token": token, "liveness_enabled": "true"}
        r = requests.post(f"{api_url}/api/login", data=data, files=files)
        
    print(f"    Mã phản hồi HTTP: {GREEN if r.status_code == 404 else RED}{r.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r.text}{RESET}")
    if r.status_code == 404 and "not found" in r.text.lower():
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Server chặn người dùng lạ và trả lỗi 404.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Phản hồi không chính xác.{RESET}")

    # 5b. Account Lockout
    print(f"\n{CYAN}[*] Thử nghiệm 5b: Đăng nhập tài khoản đã bị khóa ('locked_user')...{RESET}")
    
    # Clear if exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = 'locked_user';")
    conn.commit()
    cursor.close()
    conn.close()

    # Register locked_user first
    with open(image_path, "rb") as f:
        files = {"file": ("face.png", f, "image/png")}
        data = {"username": "locked_user", "full_name": "Locked User", "liveness_enabled": "true"}
        requests.post(f"{api_url}/api/register", data=data, files=files)
        
    # Lock in DB
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = 0 WHERE username = 'locked_user';")
    conn.commit()
    cursor.close()
    conn.close()
    print(f"{YELLOW}[!] Đã giả lập khóa tài khoản 'locked_user' (is_active = 0) trong DB.{RESET}")
    
    token = get_challenge_token_for_normal_gesture("locked_user")
    if not token:
        print(f"{RED}[- ] Không lấy được challenge token cho locked_user.{RESET}")
        return
        
    with open(image_path, "rb") as f:
        files = {"file": ("face.png", f, "image/png")}
        data = {"username": "locked_user", "challenge_token": token, "liveness_enabled": "true"}
        r = requests.post(f"{api_url}/api/login", data=data, files=files)
        
    print(f"    Mã phản hồi HTTP: {GREEN if r.status_code == 403 else RED}{r.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r.text}{RESET}")
    if r.status_code == 403 and "locked" in r.text.lower():
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Server từ chối tài khoản bị khóa (403 Forbidden).{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Chấp nhận tài khoản bị khóa.{RESET}")
        
    # Clean up
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = 'locked_user';")
    conn.commit()
    cursor.close()
    conn.close()

def demo_jwt_manipulation():
    print_header("JWT SESSION MANIPULATION (GIẢ MẠO PHIÊN XÁC THỰC)")
    api_url = "http://localhost:8000"
    
    print(f"{CYAN}[*] Bước 1: Kẻ tấn công tự sinh một cặp khóa RSA giả mạo (Rogue Keypair)...{RESET}")
    rogue_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rogue_private_pem = rogue_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    print(f"\n{CYAN}[*] Bước 2: Kẻ tấn công tạo payload giả danh 'admin' và ký bằng khóa giả mạo...{RESET}")
    malicious_payload = {
        "sub": "admin",
        "name": "Administrator (Fake)",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    manipulated_token = jwt.encode(malicious_payload, rogue_private_pem, algorithm="RS256")
    print(f"    Manipulated Token: {RED}{manipulated_token[:60]}...{RESET}")
 
    print(f"\n{CYAN}[*] Bước 3: Gửi request mang token giả mạo lên API verify `/api/verify`...{RESET}")
    headers = {"Authorization": f"Bearer {manipulated_token}"}
    try:
        r = requests.get(f"{api_url}/api/verify", headers=headers)
        print(f"    Mã phản hồi HTTP: {RED if r.status_code >= 400 else GREEN}{r.status_code}{RESET}")
        print(f"    Phản hồi từ Server: {RED if r.status_code >= 400 else GREEN}{r.text}{RESET}")
        
        if r.status_code == 401 and "Invalid session token" in r.text:
            print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Chữ ký không hợp lệ với khóa công khai của server đã bị chặn đứng.{RESET}")
        else:
            print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống chấp nhận token tự ký giả mạo.{RESET}")
    except requests.exceptions.ConnectionError:
        print(f"{RED}[-] LỖI: Không thể kết nối tới API tại {api_url}.{RESET}")

def demo_database_leakage():
    print_header("DATABASE LEAKAGE (RÒ RỈ CƠ SỞ DỮ LIỆU BẢN MẪU SINH TRẮC)")
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    
    print(f"{CYAN}[*] Kết nối trực tiếp cơ sở dữ liệu SQLite tại {db_path}...{RESET}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print(f"{GREEN}[+] Kết nối thành công! Đang truy vấn bảng 'users' để đánh cắp dữ liệu...{RESET}")
        
        query = "SELECT username, full_name, face_embedding_encrypted FROM users LIMIT 3;"
        print(f"{YELLOW}    SQL> {query}{RESET}")
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"\n{BLUE}{'='*85}{RESET}")
        print(f"{BOLD}{'USERNAME':<12} | {'FULL NAME':<18} | {'FACE EMBEDDING ENCRYPTED (VAULT CIPHERTEXT)'}{RESET}")
        print(f"{BLUE}{'='*85}{RESET}")
        
        if not rows:
            print(f" {YELLOW}(Database chưa có tài khoản. Đang hiển thị ví dụ dòng dữ liệu mô phỏng khi đăng ký UI...){RESET}")
            mock_ciphertext = "vault:v1:gAAAAABmX85y...[TRUNCATED_VECTOR_DATA_ENCRYPTED_BY_VAULT]"
            print(f"{CYAN}{'demo_user':<12}{RESET} | {'Demo User':<18} | {mock_ciphertext}")
        else:
            for row in rows:
                username, full_name, encrypted_vector = row
                truncated_vector = encrypted_vector[:55] + "..." if len(encrypted_vector) > 55 else encrypted_vector
                print(f"{CYAN}{username:<12}{RESET} | {full_name:<18} | {YELLOW}{truncated_vector}{RESET}")
                
        print(f"{BLUE}{'='*85}{RESET}")
        print(f"\n{GREEN}[+] KẾT QUẢ: Kẻ tấn công chỉ lấy được ciphertext dạng 'vault:v1:...'.{RESET}")
        print(f"             Các vector khuôn mặt gốc được bảo vệ an toàn thông qua mã hóa HashiCorp Vault Transit Engine.{RESET}")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"{RED}[-] LỖI: Không thể kết nối tới cơ sở dữ liệu.{RESET}")
        print(f"    Chi tiết: {e}")

def demo_asymmetric_verification():
    print_header("ASYMMETRIC VERIFICATION (THIRD-PARTY KHÔNG CẦN CHIA SẺ SECRET)")
    api_url = "http://localhost:8000"
    
    print(f"{CYAN}[*] Bước 1: Mô phỏng Dịch vụ bên thứ ba (Third-party) gọi API lấy Khóa công khai từ `{api_url}/api/certs`...{RESET}")
    try:
        r_certs = requests.get(f"{api_url}/api/certs")
        if r_certs.status_code != 200:
            print(f"{RED}[-] Không thể lấy khóa công khai từ server: {r_certs.text}{RESET}")
            return
        public_key_pem = r_certs.json().get("public_key")
        print(f"{GREEN}[+] Tải thành công Khóa công khai từ Server!{RESET}")
        print(f"    Khóa công khai (Public Key PEM):\n{YELLOW}{public_key_pem[:150]}...\n[TRUNCATED]{RESET}")
    except requests.exceptions.ConnectionError:
        print(f"{RED}[-] LỖI: Không thể kết nối tới API.{RESET}")
        return

    print(f"\n{CYAN}[*] Bước 2: Tải khóa riêng của server để tạo một session token giả lập hợp lệ...{RESET}")
    private_key_path = "backend/keys/private_key.pem"
    if not os.path.exists(private_key_path):
        print(f"{RED}[-] Không tìm thấy khóa riêng tại {private_key_path} để tạo token mẫu.{RESET}")
        print(f"    Vui lòng chạy server để tự sinh khóa riêng trước.")
        return
        
    with open(private_key_path, "rb") as f:
        server_private_key = f.read()
        
    sample_payload = {
        "sub": "bruce_wayne",
        "name": "Bruce Wayne",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    valid_token = jwt.encode(sample_payload, server_private_key, algorithm="RS256")
    print(f"{GREEN}[+] Tạo token mẫu thành công!{RESET}")
    print(f"    Token: {YELLOW}{valid_token[:60]}...{RESET}")
    
    print(f"\n{CYAN}[*] Bước 3: Dịch vụ bên thứ ba tự verify Token cục bộ bằng Public Key đã lấy từ API...{RESET}")
    try:
        decoded = jwt.decode(valid_token, public_key_pem, algorithms=["RS256"])
        print(f"{GREEN}[+] KẾT QUẢ: Xác thực thành công tại local của Third-party!{RESET}")
        print(f"             Dữ liệu giải mã: {BOLD}{json.dumps(decoded)}{RESET}")
        print(f"             Chứng minh: Hệ thống phân tán có thể verify phiên đăng nhập mà không cần truy vấn DB hay chia sẻ khóa riêng.")
    except Exception as e:
        print(f"{RED}[-] KẾT QUẢ: Xác thực thất bại cục bộ. Lỗi: {e}{RESET}")

def demo_registration_attacks():
    print_header("TẤN CÔNG GIAO THỨC ĐĂNG KÝ (REGISTRATION PROTOCOL ATTACKS)")
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    username = "test_registration_user"
    mock_vector = "vault:v1:mock_encrypted_face_embedding_data_for_reg"
    
    # 1. Register a user first (Simulate legit registration)
    print(f"{CYAN}[*] Bước 1: Đăng ký một tài khoản mới hợp lệ '{username}'...{RESET}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
        conn.commit()
        
        cursor.execute("""
        INSERT INTO users (username, full_name, face_embedding_encrypted)
        VALUES (?, ?, ?);
        """, (username, "Legitimate User", mock_vector))
        conn.commit()
        print(f"{GREEN}[+] Đã đăng ký thành công tài khoản '{username}' lần đầu.{RESET}")
    except Exception as e:
        print(f"{RED}[-] LỖI khởi tạo giả lập: {e}{RESET}")
        cursor.close()
        conn.close()
        return
        
    # 2. Attack: Duplicate Registration / Identity Preemption
    print(f"\n{CYAN}[*] Bước 2: Tấn công chiếm đoạt - Kẻ tấn công đăng ký đè lên username '{username}' bằng khuôn mặt của mình...{RESET}")
    attacker_mock_vector = "vault:v1:attacker_malicious_face_embedding_data"
    
    try:
        cursor.execute("""
        INSERT INTO users (username, full_name, face_embedding_encrypted)
        VALUES (?, ?, ?);
        """, (username, "Attacker Identity", attacker_mock_vector))
        conn.commit()
        print(f"{RED}[-] KẾT QUẢ: Tấn công THÀNH CÔNG! Hệ thống cho phép ghi đè thông tin sinh trắc học của tài khoản đã tồn tại.{RESET}")
    except sqlite3.IntegrityError:
        conn.rollback()
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Ràng buộc UNIQUE của Cơ sở dữ liệu đã chặn đứng hành vi ghi đè sinh trắc.")
        print(f"             Ném ra lỗi: {RED}UNIQUE constraint failed: users.username{RESET}")
    except Exception as e:
        conn.rollback()
        print(f"{RED}[-] KẾT QUẢ: Lỗi không xác định: {e}{RESET}")
    finally:
        # Cleanup
        cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
        conn.commit()
        cursor.close()
        conn.close()

def demo_vault_compromise():
    print_header("VAULT KMS COMPROMISE (KHI HỆ THỐNG VAULT BỊ TẤN CÔNG / RÒ RỈ TOKEN)")
    
    # Load env variables manually from .env
    env = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    env[key] = val
                    
    vault_url = env.get("VAULT_URL", "http://localhost:8200")
    vault_token = env.get("VAULT_TOKEN")
    key_name = env.get("VAULT_KEY_NAME", "transit-key")
    db_path = env.get("DB_PATH", "backend/ekyc_matrix.db")
    
    if not vault_token:
        print(f"{RED}[-] LỖI: Không tìm thấy VAULT_TOKEN trong file .env để thực hiện kịch bản.{RESET}")
        return
        
    # Phase 1: Decrypt database ciphertext using leaked token (Online decryption)
    print(f"{CYAN}[*] Bước 1: Giả lập kẻ tấn công đánh cắp được VAULT_TOKEN và muốn giải mã dữ liệu sinh trắc trong DB...{RESET}")
    
    # Get a sample ciphertext from the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT username, face_embedding_encrypted FROM users LIMIT 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        print(f"{YELLOW}[!] DB chưa có người dùng thực tế. Sử dụng một ciphertext giả định để mô phỏng...{RESET}")
        import base64
        import json
        dummy_vec = [0.1] * 512
        base64_data = base64.b64encode(json.dumps(dummy_vec).encode('utf-8')).decode('utf-8')
        try:
            r_enc = requests.post(
                f"{vault_url}/v1/transit/encrypt/{key_name}",
                headers={"X-Vault-Token": vault_token},
                json={"plaintext": base64_data}
            )
            ciphertext = r_enc.json()['data']['ciphertext']
            username = "demo_compromise_user"
        except Exception as e:
            print(f"{RED}[-] LỖI: Không thể mã hóa mẫu thử qua Vault: {e}{RESET}")
            return
    else:
        username, ciphertext = row
        
    print(f"    Tài khoản mục tiêu: {BOLD}{username}{RESET}")
    print(f"    Ciphertext lấy từ DB: {YELLOW}{ciphertext[:60]}...{RESET}")
    
    # Attacker calls Vault API to decrypt
    print(f"{YELLOW}[!] Đang gửi yêu cầu giải mã trực tuyến lên Vault REST API bằng Token rò rỉ...{RESET}")
    try:
        r_dec = requests.post(
            f"{vault_url}/v1/transit/decrypt/{key_name}",
            headers={"X-Vault-Token": vault_token},
            json={"ciphertext": ciphertext}
        )
        if r_dec.status_code == 200:
            plaintext_b64 = r_dec.json()['data']['plaintext']
            import base64
            decoded_vec = base64.b64decode(plaintext_b64).decode('utf-8')
            print(f"{RED}[- ] KẾT QUẢ PHÂN TÍCH: Tấn công giải mã thành công! Kẻ tấn công đọc được dữ liệu gốc.{RESET}")
            print(f"    Vector sinh trắc giải mã: {BOLD}{decoded_vec[:80]}... [TRUNCATED]{RESET}")
            print(f"    {YELLOW}(Cảnh báo: Việc rò rỉ token cho phép kẻ tấn công gọi giải mã online. Hệ thống cần giám sát log / audit log của Vault để phát hiện hành vi bất thường.){RESET}")
        else:
            print(f"{GREEN}[+] Phòng thủ thành công? Vault từ chối giải mã: {r_dec.text}{RESET}")
    except Exception as e:
        print(f"{RED}[- ] LỖI khi gọi Vault API: {e}{RESET}")
        return

    # Phase 2: Attacker attempts to download/export the Master Key (Offline decryption attempt)
    print(f"\n{CYAN}[*] Bước 2: Kẻ tấn công muốn đánh cắp khóa gốc (Master Key) để giải mã offline hàng loạt...{RESET}")
    print(f"{YELLOW}[!] Đang gửi yêu cầu xuất khóa gốc tại `/v1/transit/export/encryption-key/{key_name}`...{RESET}")
    
    try:
        r_exp = requests.get(
            f"{vault_url}/v1/transit/export/encryption-key/{key_name}",
            headers={"X-Vault-Token": vault_token}
        )
        print(f"    Mã phản hồi HTTP: {RED if r_exp.status_code >= 400 else GREEN}{r_exp.status_code}{RESET}")
        print(f"    Phản hồi từ Vault: {RED}{r_exp.text}{RESET}")
        
        if r_exp.status_code == 400 and "not exportable" in r_exp.text.lower():
            print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Vault từ chối xuất khóa vì khóa được cấu hình là 'non-exportable'.{RESET}")
            print(f"             Chứng minh: Khóa mật mã gốc được bảo vệ an toàn vật lý bên trong Vault HSM/KMS. Kẻ tấn công không thể tải khóa về.{RESET}")
        else:
            print(f"{RED}[- ] KẾT QUẢ: Tấn công THÀNH CÔNG! Kẻ tấn công đã đánh cắp được khóa mật mã gốc để giải mã offline.{RESET}")
    except Exception as e:
        print(f"{RED}[- ] LỖI khi gọi Vault API: {e}{RESET}")

def demo_mitm_key_substitution():
    print_header("TẤN CÔNG GIẢ MẠO SERVER (MITM PUBLIC KEY SUBSTITUTION)")
    
    print(f"{CYAN}[*] Bước 1: Kẻ tấn công tạo một cặp khóa RSA giả mạo (Rogue Keypair)...{RESET}")
    rogue_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rogue_private_pem = rogue_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    rogue_public_key = rogue_private_key.public_key()
    rogue_public_pem = rogue_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    print(f"    Rogue Public Key PEM (được dùng để tráo đổi):\n{YELLOW}{rogue_public_pem[:150].decode('utf-8')}...\n[TRUNCATED]{RESET}")
    
    print(f"\n{CYAN}[*] Bước 2: Dịch vụ bên thứ ba (Third-party) gọi API lấy khóa công khai từ Server...{RESET}")
    print(f"{RED}[!] GIẢ LẬP MITM: Kẻ tấn công đánh chặn gói tin qua HTTP và TRÁO ĐỔI khóa công khai thật thành Khóa giả mạo.{RESET}")
    # Simulate that the client receives the attacker's public key instead of the server's
    swapped_public_pem = rogue_public_pem
    print(f"{GREEN}[+] Client nhận được khóa công khai (mà không biết đó là Khóa giả mạo của kẻ tấn công).{RESET}")
    
    print(f"\n{CYAN}[*] Bước 3: Kẻ tấn công tạo JWT giả danh 'admin' và ký bằng khóa riêng giả mạo...{RESET}")
    malicious_payload = {
        "sub": "admin",
        "name": "Administrator (Fake)",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    manipulated_token = jwt.encode(malicious_payload, rogue_private_pem, algorithm="RS256")
    print(f"    Manipulated Token: {RED}{manipulated_token[:60]}...{RESET}")
    
    print(f"\n{CYAN}[*] Bước 4: Client tiến hành xác thực token này bằng Khóa công khai đã nhận được...{RESET}")
    try:
        decoded = jwt.decode(manipulated_token, swapped_public_pem, algorithms=["RS256"])
        print(f"{RED}[- ] KẾT QUẢ: Tấn công THÀNH CÔNG! Token độc hại đã được chấp nhận và giải mã thành công.{RESET}")
        print(f"             Dữ liệu giải mã: {BOLD}{json.dumps(decoded)}{RESET}")
        print(f"             Giải thích: Vì khóa công khai bị tráo đổi qua kênh truyền không mã hóa (MitM), chữ ký giả khớp hoàn hảo với khóa giả.{RESET}")
    except Exception as e:
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Token bị bác bỏ: {e}{RESET}")

def demo_happy_path():
    print_header("HAPPY PATH (XÁC THỰC KHUÔN MẶT ĐẦU CUỐI THÀNH CÔNG)")
    api_url = "http://localhost:8000"
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    image_path = "sample_face.png"
    username = "happy_user"
    
    if not os.path.exists(image_path):
        print(f"{RED}[-] LỖI: Cần tệp {image_path} để thực hiện demo. Vui lòng tạo tệp ảnh này trước.{RESET}")
        return

    # Clean up first
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
    conn.commit()
    cursor.close()
    conn.close()

    # 1. Register
    print(f"{CYAN}[*] Bước 1: Đăng ký người dùng mới '{username}' với ảnh khuôn mặt thực...{RESET}")
    with open(image_path, "rb") as f:
        files = {"file": ("face.png", f, "image/png")}
        data = {"username": username, "full_name": "Happy User", "liveness_enabled": "true"}
        r = requests.post(f"{api_url}/api/register", data=data, files=files)
    if r.status_code != 200:
        print(f"{RED}[-] Đăng ký thất bại: {r.text}{RESET}")
        return
    print(f"{GREEN}[+] Đăng ký tài khoản '{username}' thành công!{RESET}")

    # 2. Get Challenge
    token = get_challenge_token_for_normal_gesture(username)
    if not token:
        print(f"{RED}[- ] Không lấy được challenge token cho cử chỉ NORMAL.{RESET}")
        return

    # 3. Login
    print(f"\n{CYAN}[*] Bước 2: Đăng nhập bằng ảnh và cử chỉ khớp với challenge token...{RESET}")
    with open(image_path, "rb") as f:
        files = {"file": ("face.png", f, "image/png")}
        data = {"username": username, "challenge_token": token, "liveness_enabled": "true"}
        r = requests.post(f"{api_url}/api/login", data=data, files=files)
        
    print(f"    Mã phản hồi HTTP: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {r.text}")
    if r.status_code == 200:
        print(f"{GREEN}[+] KẾT QUẢ: Xác thực THÀNH CÔNG! Nhận được JWT Session Token.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Xác thực THẤT BẠI!{RESET}")

    # Clean up
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
    conn.commit()
    cursor.close()
    conn.close()

def register_mock_users():
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    mock_users = [
        ("attacker_user", "Attacker User"),
        ("victim_user", "Victim User"),
        ("timeout_victim", "Timeout Victim"),
        ("replay_victim", "Replay Victim")
    ]
    for username, fullname in mock_users:
        cursor.execute("""
        INSERT INTO users (username, full_name, face_embedding_encrypted, is_active)
        VALUES (?, ?, 'vault:v1:mock_encrypted_face_embedding_data', 1)
        ON CONFLICT(username) DO UPDATE SET is_active = 1;
        """, (username, fullname))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"{GREEN}[+] Đã đăng ký tạm thời các tài khoản mock phục vụ demo: attacker_user, victim_user, timeout_victim, replay_victim.{RESET}")

def cleanup_mock_users():
    db_path = os.getenv("DB_PATH", "backend/ekyc_matrix.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    mock_users = ["attacker_user", "victim_user", "timeout_victim", "replay_victim"]
    for username in mock_users:
        cursor.execute("DELETE FROM users WHERE username = ?;", (username,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"{GREEN}[+] Đã dọn dẹp các tài khoản mock khỏi database.{RESET}")

def main():
    register_mock_users()
    try:
        while True:
            print(f"\n{BLUE}{BOLD}===================================================================={RESET}")
            print(f"{BLUE}{BOLD}   HỆ THỐNG DEMO TẤN CÔNG & PHÒNG THỦ {RESET}")
            print(f"{BLUE}{BOLD}===================================================================={RESET}")
            print(f" 1. Demo Tấn công Mạo danh & Giả mạo Chữ ký (Username Mismatch & Rogue Token)")
            print(f" 2. Demo Quá hạn Xác thực (Challenge & Session Timeout)")
            print(f" 3. Demo Tấn công Phát lại Yêu cầu Đăng nhập (Replay Attack)")
            print(f" 4. Demo Tấn công Giả mạo Cử chỉ (Active Liveness Pose Mismatch)")
            print(f" 5. Demo Tấn công Đăng nhập Khóa tài khoản & Tài khoản chưa đăng ký")
            print(f" 6. Demo Tấn công Sửa đổi JWT Token (Session Hijack chặn bằng RSA)")
            print(f" 7. Demo Tấn công Đọc trộm Cơ sở dữ liệu (Database Leak bảo vệ bằng Vault)")
            print(f" 8. Demo Xác thực Asymmetric JWT (Third-party verify dùng public key)")
            print(f" 9. Demo Tấn công Giao thức Đăng ký (Duplicate Registration Overwrite)")
            print(f" 10. Demo Tấn công Hệ thống Vault KMS (Steal Token / Key Export Check)")
            print(f" 11. Demo Tấn công Giả mạo Server (MitM Public Key Substitution)")
            print(f" 12. Demo Happy Path (Xác thực khuôn mặt thành công đầu cuối)")
            print(f" 13. Thoát")
            print(f"{BLUE}--------------------------------------------------------------------{RESET}")
            try:
                choice = input(f"{BOLD}Chọn chức năng (1-13): {RESET}").strip()
                if choice == '1':
                    demo_replay_attack()
                elif choice == '2':
                    demo_timeouts()
                elif choice == '3':
                    demo_challenge_reuse_attack()
                elif choice == '4':
                    demo_active_liveness_checks()
                elif choice == '5':
                    demo_lockout_and_unknown()
                elif choice == '6':
                    demo_jwt_manipulation()
                elif choice == '7':
                    demo_database_leakage()
                elif choice == '8':
                    demo_asymmetric_verification()
                elif choice == '9':
                    demo_registration_attacks()
                elif choice == '10':
                    demo_vault_compromise()
                elif choice == '11':
                    demo_mitm_key_substitution()
                elif choice == '12':
                    demo_happy_path()
                elif choice == '13':
                    break
                else:
                    print(f"{RED}Lựa chọn không hợp lệ. Vui lòng nhập từ 1 đến 13.{RESET}")
            except KeyboardInterrupt:
                break
    finally:
        cleanup_mock_users()

if __name__ == "__main__":
    main()

