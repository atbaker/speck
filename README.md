# speck-app

## PyInstaller

pyinstaller --additional-hooks-dir=services/hooks --add-data "services/models/Meta-Llama-3-8B-Instruct.Q4_0.gguf:models/" services/server.py
pyinstaller --onefile --additional-hooks-dir=services/hooks services/server.py
pyinstaller --additional-hooks-dir=services/hooks services/server.py

http://localhost:7725/chat?prompt=Why%20is%20the%20sky%20blue?