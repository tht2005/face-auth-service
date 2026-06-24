FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install python packages. We force uninstall opencv-python if pulled in by insightface
# and replace it with opencv-python-headless to avoid GUI library dependencies.
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    insightface \
    hvac \
    numpy \
    python-multipart \
    pyjwt \
    cryptography \
    python-dotenv \
    onnxruntime && \
    pip uninstall -y opencv-python opencv-python-headless && \
    pip install --no-cache-dir opencv-python-headless

# Pre-download the InsightFace buffalo_l model to cache it inside the image
RUN python -c "import insightface; app = insightface.app.FaceAnalysis(name='buffalo_l'); app.prepare(ctx_id=-1)"

# Copy application files (frontend will be served as static files)
COPY backend /app/backend
COPY frontend/static /app/frontend/static

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
