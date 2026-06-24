import os
import sys
import time
import json
import datetime
import secrets

# ANSI Colors for terminal presentation
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_header(title):
    print(f"\n{BLUE}{BOLD}{'='*70}{RESET}")
    print(f"{BLUE}{BOLD}  {title}{RESET}")
    print(f"{BLUE}{BOLD}{'='*70}{RESET}")

# Verify dependencies are installed
try:
    import requests
except ImportError:
    print(f"{RED}Error: 'requests' library is not installed.{RESET}")
    print(f"Please run: {YELLOW}pip install requests{RESET}")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print(f"{RED}Error: 'psycopg2' library is not installed.{RESET}")
    print(f"Please run: {YELLOW}pip install psycopg2-binary{RESET}")
    sys.exit(1)

try:
    import jwt
except ImportError:
    print(f"{RED}Error: 'pyjwt' library is not installed.{RESET}")
    print(f"Please run: {YELLOW}pip install pyjwt{RESET}")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def demo_replay_attack():
    print_header("KỊCH BẢN 1: API REPLAY & CHALLENGE TOKEN ATTACK")
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
        print(f"{GREEN}[+] Lấy token thành công!{RESET}")
        print(f"    Token: {YELLOW}{token[:60]}...{RESET}")
    except requests.exceptions.ConnectionError:
        print(f"{RED}[-] LỖI: Không thể kết nối tới API tại {api_url}.{RESET}")
        print(f"    Vui lòng chạy API service trước (ví dụ: docker-compose up).{RESET}")
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

    # Scenario B: Expired Token Simulation
    print(f"\n{CYAN}[*] Bước 2b: Tấn công Replay - Sử dụng Token hết hạn (Simulated Expiration)...{RESET}")
    jwt_secret = os.getenv("JWT_SECRET", "supersecretjwtkey123!")
    print(f"    Tạo chữ ký challenge_token mới với thời gian hết hạn (exp) trong quá khứ...")
    
    expired_payload = {
        "sub": username,
        "nonce": secrets.token_hex(16),
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10),
        "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=70),
        "type": "challenge"
    }
    expired_token = jwt.encode(expired_payload, jwt_secret, algorithm="HS256")
    print(f"    Expired Token: {YELLOW}{expired_token[:60]}...{RESET}")

    data_payload_expired = {
        'username': username,
        'challenge_token': expired_token,
        'liveness_enabled': 'false'
    }
    print(f"{YELLOW}[!] Đang gửi request đăng nhập bằng Token hết hạn...{RESET}")
    r_expired = requests.post(f"{api_url}/api/login", data=data_payload_expired, files=files)
    print(f"    Mã phản hồi HTTP: {RED if r_expired.status_code >= 400 else GREEN}{r_expired.status_code}{RESET}")
    print(f"    Phản hồi từ Server: {RED}{r_expired.text}{RESET}")
    if r_expired.status_code in [400, 500] and "Biometric challenge token expired" in r_expired.text:
        print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Phát hiện Token hết hạn và từ chối xử lý.{RESET}")
    else:
        print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống chấp nhận token hết hạn.{RESET}")

def demo_jwt_manipulation():
    print_header("KỊCH BẢN 2: JWT SESSION MANIPULATION (GIẢ MẠO PHIÊN)")
    api_url = "http://localhost:8000"
    jwt_secret = os.getenv("JWT_SECRET", "supersecretjwtkey123!")
    
    print(f"{CYAN}[*] Bước 1: Tạo JWT Session Token hợp lệ của user thường ('testuser')...{RESET}")
    valid_payload = {
        "sub": "testuser",
        "name": "Test User",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    valid_token = jwt.encode(valid_payload, jwt_secret, algorithm="HS256")
    print(f"    Valid Token: {GREEN}{valid_token[:60]}...{RESET}")

    print(f"\n{CYAN}[*] Bước 2: Kẻ tấn công sửa payload đổi 'sub' thành 'admin' và ký bằng khóa sai ('wrong_secret')...{RESET}")
    malicious_payload = {
        "sub": "admin",
        "name": "Administrator",
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.timezone.utc)
    }
    manipulated_token = jwt.encode(malicious_payload, "wrong_secret_key_123", algorithm="HS256")
    print(f"    Manipulated Token: {RED}{manipulated_token[:60]}...{RESET}")

    print(f"\n{CYAN}[*] Bước 3: Gửi request xác thực token giả mạo lên API `/api/verify`...{RESET}")
    headers = {"Authorization": f"Bearer {manipulated_token}"}
    try:
        r = requests.get(f"{api_url}/api/verify", headers=headers)
        print(f"    Mã phản hồi HTTP: {RED if r.status_code >= 400 else GREEN}{r.status_code}{RESET}")
        print(f"    Phản hồi từ Server: {RED if r.status_code >= 400 else GREEN}{r.text}{RESET}")
        
        if r.status_code == 401 and "Invalid session token" in r.text:
            print(f"{GREEN}[+] KẾT QUẢ: Phòng thủ THÀNH CÔNG! Signature không hợp lệ và đã bị chặn.{RESET}")
        else:
            print(f"{RED}[-] KẾT QUẢ: Phòng thủ THẤT BẠI! Hệ thống chấp nhận token giả mạo.{RESET}")
    except requests.exceptions.ConnectionError:
        print(f"{RED}[-] LỖI: Không thể kết nối tới API tại {api_url}.{RESET}")

def demo_database_leakage():
    print_header("KỊCH BẢN 3: DATABASE LEAKAGE (RÒ RỈ DỮ LIỆU SINH TRẮC)")
    
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "ekyc_admin")
    db_password = os.getenv("DB_PASSWORD", "SuperStrongPass!No1")
    db_name = os.getenv("DB_NAME", "ekyc_matrix")
    
    print(f"{CYAN}[*] Kết nối trực tiếp cơ sở dữ liệu PostgreSQL tại {db_host}:{db_port}...{RESET}")
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password
        )
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
        print(f"\n{GREEN}[+] KẾT QUẢ: Kẻ tấn công có toàn quyền truy cập DB nhưng chỉ lấy được ciphertext dạng 'vault:v1:...'.{RESET}")
        print(f"             Các vector đặc trưng gốc của khuôn mặt được mã hóa an toàn qua HashiCorp Vault Transit Engine.{RESET}")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"{RED}[-]- LỖI: Không thể kết nối tới cơ sở dữ liệu.{RESET}")
        print(f"    Chi tiết: {e}")
        print(f"    (Hãy chắc chắn cổng {db_port} đã được map ra ngoài host hoặc kiểm tra cấu hình .env){RESET}")

def main():
    while True:
        print(f"\n{BLUE}{BOLD}==================================================={RESET}")
        print(f"{BLUE}{BOLD}   HỆ THỐNG DEMO TẤN CÔNG & PHÒNG THỦ (eKYC API)   {RESET}")
        print(f"{BLUE}{BOLD}==================================================={RESET}")
        print(f" 1. Demo Tấn công Replay API (Challenge Token)")
        print(f" 2. Demo Tấn công Sửa đổi JWT Token (Session Hijack)")
        print(f" 3. Demo Tấn công Đọc trộm Cơ sở dữ liệu (Database Leak)")
        print(f" 4. Thoát")
        print(f"{BLUE}---------------------------------------------------{RESET}")
        try:
            choice = input(f"{BOLD}Chọn chức năng (1-4): {RESET}").strip()
            if choice == '1':
                demo_replay_attack()
            elif choice == '2':
                demo_jwt_manipulation()
            elif choice == '3':
                demo_database_leakage()
            elif choice == '4':
                print(f"{GREEN}Tạm biệt.{RESET}")
                break
            else:
                print(f"{RED}Lựa chọn không hợp lệ. Vui lòng nhập từ 1 đến 4.{RESET}")
        except KeyboardInterrupt:
            print(f"\n{GREEN}Tạm biệt.{RESET}")
            break

if __name__ == "__main__":
    main()
