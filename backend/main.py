from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
from contextlib import asynccontextmanager
from backend.extract import extract_face_embedding
from backend.auth import (
    register, 
    validation, 
    create_jwt_token, 
    decode_jwt_token,
    create_challenge_token,
    verify_challenge_token
)

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("face-auth-api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite database tables
    from backend.auth import init_db
    init_db()
    logger.info("SQLite database tables initialized successfully.")
    yield

app = FastAPI(title="Face Verification API Service", lifespan=lifespan)

# Configure CORS for ease of access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/register")
async def api_register(
    username: str = Form(...),
    full_name: str = Form(...),
    file: UploadFile = File(...),
    liveness_enabled: bool = Form(True),
    min_laplacian: float = Form(30.0),
    min_fft: float = Form(0.05),
    max_fft: float = Form(0.65),
    max_glare: float = Form(0.15)
):
    try:
        # Read upload image bytes
        image_bytes = await file.read()
        
        # Extract face embedding with dynamically configured liveness checks
        emb = extract_face_embedding(
            image_bytes,
            liveness_enabled=liveness_enabled,
            min_laplacian=min_laplacian,
            min_fft=min_fft,
            max_fft=max_fft,
            max_glare=max_glare
        )
        
        # Register user (encrypts embedding and saves to DB)
        register(username, full_name, emb)
        
        logger.info(f"Registered user: {username} (liveness_check={liveness_enabled})")
        return {"status": "success", "message": f"User '{username}' registered successfully."}
        
    except ValueError as e:
        logger.warning(f"Registration validation failed for {username}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error during registration of {username}: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.get("/api/certs")
async def get_certs():
    """
    Exposes the public key in PEM format so that other services can verify user session JWTs.
    """
    from backend.auth import PUBLIC_KEY
    return {"status": "success", "public_key": PUBLIC_KEY.decode("utf-8")}

@app.get("/api/auth/challenge")
async def get_challenge(username: str):
    if not username:
        raise HTTPException(status_code=400, detail="Username query parameter is required.")
    
    import random
    gestures = ["LOOK_LEFT", "LOOK_RIGHT", "LOOK_UP", "LOOK_DOWN", "NORMAL"]
    selected_gesture = random.choice(gestures)
    
    challenge_token = create_challenge_token(username, gesture=selected_gesture)
    return {
        "status": "success", 
        "challenge_token": challenge_token,
        "gesture": selected_gesture
    }

@app.post("/api/login")
async def api_login(
    username: str = Form(...),
    file: UploadFile = File(...),
    challenge_token: str = Form(...),
    liveness_enabled: bool = Form(True),
    min_laplacian: float = Form(30.0),
    min_fft: float = Form(0.05),
    max_fft: float = Form(0.65),
    max_glare: float = Form(0.15)
):
    try:
        # Check if user exists and is active before doing expensive face analysis
        from backend.auth import check_user_status
        check_user_status(username)

        # Verify the signed challenge token first to prevent replay attacks
        try:
            challenge_payload = verify_challenge_token(challenge_token, username)
        except ValueError as e:
            logger.warning(f"Challenge verification failed for {username}: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        required_gesture = challenge_payload.get("gesture", "NORMAL")

        # Read upload image bytes
        image_bytes = await file.read()
        
        # Extract live face embedding with dynamic liveness checks (passive + active)
        live_emb = extract_face_embedding(
            image_bytes,
            liveness_enabled=liveness_enabled,
            required_gesture=required_gesture,
            min_laplacian=min_laplacian,
            min_fft=min_fft,
            max_fft=max_fft,
            max_glare=max_glare
        )
        
        # Match embedding with DB (decrypts DB embedding using Vault)
        is_match, full_name, sim = validation(username, live_emb)
        
        if is_match:
            # Issue session JWT
            token = create_jwt_token(username, full_name)
            logger.info(f"User '{username}' logged in successfully. (liveness_check={liveness_enabled})")
            return {
                "status": "success",
                "token": token,
                "username": username,
                "full_name": full_name,
                "similarity": sim
            }
        else:
            logger.warning(f"Login attempt failed for '{username}': Face did not match.")
            raise HTTPException(status_code=401, detail="Authentication failed: Face does not match.")
            
    except HTTPException as e:
        raise e
    except ValueError as e:
        logger.warning(f"Login validation failed for {username}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except NameError as e:
        logger.warning(f"User not found during login: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Locked account login attempt: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Internal login error for {username}: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/api/verify")
async def api_verify(authorization: str = Header(None)):
    """
    Checks if a JWT token is valid and active.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
        
    parts = authorization.split(" ")
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="Invalid Authorization header format. Expected 'Bearer <token>'.")
    token = parts[1]
    try:
        payload = decode_jwt_token(token)
        return {
            "status": "success",
            "username": payload.get("sub"),
            "full_name": payload.get("name"),
            "expires_at": payload.get("exp")
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")

# Mount static frontend files LAST so standard routing takes precedence
app.mount("/", StaticFiles(directory="frontend/static", html=True), name="static")
