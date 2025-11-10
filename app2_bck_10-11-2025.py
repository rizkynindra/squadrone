# python
import base64
import io
import logging
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np
import requests
import torch
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image
from ultralytics import RTDETR, YOLO

WAHA_TOKEN = os.getenv('WAHA_TOKEN')
WAHA_SESSION = os.getenv('WAHA_SESSION')

# Configure logging for manusia detection
logging.basicConfig(
    filename='manusia_detection.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# response = requests.post(url, json=data, headers=headers)
# print(response.json())



def send_whatsapp_message(phone_number, message):
    url = "https://waha-mq4x4bgkgjsm.anakit.sumopod.my.id/api/sendText"  # Adjust to your WAHA API endpoint
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": f"{WAHA_TOKEN}"
    }
    data = {
        "session": f"{WAHA_SESSION}",
        "chatId": "6285936108008@c.us",
        "text": message
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to send WhatsApp message: {e}")
        return None

print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
print(f"CUDA device count: {torch.cuda.device_count()}")
if torch.cuda.is_available():
    print(f"CUDA device name: {torch.cuda.get_device_name(0)}")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # Limit uploads to 5MB

@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory('audio', filename)

# Load YOLO model
# model = YOLO('model/best_26102025.pt')

# Load RT-DETR model
model = RTDETR('model/best_rtdetr.pt')

#use GPU
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model.to(device)
model.eval()
print(f"model loaded on device: {model.device}")

# Model configuration
CONFIDENCE_THRESHOLD = 0.35 # Lower confidence threshold for better detection
IMAGE_SIZE = 320  # Smaller inference size can improve performance

# Human detection tracking
human_detection_state = {
    'first_detected_at': None,
    'is_alarm_active': False,
    'last_detection_time': 0,
    'detection_threshold': 0.05  # 1 seconds
}

# Shared buffers for latest frame / results (single-slot queue behavior)
_shared_lock = threading.Lock()
_shared_state = {
    'pending_frame': None,        # numpy BGR image waiting to be processed
    'pending_ts': 0.0,            # timestamp when frame was received
    'frame_id': 0,                # increasing id for frames
    'latest_result': None         # dict with last processed detections + metadata
}

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
            # fallback to base64 JSON-based upload if present
            data = request.form.to_dict() or request.json or {}
            image_data = data.get('image', '')
            if 'data:image' in image_data:
                image_data = image_data.split(',', 1)[1]
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        if frame is None:
            return jsonify(success=False, error='Unable to decode image'), 400

        # Inference with timing and recommended context managers
        infer_start = time.time()
        with torch.inference_mode():
            if torch.cuda.is_available():
                with torch.amp.autocast('cuda'):
                    results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, imgsz=IMAGE_SIZE, verbose=False, iou=0.5)
            else:
                results = model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, imgsz=IMAGE_SIZE, verbose=False, iou=0.5)
        infer_end = time.time()
        inference_time_ms = int((infer_end - infer_start) * 1000)

        # Convert results to JSON-friendly detection list
        detections = []
        for r in results:
            # adapt depending on your model output (ultralytics/RTDETR)
            if hasattr(r, 'boxes') and r.boxes is not None:
                for box in r.boxes:
                    # box.xyxy might be tensor-like or list
                    try:
                        xyxy = box.xyxy[0].cpu().numpy() if hasattr(box.xyxy, 'cpu') else np.array(box.xyxy)
                    except Exception:
                        # fallback if structure different
                        vals = box.xyxy if hasattr(box, 'xyxy') else getattr(box, 'xyxy', None)
                        xyxy = np.array(vals) if vals is not None else np.array([0,0,0,0])
                    x1, y1, x2, y2 = [int(v) for v in xyxy]
                    conf = float(box.conf[0]) if hasattr(box, 'conf') else (float(getattr(box, 'confidence', 1.0)) if hasattr(box, 'confidence') else 1.0)
                    cls = int(box.cls[0]) if hasattr(box, 'cls') else (int(getattr(box, 'class', 0)) if hasattr(box, 'class') else 0)
                    class_name = model.names[cls] if hasattr(model, 'names') and cls in model.names else str(cls)
                    detections.append({'box': [x1, y1, x2, y2], 'class': class_name, 'confidence': conf})

        total_time_ms = int((time.time() - start_time) * 1000)
        return jsonify(success=True, detections=detections, inference_time_ms=inference_time_ms, total_time_ms=total_time_ms, alarm={}), 200

    except Exception as e:
        logging.exception('Detection error')
        return jsonify(success=False, error=str(e)), 500

def check_human_detection(human_detected, current_time):
    """Track human detection and determine if alarm should be triggered"""
    global human_detection_state

    if human_detected:
        # If this is the first human detection or there was a gap in detection
        if human_detection_state['first_detected_at'] is None:
            human_detection_state['first_detected_at'] = current_time
            human_detection_state['is_alarm_active'] = False
            return {'active': False}

        # Check if human has been detected for the threshold duration
        elapsed_time = current_time - human_detection_state['first_detected_at']
        if elapsed_time >= human_detection_state['detection_threshold']:
            # Trigger the alarm if not already triggered
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
    try:
        detection_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = send_whatsapp_message("6281238875634", f"Manusia detected at {detection_time}!")
        if result:
            return jsonify({'success': True, 'message': 'Pesan Telah Terkirim'})
        else:
            return jsonify({'success': False, 'message': 'Gagal mengirim pesan'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



if __name__ == '__main__':
    # Use threaded mode for better performance
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
