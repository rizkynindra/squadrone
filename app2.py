from flask import Flask, render_template, request, jsonify, send_from_directory
import base64
import cv2
import numpy as np
from ultralytics import YOLO
import io
from PIL import Image
import time
import torch
import logging
from datetime import datetime
import requests

# Configure logging for manusia detection
logging.basicConfig(
    filename='manusia_detection.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

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
model = YOLO('model/best_rtdetr.pt')

#use GPU
# model.to('cuda')
# print(f"YOLO model loaded on device: {model.device}")

# Model configuration
CONFIDENCE_THRESHOLD = 0.3 # Lower confidence threshold for better detection
IMAGE_SIZE = 480  # Smaller inference size can improve performance

# Human detection tracking
human_detection_state = {
    'first_detected_at': None,
    'is_alarm_active': False,
    'last_detection_time': 0,
    'detection_threshold': 0.05  # 1 seconds
}

@app.route('/')
def index():
    return render_template('screen_share.html')


@app.route('/detect', methods=['POST'])
def detect():
    start_time = time.time()
    try:
        # Get image data from request
        data = request.json
        image_data = data['image']

        # Remove the prefix from base64 data
        if 'data:image/jpeg;base64,' in image_data:
            image_data = image_data.replace('data:image/jpeg;base64,', '')
        elif 'data:image/png;base64,' in image_data:
            image_data = image_data.replace('data:image/png;base64,', '')

        # Decode base64 to image
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to OpenCV format
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Run detection with optimized parameters
        results = model.predict(
            source=frame,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,
            imgsz=IMAGE_SIZE,  # Use smaller size for faster inference
            iou=0.5
        )

        # Process results
        detections = []
        human_detected = False

        for result in results:
            boxes = result.boxes.xyxy.cpu().numpy()
            scores = result.boxes.conf.cpu().numpy()
            classes = result.boxes.cls.cpu().numpy()

            for box, score, cls in zip(boxes, scores, classes):
                x1, y1, x2, y2 = map(int, box)
                class_name = model.names[int(cls)]

                # save to log if manusia detected
                if class_name.lower() == 'manusia':
                    detection_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    logging.info(f"Detected 'manusia' at {detection_time} with confidence {score:.4f}")

                # Check if this is a human/person detection
                if class_name.lower() == 'manusia':
                    human_detected = True

                detections.append({
                    'box': [x1, y1, x2, y2],
                    'class': class_name,
                    'confidence': float(score)
                })

        # Update human detection state
        current_time = time.time()
        alarm_status = check_human_detection(human_detected, current_time)

        processing_time = time.time() - start_time
        return jsonify({
            'success': True,
            'detections': detections,
            'processing_time_ms': round(processing_time * 1000, 2),
            'alarm': alarm_status
        })

    except Exception as e:
        print(f"Error processing image: {str(e)}")
        # Reset human detection on error
        reset_human_detection()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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


if __name__ == '__main__':
    # Use threaded mode for better performance
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
