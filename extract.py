import cv2
import numpy as np
import insightface
import time
import threading
from queue import Queue

faceapp = insightface.app.FaceAnalysis(name='buffalo_l')
faceapp.prepare(ctx_id=0, det_size=(640,640))

def ai_worker(input_queue, output_queue, stop_event):
    while not stop_event.is_set():
        if not input_queue.empty():
            frame = input_queue.get()
            faces = faceapp.get(frame)
            output_queue.put(faces)
        else:
            time.sleep(0.01)

def retrieve_face_emb_from_webcam(st_frame=None):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise ConnectionError("Can not connect to camera device")

    input_queue = Queue(maxsize=1)
    output_queue = Queue(maxsize=1)
    stop_event = threading.Event()

    ai_thread = threading.Thread(target=ai_worker, args=(input_queue,output_queue,stop_event))
    ai_thread.start()

    start_time = time.time()
    initial_delay = 1.5
    scan_cooldown = 2

    face_detected_start_time = None
    latest_faces = None
    final_embedding = None
    final_captured_frame = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError("Lose the data stream from camera device")

        frame = cv2.flip(frame, 1)
        display_frame = frame.copy()
        current_time = time.time()
        elapsed_duration = current_time - start_time

        if elapsed_duration > initial_delay and input_queue.empty():
            input_queue.put(frame)

        if not output_queue.empty():
            latest_faces = output_queue.get()

        if latest_faces and len(latest_faces) > 0:
            face = latest_faces[0]
            bbox = face.bbox.astype(int)

            cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)

            if face_detected_start_time is None:
                face_detected_start_time = current_time
            
            lock_duration = current_time - face_detected_start_time
            
            if lock_duration < scan_cooldown:
                progress = int((lock_duration / scan_cooldown) * 100)
                cv2.putText(display_frame, f"Scanning... {progress}%", (bbox[0], bbox[1] - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            else:
                cv2.putText(display_frame, "SUCCESS!", (bbox[0], bbox[1] - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                final_embedding = face.embedding
                final_captured_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                break
        else:
            face_detected_start_time = None
            if elapsed_duration < initial_delay:
                cv2.putText(display_frame, "Initializing...", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            else:
                cv2.putText(display_frame, "Please look at the camera", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if st_frame is not None:
            display_small = cv2.resize(display_frame, (640, 480))
            rgb_live = cv2.cvtColor(display_small, cv2.COLOR_BGR2RGB)
            st_frame.image(rgb_live, channels="RGB")

            if face_detected_start_time is not None:
                time.sleep(0.04)
            else:
                time.sleep(0.01)

    stop_event.set()
    ai_thread.join(timeout=5)
    cap.release()

    if final_embedding is None:
        raise ValueError("Final Embedding is None after the loop!")

    return final_embedding, final_captured_frame

