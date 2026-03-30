import socketio

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

@sio.event
async def connect(sid, environ, auth):
    print(f"Socket connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Socket disconnected: {sid}")

@sio.on("join-room")
async def join_room(sid, room_id):
    await sio.enter_room(sid, room_id)

@sio.on("send-message")
async def send_message(sid, message):
    room_id = message.get("roomId")
    if not room_id:
        return
    await sio.emit("receive-message", {
        "sender": sid,
        "content": message.get("content"),
        "topicId": message.get("topicId"),
    }, room=room_id)
