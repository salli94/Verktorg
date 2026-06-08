import json
from fastapi import WebSocket, WebSocketDisconnect
from .auth import decode_token


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id] = [
                w for w in self.active_connections[user_id] if w != websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            dead = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_text(json.dumps(message, default=str))
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(ws, user_id)

    async def broadcast(self, message: dict):
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


async def authenticate_websocket(websocket: WebSocket) -> int | None:
    token = websocket.query_params.get("token")
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    return int(payload.get("sub"))


async def create_and_send_notification(
    db,
    user_id: int,
    type: str,
    message: str,
    data: dict = None,
):
    from .models import Notification
    notif = Notification(
        user_id=user_id,
        type=type,
        message=message,
        data=data or {},
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    await manager.send_personal_message(
        {
            "type": "notification",
            "notification": {
                "id": notif.id,
                "type": type,
                "message": message,
                "data": data or {},
                "is_read": False,
                "created_at": str(notif.created_at),
            },
        },
        user_id,
    )
    return notif
