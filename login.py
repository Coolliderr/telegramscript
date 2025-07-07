from fastapi import FastAPI
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.tl.types import User
from fastapi import HTTPException
import os
import asyncio
from fastapi.responses import FileResponse

app = FastAPI()

# 替换为你自己的 API 信息
api_id = int(os.getenv("API_ID", "123456"))
api_hash = os.getenv("API_HASH", "your_api_hash")
SESSION_DIR = "session"

if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

clients = {}
client_locks = {}

def normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("+", "")

async def get_lock(phone: str) -> asyncio.Lock:
    if phone not in client_locks:
        client_locks[phone] = asyncio.Lock()
    return client_locks[phone]

async def get_client(phone: str) -> TelegramClient:
    clean_phone = normalize_phone(phone)
    
    if clean_phone in clients:
        return clients[clean_phone]

    session_path = os.path.join(SESSION_DIR, f'session_{clean_phone}')
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        raise HTTPException(
            status_code=401,
            detail=f"Session for {clean_phone} not authorized. Please log in again."
        )

    clients[phone] = client
    return client

class SendMessageModel(BaseModel):
    phone: str
    peer_id: int
    message: str

@app.get("/dialogs")
async def list_dialogs(phone: str):
    phone = normalize_phone(phone)
    lock = await get_lock(phone)

    async with lock:
        client = await get_client(phone)
        dialogs = await client.get_dialogs(limit=100)
        return [{
            "id": d.entity.id,
            "name": getattr(d.entity, "title", None) or getattr(d.entity, "first_name", None) or getattr(d.entity, "username", ""),
            "is_user": isinstance(d.entity, User)
        } for d in dialogs]

@app.get("/messages")
async def get_messages(phone: str, peer_id: int, limit: int = 20):
    phone = normalize_phone(phone)
    lock = await get_lock(phone)

    async with lock:
        client = await get_client(phone)
        entity = await client.get_entity(peer_id)
        messages = await client.get_messages(entity, limit=limit)
        return [{
            "id": m.id,
            "text": m.message,
            "sender_id": m.sender_id
        } for m in messages]

@app.post("/send_message")
async def send_message(data: SendMessageModel):
    phone = normalize_phone(data.phone)
    lock = await get_lock(phone)

    async with lock:
        client = await get_client(phone)
        entity = await client.get_entity(data.peer_id)
        await client.send_message(entity, data.message)
        return {"status": "sent"}

@app.get("/download_session")
async def download_session(phone: str):
    phone = normalize_phone(phone)
    session_file = os.path.join(SESSION_DIR, f"session_{phone}.session")

    if not os.path.exists(session_file):
        raise HTTPException(status_code=404, detail="Session file not found")

    return FileResponse(
        path=session_file,
        filename=f"{phone}.session",
        media_type='application/octet-stream'
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("login:app", host="0.0.0.0", port=8080, reload=False)
