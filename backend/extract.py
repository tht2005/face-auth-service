import cv2
import numpy as np
import insightface
import os

# Initialize InsightFace (default to CPU ctx_id=-1, customizable via env)
ctx_id = int(os.getenv("INSIGHTFACE_CTX_ID", "-1"))
faceapp = insightface.app.FaceAnalysis(name='buffalo_l')
faceapp.prepare(ctx_id=ctx_id, det_size=(640, 640))

def extract_face_embedding(image_bytes: bytes) -> np.ndarray:
    """
    Decodes an image from raw bytes, runs InsightFace detection, 
    and returns the 512-dimensional face embedding of the first detected face.
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
        
    # Return the embedding vector
    return faces[0].embedding
