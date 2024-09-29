from typing import Set
from fastapi import WebSocket, WebSocketDisconnect
import asyncio

class EventManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        # Start the heartbeat task and store it
        heartbeat_task = asyncio.create_task(self._start_heartbeat(websocket))
        self.active_connections[websocket] = heartbeat_task

    def disconnect(self, websocket: WebSocket):
        # Cancel the heartbeat task associated with the websocket
        heartbeat_task = self.active_connections.pop(websocket, None)
        if heartbeat_task:
            heartbeat_task.cancel()

    async def broadcast(self, message: dict):
        for connection in self.active_connections.copy():
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                self.disconnect(connection)

    async def _start_heartbeat(self, websocket: WebSocket):
        try:
            while True:
                await asyncio.sleep(10)  # Heartbeat interval in seconds
                await websocket.send_json({"type": "heartbeat"})
        except asyncio.CancelledError:
            # Handle the cancellation by simply passing
            pass
        except Exception as e:
            # Handle other exceptions if necessary
            print(f"Heartbeat error: {e}")

event_manager = EventManager()
