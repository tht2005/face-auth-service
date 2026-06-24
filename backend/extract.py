import cv2
import numpy as np
import insightface
import os

# Initialize InsightFace (default to CPU ctx_id=-1, customizable via env)
ctx_id = int(os.getenv("INSIGHTFACE_CTX_ID", "-1"))
faceapp = insightface.app.FaceAnalysis(name='buffalo_l')
faceapp.prepare(ctx_id=ctx_id, det_size=(640, 640))

def check_passive_liveness(
    img: np.ndarray, 
    bbox: np.ndarray,
    min_laplacian: float = 30.0,
    min_fft: float = 0.05,
    max_fft: float = 0.65,
    max_glare: float = 0.15
) -> bool:
    """
    Analyzes the face region in the image to detect presentation attacks (spoofing).
    Checks:
      1. Laplacian Variance (Texture check for flat/blurry prints)
      2. FFT High-Frequency Ratio (Moiré pattern/screen check)
      3. HSV Glare Ratio (Screen specular reflection check)
    Raises ValueError if spoofing is detected.
    """
    h, w, _ = img.shape
    x1, y1, x2, y2 = bbox.astype(int)
    
    # Clamp bounding box to image bounds
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    
    if (x2 - x1) < 20 or (y2 - y1) < 20:
        raise ValueError("Face is too far or too small. Please move closer to the camera.")
        
    face_img = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    
    # 1. Laplacian Variance Check (Print attack / blurriness)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # 2. FFT Frequency Analysis (Moiré / Screen check)
    gray_resized = cv2.resize(gray, (100, 100))
    f_transform = np.fft.fft2(gray_resized)
    f_shift = np.fft.fftshift(f_transform)
    magnitude_spectrum = np.abs(f_shift)
    
    # Filter out low-frequency center (radius 15)
    cy, cx = 50, 50
    r = 15
    magnitude_spectrum[cy-r:cy+r, cx-r:cx+r] = 0
    
    high_freq_sum = np.sum(magnitude_spectrum)
    total_sum = np.sum(np.abs(f_shift))
    high_freq_ratio = (high_freq_sum / total_sum) if total_sum > 0 else 0
    
    # 3. Specular Glare (HSV) Check
    hsv = cv2.cvtColor(face_img, cv2.COLOR_BGR2HSV)
    h_val, s_val, v_val = cv2.split(hsv)
    glare_pixels = np.sum((v_val > 245) & (s_val < 30))
    glare_ratio = glare_pixels / (v_val.shape[0] * v_val.shape[1])
    
    print(f"[LIVENESS DEBUG] Laplacian Var: {laplacian_var:.2f} (min: {min_laplacian}) | "
          f"FFT Ratio: {high_freq_ratio:.4f} (min: {min_fft}, max: {max_fft}) | "
          f"Glare: {glare_ratio:.4f} (max: {max_glare})")
    
    if laplacian_var < min_laplacian:
        raise ValueError(f"Biometric liveness check failed: Image texture too flat/blurry (Laplacian Var {laplacian_var:.1f} < {min_laplacian}).")
        
    if high_freq_ratio < min_fft:
        raise ValueError(f"Biometric liveness check failed: Lack of high-frequency detail (FFT Ratio {high_freq_ratio:.3f} < {min_fft}).")
        
    if high_freq_ratio > max_fft:
        raise ValueError(f"Biometric liveness check failed: Unnatural high-frequency patterns (FFT Ratio {high_freq_ratio:.3f} > {max_fft}). Possible screen spoof.")
        
    if glare_ratio > max_glare:
        raise ValueError(f"Biometric liveness check failed: Specular glare detected (Glare Ratio {glare_ratio:.3f} > {max_glare}). Possible screen reflection.")
        
    return True

def check_active_liveness(
    pose: np.ndarray,
    required_gesture: str
) -> bool:
    """
    Checks if the detected face pose matches the required active liveness gesture.
    pose: [pitch, yaw, roll] in degrees
    """
    if required_gesture == "NONE" or not required_gesture:
        return True

    if pose is None or len(pose) < 3:
        raise ValueError("Biometric liveness check failed: Could not estimate face pose for active liveness verification.")
        
    pitch, yaw, roll = pose
    
    print(f"[ACTIVE LIVENESS DEBUG] Pose: pitch={pitch:.2f}, yaw={yaw:.2f}, roll={roll:.2f} | Required: {required_gesture}")
          
    if required_gesture == "NORMAL":
        # Face should look straight: yaw, pitch, roll all close to 0.
        # Enforce a relaxed threshold for real-world laptop webcam angles (which look up at the face)
        if abs(yaw) > 15 or abs(pitch) > 18 or abs(roll) > 15:
            raise ValueError(f"Biometric liveness check failed: Please look straight at the camera. (Yaw: {yaw:.1f}, Pitch: {pitch:.1f}, Roll: {roll:.1f})")
    elif required_gesture == "LOOK_LEFT":
        # User looks left: their head turns left, yaw should be negative (typically yaw < -12)
        if yaw >= -12:
            raise ValueError(f"Biometric liveness check failed: Please turn your head to the LEFT (Yaw: {yaw:.1f} >= -12).")
    elif required_gesture == "LOOK_RIGHT":
        # User looks right: their head turns right, yaw should be positive (typically yaw > 12)
        if yaw <= 12:
            raise ValueError(f"Biometric liveness check failed: Please turn your head to the RIGHT (Yaw: {yaw:.1f} <= 12).")
    elif required_gesture == "LOOK_UP":
        # User looks up: pitch should be positive (typically pitch > 12)
        if pitch <= 12:
            raise ValueError(f"Biometric liveness check failed: Please look UP (Pitch: {pitch:.1f} <= 12).")
    elif required_gesture == "LOOK_DOWN":
        # User looks down: pitch should be negative (typically pitch < -12)
        if pitch >= -12:
            raise ValueError(f"Biometric liveness check failed: Please look DOWN (Pitch: {pitch:.1f} >= -12).")
    elif required_gesture == "TILT_LEFT":
        # User tilts head left: roll should be negative (typically roll < -10)
        if roll >= -10:
            raise ValueError(f"Biometric liveness check failed: Please tilt your head to the LEFT (Roll: {roll:.1f} >= -10).")
    elif required_gesture == "TILT_RIGHT":
        # User tilts head right: roll should be positive (typically roll > 10)
        if roll <= 10:
            raise ValueError(f"Biometric liveness check failed: Please tilt your head to the RIGHT (Roll: {roll:.1f} <= 10).")
            
    return True

def extract_face_embedding(
    image_bytes: bytes,
    liveness_enabled: bool = True,
    required_gesture: str = "NONE",
    min_laplacian: float = 30.0,
    min_fft: float = 0.05,
    max_fft: float = 0.65,
    max_glare: float = 0.15
) -> np.ndarray:
    """
    Decodes an image from raw bytes, runs face detection, 
    applies optional passive and active liveness checks, and returns the embedding.
    """
    # Convert image bytes to numpy array and decode
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Invalid image file format. Could not decode image.")
    
    # Analyze the image for faces
    faces = faceapp.get(img)
    
    if not faces:
        raise ValueError("No face detected in the image. Please ensure your face is clearly visible.")
        
    if len(faces) > 1:
        raise ValueError("Multiple faces detected. Please make sure only one person is in the frame.")
        
    # Perform liveness check if enabled
    if liveness_enabled:
        # 1. Passive Liveness Check (Laplacian, FFT, Glare)
        check_passive_liveness(
            img, 
            faces[0].bbox, 
            min_laplacian=min_laplacian, 
            min_fft=min_fft, 
            max_fft=max_fft, 
            max_glare=max_glare
        )
        
        # 2. Active Liveness Check (Pose)
        pose = None
        if hasattr(faces[0], 'pose'):
            pose = faces[0].pose
        elif isinstance(faces[0], dict) and 'pose' in faces[0]:
            pose = faces[0]['pose']
            
        check_active_liveness(pose, required_gesture)
    
    # Return the embedding vector
    return faces[0].embedding

