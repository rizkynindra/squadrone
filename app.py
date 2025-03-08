from ultralytics import solutions
import os
import torch
import streamlit

torch.classes.__path__ = [os.path.join(torch.__path__[0], torch.classes.__file__)]

# or simply:
torch.classes.__path__ = []


inf = solutions.Inference(
    model="model/best.pt",  # You can use any model that Ultralytics support, i.e. YOLO11, or custom trained model
)

inf.inference()

### Make sure to run the file using command `streamlit run <file-name.py>`