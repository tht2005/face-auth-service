from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
from backend.extract import extract_face_embedding
from backend.auth import register, validation, create_jwt_token, decode_jwt_token

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("face-auth-api")

app = FastAPI(title="Face Verification API Service")

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
    file: UploadFile = File(...)
):
    try:
        # Read upload image bytes
        image_bytes = await file.read()
        
        # Extract face embedding (checks for single face & validity)
        emb = extract_face_embedding(image_bytes)
        
        # Register user (encrypts embedding and saves to DB)
        register(username, full_name, emb)
        
        logger.info(f"Registered user: {username}")
        return {"status": "success", "message": f"User '{username}' registered successfully."}
        
    except ValueError as e:
        logger.warning(f"Registration validation failed for {username}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error during registration of {username}: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/login")
async def api_login(
    username: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        # Read upload image bytes
        image_bytes = await file.read()
        
        # Extract live face embedding
        live_emb = extract_face_embedding(image_bytes)
        
        # Match embedding with DB (decrypts DB embedding using Vault)
        is_match, full_name, sim = validation(username, live_emb)
        
        if is_match:
            # Issue session JWT
            token = create_jwt_token(username, full_name)
            logger.info(f"User '{username}' logged in successfully.")
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
