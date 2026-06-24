from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
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

app = FastAPI(title="Face Verification API Service")

@app.on_event("startup")
def startup_event():
    from backend.auth import init_db
    init_db()
    logger.info("SQLite database tables initialized successfully.")

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

@app.get("/api/auth/challenge")
async def get_challenge(username: str):
    if not username:
        raise HTTPException(status_code=400, detail="Username query parameter is required.")
    challenge_token = create_challenge_token(username)
    return {"status": "success", "challenge_token": challenge_token}

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
        # Verify the signed challenge token first to prevent replay attacks
        try:
            verify_challenge_token(challenge_token, username)
        except ValueError as e:
            logger.warning(f"Challenge verification failed for {username}: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        # Read upload image bytes
        image_bytes = await file.read()
        
        # Extract live face embedding with dynamic liveness checks
        live_emb = extract_face_embedding(
            image_bytes,
            liveness_enabled=liveness_enabled,
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
        
    token = authorization.split(" ")[1]
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
