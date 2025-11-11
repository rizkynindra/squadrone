# python
import base64
import io
import logging
import os
import random
import csv
import time
import threading
from datetime import datetime
from typing import List, Union
from flask_cors import CORS

import cv2
import numpy as np
import requests
import torch
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image
from ultralytics import RTDETR, YOLO

# -------------------------
# Configuration / Env vars
# -------------------------
WAHA_TOKEN = os.getenv('WAHA_TOKEN')
WAHA_SESSION = os.getenv('WAHA_SESSION')
WAHA_API_URL = os.getenv('WAHA_API_URL')

# Comma-separated notify numbers (e.g. "628123...,628987...")
NOTIFY_NUMBERS = os.getenv('NOTIFY_NUMBERS', '6285121013271').split(',')

# Bulk sending defaults
DEFAULT_DELAY_MIN = int(os.getenv('WAHA_DELAY_MIN', '5'))
DEFAULT_DELAY_MAX = int(os.getenv('WAHA_DELAY_MAX', '15'))
DEFAULT_MAX_RETRIES = int(os.getenv('WAHA_MAX_RETRIES', '3'))

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    filename='manusia_detection.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

waha_logger = logging.getLogger('waha_send')
waha_logger.setLevel(logging.INFO)
waha_handler = logging.FileHandler('waha_send.log')
waha_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
waha_logger.addHandler(waha_handler)

# -------------------------
# Flask app
# -------------------------
app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # Limit uploads to 5MB

@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory('audio', filename)

# -------------------------
# Model load
# -------------------------
print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
print(f"CUDA device count: {torch.cuda.device_count()}")
if torch.cuda.is_available():
    try:
        print(f"CUDA device name: {torch.cuda.get_device_name(0)}")
    except Exception:
        pass

# Load RT-DETR model
model = RTDETR('model/best_rtdetr.pt')

# Use GPU if available (some ultralytics models expose .to/.device)
device = 'cuda' if torch.cuda.is_available() else 'cpu'
try:
    model.to(device)
except Exception:
    # some ultralytics wrappers manage device internally; ignore if not supported
    pass

try:
    print(f"model loaded on device: {model.device}")
except Exception:
    print("model loaded (device unknown)")

# Model configuration
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.35'))
IMAGE_SIZE = int(os.getenv('IMAGE_SIZE', '320'))

# Human detection tracking
human_detection_state = {
    'first_detected_at': None,
    'is_alarm_active': False,
    'last_detection_time': 0,
    'detection_threshold': float(os.getenv('DETECTION_THRESHOLD', '1.0'))  # seconds required to trigger alarm
}

# Shared buffers for latest frame / results (single-slot queue behavior)
_shared_lock = threading.Lock()
_shared_state = {
    'pending_frame': None,        # numpy BGR image waiting to be processed
    'pending_ts': 0.0,            # timestamp when frame was received
    'frame_id': 0,                # increasing id for frames
    'latest_result': None         # dict with last processed detections + metadata
}

# -------------------------
# WAHA helper functions
# -------------------------
def send_whatsapp_message(phone_number: str, message: str, session: str = WAHA_SESSION, token: str = WAHA_TOKEN, timeout: int = 30) -> dict:
    """
    Send a single WhatsApp text via WAHA endpoint to phone_number (string, e.g. '628123...').
    Returns a dict: {'ok': True, 'response': ...} or {'ok': False, 'error': ...}
    """
    chat_id = f"{phone_number}@c.us"
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": token
    }
    payload = {
        "session": session,
        "chatId": chat_id,
        "text": message
    }
    try:
        resp = requests.post(WAHA_API_URL, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        try:
            body = resp.json()
        except Exception:
            body = {'raw_text': resp.text}
        waha_logger.info("SENT to %s: %s", phone_number, str(body))
        return {"ok": True, "response": body}
    except requests.RequestException as e:
        waha_logger.error("FAILED to %s: %s", phone_number, str(e))
        return {"ok": False, "error": str(e)}
    except Exception as e:
        waha_logger.error("FAILED to %s (unexpected): %s", phone_number, str(e))
        return {"ok": False, "error": str(e)}

def _send_single_with_retry(phone_number: str, message: str, max_retries: int = DEFAULT_MAX_RETRIES, retry_delay_base: float = 1.0):
    attempt = 0
    backoff = retry_delay_base
    while attempt <= max_retries:
        result = send_whatsapp_message(phone_number, message)
        if result.get("ok"):
            return {"phone": phone_number, **result, "attempts": attempt + 1}
        attempt += 1
        if attempt > max_retries:
            return {"phone": phone_number, **result, "attempts": attempt}
        # exponential backoff with jitter
        sleep_for = backoff + random.uniform(0, 1.0)
        time.sleep(sleep_for)
        backoff *= 2

def send_whatsapp_bulk(phone_numbers: NOTIFY_NUMBERS, message: str, delay_min: int = DEFAULT_DELAY_MIN, delay_max: int = DEFAULT_DELAY_MAX, max_retries: int = DEFAULT_MAX_RETRIES, template: bool = False) -> List[dict]:
    """
    Send message to many numbers.
    - phone_numbers: list of strings OR path to CSV file (first column contains phone numbers)
    - template=True: message can contain {phone} placeholder
    Returns list of results per phone.
    """
    numbers = []
    if isinstance(phone_numbers, str):
        # assume it's path to CSV
        try:
            with open(phone_numbers, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    num = row[0].strip()
                    if not num:
                        continue
                    # skip header if it contains non-digits letters
                    if any(c.isalpha() for c in num) and num.lower().startswith("phone"):
                        continue
                    numbers.append(num)
        except FileNotFoundError:
            raise ValueError(f"CSV file not found: {phone_numbers}")
    else:
        numbers = [p.strip() for p in phone_numbers if p and p.strip()]

    results = []
    total = len(numbers)
    for idx, num in enumerate(numbers, start=1):
        text_to_send = message.format(phone=num) if template else message
        waha_logger.info("Attempting to send [%d/%d] to %s", idx, total, num)
        res = _send_single_with_retry(num, text_to_send, max_retries=max_retries)
        results.append(res)
        if idx != total:
            delay = random.uniform(delay_min, delay_max)
            waha_logger.info("Waiting %.1f seconds before next send", delay)
            time.sleep(delay)
    return results

# -------------------------
# Detection endpoints
# -------------------------
@app.route('/')
def index():
    return render_template('screen_share.html')

@app.route('/detect', methods=['POST'])
def detect():
    start_time = time.time()
    try:
        # Prefer binary multipart uploads from client
        if 'image' in request.files:
            file = request.files['image']
            image_bytes = file.read()
            arr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            data = request.form.to_dict() or request.json or {}
            image_data = data.get('image', '') or data.get('image_base64', '')
            if not image_data:
                return jsonify(success=False, error='No image provided'), 400
            if 'data:image' in image_data:
                image_data = image_data.split(',', 1)[1]
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        if frame is None:
            return jsonify(success=False, error='Unable to decode image'), 400

        # Inference with timing and recommended context managers
        infer_start = time.time()
        with torch.inference_mode():
            if torch.cuda.is_available():
                try:
                    with torch.amp.autocast('cuda'):
                        results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, imgsz=IMAGE_SIZE, verbose=False, iou=0.5)
                except Exception:
                    # fallback if autocast or predict signature differs
                    results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, imgsz=IMAGE_SIZE, verbose=False, iou=0.5)
            else:
                results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, imgsz=IMAGE_SIZE, verbose=False, iou=0.5)
        infer_end = time.time()
        inference_time_ms = int((infer_end - infer_start) * 1000)

        # Convert results to JSON-friendly detection list
        detections = []
        human_detected = False
        for r in results:
            # ultralytics result rows may contain .boxes
            boxes = getattr(r, 'boxes', None)
            if boxes is None:
                continue
            # boxes may be a list-like object
            for box in boxes:
                # Attempt to fetch coordinates, confidence, class
                try:
                    # xyxy can be tensor or array-like
                    if hasattr(box, 'xyxy'):
                        xyxy_val = box.xyxy[0] if hasattr(box.xyxy, '__len__') else box.xyxy
                        xyxy = xyxy_val.cpu().numpy() if hasattr(xyxy_val, 'cpu') else np.array(xyxy_val)
                    else:
                        xyxy = np.array([0,0,0,0])
                    x1, y1, x2, y2 = [int(float(v)) for v in xyxy[:4]]
                except Exception:
                    x1, y1, x2, y2 = 0, 0, 0, 0

                try:
                    conf = float(box.conf[0]) if hasattr(box, 'conf') else float(getattr(box, 'confidence', 1.0))
                except Exception:
                    conf = 1.0

                try:
                    cls = int(box.cls[0]) if hasattr(box, 'cls') else int(getattr(box, 'class', 0))
                except Exception:
                    cls = 0

                class_name = model.names[cls] if hasattr(model, 'names') and cls in model.names else str(cls)
                detections.append({'box': [x1, y1, x2, y2], 'class': class_name, 'confidence': conf})

                # decide what class name indicates human (depends on your model training label)
                # common: class_name == 'person' or 'man' or 'human' — adjust as necessary
                if class_name.lower() in ('person', 'people', 'human', 'man', 'woman'):
                    human_detected = True

        total_time_ms = int((time.time() - start_time) * 1000)
        # update shared state
        with _shared_lock:
            _shared_state['latest_result'] = {
                'detections': detections,
                'inference_time_ms': inference_time_ms,
                'total_time_ms': total_time_ms,
                'timestamp': time.time()
            }

        # human detection tracking
        current_time = time.time()
        alarm_info = check_human_detection(human_detected, current_time)
        if alarm_info.get('active'):
            logging.info("Alarm triggered; human detected continuously for %s seconds", alarm_info.get('duration'))
            # Optionally auto-send notification when alarm triggers:
            # compose message and send to NOTIFY_NUMBERS asynchronously to avoid blocking
            threading.Thread(target=send_whatsapp_bulk, args=(NOTIFY_NUMBERS, f"Alarm! Manusia terdeteksi pada {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (durasi {alarm_info.get('duration'):.1f}s).", DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX, DEFAULT_MAX_RETRIES, False), daemon=True).start()

        return jsonify(success=True, detections=detections, inference_time_ms=inference_time_ms, total_time_ms=total_time_ms, alarm=alarm_info), 200

    except Exception as e:
        logging.exception('Detection error')
        return jsonify(success=False, error=str(e)), 500

# -------------------------
# Human detection helpers
# -------------------------
def check_human_detection(human_detected: bool, current_time: float):
    """Track human detection and determine if alarm should be triggered"""
    global human_detection_state

    if human_detected:
        # If this is the first human detection or there was a gap in detection
        if human_detection_state['first_detected_at'] is None:
            human_detection_state['first_detected_at'] = current_time
            human_detection_state['is_alarm_active'] = False
            return {'active': False, 'progress': 0.0}

        # Check if human has been detected for the threshold duration
        elapsed_time = current_time - human_detection_state['first_detected_at']
        if elapsed_time >= human_detection_state['detection_threshold']:
            # Trigger the alarm if not already triggered
            if not human_detection_state['is_alarm_active']:
                human_detection_state['is_alarm_active'] = True
            return {'active': True, 'duration': elapsed_time}

        # Human detected but threshold not reached
        return {'active': False, 'progress': elapsed_time / human_detection_state['detection_threshold']}
    else:
        # No human detected, reset the tracking
        reset_human_detection()
        return {'active': False}

def reset_human_detection():
    """Reset human detection tracking"""
    global human_detection_state
    human_detection_state['first_detected_at'] = None
    human_detection_state['is_alarm_active'] = False

@app.route('/reset_alarm', methods=['POST'])
def reset_alarm():
    """Endpoint to manually reset the alarm"""
    reset_human_detection()
    return jsonify({'success': True})

@app.route('/panic', methods=['POST'])
def panic():
    """
    Panic endpoint: trigger immediate notification to NOTIFY_NUMBERS.
    You can POST JSON: {"message": "...", "numbers": ["628...","628..."]} to override defaults.
    """
    try:
        payload = request.json or {}
        message = payload.get('message') or f"Manusia detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}!"
        numbers = payload.get('numbers') or NOTIFY_NUMBERS

        # send async so we don't block response
        threading.Thread(target=send_whatsapp_bulk, args=(numbers, message, DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX, DEFAULT_MAX_RETRIES, False), daemon=True).start()
        return jsonify({'success': True, 'message': 'Notification enqueued'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Optional route to check last detection result
@app.route('/last_result', methods=['GET'])
def last_result():
    with _shared_lock:
        return jsonify(_shared_state.get('latest_result') or {})

# -------------------------
# Run server
# -------------------------
if __name__ == '__main__':
    # Use threaded mode for better performance
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', '5000')), threaded=True)
