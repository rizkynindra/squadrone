from ultralytics import solutions
import os
import torch
import streamlit
import sys

torch.classes.__path__ = [os.path.join(torch.__path__[0], torch.classes.__file__)]

# or simply:
torch.classes.__path__ = []

# Get the base path for PyInstaller compatibility
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS  # Extracted temp directory for PyInstaller
else:
    base_path = os.path.dirname(__file__)  # Regular path for development

# Use os.path.join to avoid issues with backslashes
model_path = os.path.join(base_path, 'model', 'best_100_fix.pt')
model_path = os.path.normpath(model_path)  # Normalize path for Windows/Linux

inf = solutions.Inference(
    model=model_path,  # You can use any model that Ultralytics support, i.e. YOLO11, or custom trained model
    #for desktop apps
    # model="https://huggingface.co/rizkynindra/squadrone/blob/main/best_100.pt"
)

inf.inference()

### Make sure to run the file using command `streamlit run <file-name.py>`