# squadrone


pyinstaller --onefile --add-data "model:./model" app.py --name "Squadrone"

streamlit-desktop-app build app.py --name Squadrone --icon path/to/icon.ico --pyinstaller-options --onefile --noconfirm
streamlit-desktop-app build app.py --name Squadrone --pyinstaller-options --add-data "D:\SIDE\MACHINE LEARNING PROJECT\squadrone\model:model\best_100.pt"