# squadron v1.0.3

Changelog v1.0.3:
- show log in application if 'manusia' detected.
- set alarm sound ringing for 3 seconds.
- Add toogle button to enable/disable all bounding boxes.
- always show log when 'manusia' detected.
- add RT-DETR model.

[![Result](https://github.com/rizkynindra/squadrone/blob/main/result/01.mp4)]

Squadrone is an object-detection project based on captured video from Drone. 
The purpose of this project is to detect malicious object on the parking area. 

# how to run

1. run pip install -r requirements.txt (for the first time)
2. run squadron.bat or squadron_.bat
3. if manual, you can run python3 main.py or waitress-serve --listen=*:5000 app2:app