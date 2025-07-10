# squadrone

Squadrone is an object detection project that detect car, and people based on the drone's video. The video will be live in the PC Desktop and the model automatically detect is there any car or people in the video.
The purpose of this project is to detect any malicious movement on the car parking area. 

# create desktop apps
streamlit-desktop-app build app.py --name Squadrone --pyinstaller-options --add-data "D:\SIDE\MACHINE LEARNING PROJECT\squadrone\model:model\best_100.pt"

# how to run

1. download this git as .zip or git clone
2. run Squadrone.exe from directory dist/Squadrone/Squadrone.exe

# Docker

1. docker build .
