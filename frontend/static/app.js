let currentTab = 'register';
let activeStream = null;
let capturedBlob = null;

function switchTab(tab) {
    if (tab === currentTab) return;
    
    // Stop any active camera streams
    stopCamera();
    
    // Reset state
    capturedBlob = null;
    hideMessage();
    
    // Toggle active tab buttons
    document.getElementById(`tab-register-btn`).classList.toggle('active', tab === 'register');
    document.getElementById(`tab-login-btn`).classList.toggle('active', tab === 'login');
    
    // Toggle active tab contents
    document.getElementById(`register-content`).classList.toggle('active', tab === 'register');
    document.getElementById(`login-content`).classList.toggle('active', tab === 'login');
    
    // Hide preview containers
    document.getElementById('reg-preview-container').style.display = 'none';
    document.getElementById('login-preview-container').style.display = 'none';
    
    // Disable submit/capture buttons initially
    document.getElementById('register-submit-btn').disabled = true;
    document.getElementById('reg-capture-btn').disabled = true;
    document.getElementById('login-capture-btn').disabled = true;
    
    // Reset start button text
    document.getElementById('reg-start-btn').textContent = "Turn On Camera";
    document.getElementById('login-start-btn').textContent = "Turn On Camera";
    
    document.getElementById('reg-camera-status').textContent = "Camera Off";
    document.getElementById('login-camera-status').textContent = "Camera Off";

    currentTab = tab;
}

async function toggleCamera(mode) {
    const video = document.getElementById(`${mode}-video`);
    const statusText = document.getElementById(`${mode}-camera-status`);
    const startBtn = document.getElementById(`${mode}-start-btn`);
    const captureBtn = document.getElementById(`${mode}-capture-btn`);
    
    if (activeStream) {
        // Turn off camera
        stopCamera();
        startBtn.textContent = "Turn On Camera";
        statusText.textContent = "Camera Off";
        statusText.style.display = 'block';
        captureBtn.disabled = true;
    } else {
        // Check for secure context and mediaDevices support
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            const errorMsg = "Webcam access is blocked. Browsers only allow camera access under secure contexts (HTTPS or http://localhost). If you accessed this via an IP address, please use http://localhost:8000 instead.";
            console.error(errorMsg);
            statusText.textContent = "Security Blocked";
            showMessage(errorMsg, "error");
            return;
        }

        // Turn on camera
        statusText.textContent = "Connecting to camera...";
        statusText.style.display = 'block';
        hideMessage();
        
        try {
            activeStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: "user" }
            });
            video.srcObject = activeStream;
            startBtn.textContent = "Turn Off Camera";
            statusText.style.display = 'none';
            captureBtn.disabled = false;
        } catch (err) {
            console.error("Camera access error:", err);
            statusText.textContent = "Camera access denied";
            showMessage(`Could not access camera: ${err.message || err}. Please check permissions.`, "error");
        }
    }
}

function stopCamera() {
    if (activeStream) {
        activeStream.getTracks().forEach(track => track.stop());
        activeStream = null;
    }
    const regVideo = document.getElementById('reg-video');
    const loginVideo = document.getElementById('login-video');
    if (regVideo) regVideo.srcObject = null;
    if (loginVideo) loginVideo.srcObject = null;
}

function captureSnapshot(mode) {
    if (!activeStream) return;
    
    const video = document.getElementById(`${mode}-video`);
    const canvas = document.getElementById(`${mode}-canvas`);
    const previewContainer = document.getElementById(`${mode}-preview-container`);
    const previewImg = document.getElementById(`${mode}-preview-img`);
    const laserOverlay = document.getElementById(`${mode}-scanner-overlay`);
    
    // Configure canvas dimensions
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    
    // Draw current frame to canvas
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Show laser animation temporarily to simulate scan
    laserOverlay.style.display = 'block';
    
    // Convert canvas to blob
    canvas.toBlob((blob) => {
        capturedBlob = blob;
        const imageUrl = URL.createObjectURL(blob);
        previewImg.src = imageUrl;
        
        setTimeout(() => {
            laserOverlay.style.display = 'none';
            previewContainer.style.display = 'block';
            
            // Auto stop camera after successful capture
            toggleCamera(mode);
            
            if (mode === 'reg') {
                document.getElementById('register-submit-btn').disabled = false;
            } else if (mode === 'login') {
                // Auto trigger login verification on scan completion
                submitLogin();
            }
        }, 1200); // 1.2s scan animation
    }, 'image/jpeg', 0.95);
}

async function handleRegister(event) {
    event.preventDefault();
    if (!capturedBlob) {
        showMessage("Please scan your face first.", "error");
        return;
    }
    
    const username = document.getElementById('reg-username').value.trim();
    const fullname = document.getElementById('reg-fullname').value.trim();
    const submitBtn = document.getElementById('register-submit-btn');
    
    submitBtn.disabled = true;
    submitBtn.textContent = "Registering...";
    showMessage("Saving credentials securely...", "info");
    
    const formData = new FormData();
    formData.append('username', username);
    formData.append('full_name', fullname);
    formData.append('file', capturedBlob, 'face.jpg');
    
    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage(`Success! Account "${username}" has been registered successfully.`, "success");
            // Reset form
            document.getElementById('register-form').reset();
            document.getElementById('reg-preview-container').style.display = 'none';
            capturedBlob = null;
        } else {
            showMessage(data.detail || "Registration failed. Please try again.", "error");
        }
    } catch (err) {
        console.error(err);
        showMessage("Connection error. Could not reach server.", "error");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Register Account";
    }
}

async function submitLogin() {
    const username = document.getElementById('login-username').value.trim();
    if (!username) {
        showMessage("Please fill in the username first.", "error");
        return;
    }
    
    if (!capturedBlob) {
        showMessage("Biometric scan incomplete. Try again.", "error");
        return;
    }
    
    showMessage("Performing biometric match...", "info");
    
    const formData = new FormData();
    formData.append('username', username);
    formData.append('file', capturedBlob, 'face.jpg');
    
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            hideMessage();
            showSuccessState(data.full_name, data.token);
        } else {
            showMessage(data.detail || "Login failed. Face did not match.", "error");
        }
    } catch (err) {
        console.error(err);
        showMessage("Connection error. Verification service unreachable.", "error");
    }
}

function showSuccessState(name, token) {
    document.getElementById('auth-flow-container').style.display = 'none';
    document.getElementById('success-card').style.display = 'block';
    document.getElementById('success-user').textContent = name;
    document.getElementById('jwt-token-display').value = token;
}

function resetAuthSession() {
    document.getElementById('success-card').style.display = 'none';
    document.getElementById('auth-flow-container').style.display = 'block';
    
    // Clear forms
    document.getElementById('login-form').reset();
    document.getElementById('login-preview-container').style.display = 'none';
    capturedBlob = null;
    hideMessage();
}

function showMessage(text, type) {
    const box = document.getElementById('message-box');
    const msgText = document.getElementById('message-text');
    const msgIcon = document.getElementById('message-icon');
    
    box.className = `message-box ${type}`;
    msgText.textContent = text;
    
    if (type === 'info') msgIcon.textContent = '🔄';
    else if (type === 'success') msgIcon.textContent = '🟢';
    else if (type === 'error') msgIcon.textContent = '❌';
    
    box.style.display = 'flex';
}

function hideMessage() {
    document.getElementById('message-box').style.display = 'none';
}
