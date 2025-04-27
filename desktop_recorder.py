import cv2
import numpy as np
import mss
from ultralytics import YOLO
import pygetwindow as gw
import win32gui
import ctypes

# Load YOLO model
model = YOLO('model/best_100_fix.pt')

# Nama window target
target_window_title = "GOM Player"  # Ganti sesuai window yang mau dideteksi

# Cari window
windows = gw.getWindowsWithTitle(target_window_title)
if not windows:
    print(f"Window '{target_window_title}' not found!")
    exit()

target_window = windows[0]

# Start MSS
sct = mss.mss()

print(f"Capturing window: {target_window_title}")

# Create OpenCV window
cv2.namedWindow('Window Detection', cv2.WINDOW_NORMAL)

# Resize window OpenCV jadi besar
screen_width = 960
screen_height = 540
cv2.resizeWindow('Window Detection', screen_width, screen_height)
cv2.moveWindow('Window Detection', 0, 0)  # Pojok kiri atas

# Function to set OpenCV window always on top
def set_window_topmost(window_name):
    hwnd = ctypes.windll.user32.FindWindowW(None, window_name)
    if hwnd != 0:
        ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)

while True:
    # Update lokasi window target
    rect = win32gui.GetWindowRect(target_window._hWnd)
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top

    # Kalau window target minimize atau ketutup, skip
    if width == 0 or height == 0:
        cv2.imshow('Window Detection', np.zeros((screen_height, screen_width, 3), dtype=np.uint8))
        cv2.putText(frame, "Target Window Minimized or Closed", (50, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    monitor = {
        "top": top,
        "left": left,
        "width": width,
        "height": height
    }

    # Capture window
    sct_img = sct.grab(monitor)

    # Convert to numpy
    frame = np.array(sct_img)
    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    # Run detection
    results = model.predict(source=frame, conf=0.3, verbose=False)

    # Draw bounding boxes
    for result in results:
        boxes = result.boxes.xyxy.cpu().numpy()
        scores = result.boxes.conf.cpu().numpy()
        classes = result.boxes.cls.cpu().numpy()

        for box, score, cls in zip(boxes, scores, classes):
            x1, y1, x2, y2 = map(int, box)
            # label = f"{model.names[int(cls)]} {score:.2f}"
            label_name = model.names[int(cls)]  # ambil nama class berdasarkan index

            target_classes = ["manusia", "human"]

            # Hanya lanjutkan kalau class = 'manusia'
            if label_name.lower() not in target_classes:
                continue  # skip kalau bukan manusia

            label = f"{label_name} {score:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Resize frame supaya pas dengan layar besar
    frame_resized = cv2.resize(frame, (screen_width, screen_height))

    # Tampilkan
    cv2.imshow('Window Detection', frame_resized)

    # Set window always on top
    set_window_topmost('Window Detection')

    # Quit when 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
