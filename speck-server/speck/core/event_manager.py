from typing import Dict
from fastapi import WebSocket

class EventManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        connection_id = str(id(websocket))
        self.connections[connection_id] = websocket

    def disconnect(self, websocket: WebSocket):
        connection_id = str(id(websocket))
        if connection_id in self.connections:
            del self.connections[connection_id]

    async def notify(self, message: dict):
        connection_ids = list(self.connections.keys())
        for connection_id in connection_ids:
            websocket = self.connections.get(connection_id)
            if websocket:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    self.disconnect(websocket)

event_manager = EventManager()
