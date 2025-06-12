import os
import asyncio
import time
from threading import Thread
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified, UserNotParticipant
from pyrogram.enums import ParseMode
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL")

app = Client("renamer_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
flask_app = Flask(__name__)

user_files = {}
user_cancel_flags = {}
download_tasks = {}
upload_tasks = {}

@flask_app.route("/")
def index():
    return "Bot is running!"

START_MSG = """<b> Hello <a href="tg://user?id={user_id}">{user}</a>!</b> 👋🏻
<i>Welcome to <b>File Renaming Bot!</b> ✂️</i>
<i>I can help you rename files Easily 💓</i>
<i>Send me any document, audio, or video file and See the Magic 🪄</i>"""

RECEIVED_FILE_MSG = """<b>📄 File received:</b> <code>{file_name}</code>
<b>Now, please send the new file name (with extension).</b>"""

WAIT_RENAME_MSG = "<b>🔨 Uploading your file... Please wait.</b>"
DONE_RENAME_MSG = "<b>✅ Done!</b> Your file has been renamed to: <code>{new_name}</code>"
INVALID_NAME_MSG = "<b>⚠️ Invalid format!</b> <i>Include a valid extension (e.g., .txt, .pdf).</i>"

ABOUT_MSG = """<i>🤖 <b>About File Renaming Bot:</b>
This bot allows you to rename any document, video, or audio file in just seconds!
👨‍💻 Developer: <a href="https://t.me/zeus_is_here">ZEUS</a>
🔄 Fast, simple, and efficient!</i>"""

HELP_MSG = """<i>❓ <b>How to use the bot:</b>
1️⃣ Send me any document, audio, or video file.
2️⃣ I’ll ask you to provide the new file name (include extension).
3️⃣ I’ll send back your renamed file — like magic!</i>"""

def progress_bar(percent):
    full = int(percent / 10)
    empty = 10 - full
    return f"[{'█' * full}{'▒' * empty}]"

def get_progress_fn(message, prefix):
    start_time = time.time()
    last_update = {"current": 0, "timestamp": start_time}
    is_download = "⬇️" in prefix
    cancel_callback = "cancel_download" if is_download else "cancel_upload"
    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)]])
    async def progress(current, total):
        now = time.time()
        elapsed = now - last_update["timestamp"]
        diff = current - last_update["current"]
        if elapsed < 1.5:
            return
        speed = diff / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        percent = int(current * 100 / total)
        bar = progress_bar(percent)
        speed_str = f"{speed / 1024:.2f} KB/s" if speed < 1024 * 1024 else f"{speed / (1024 * 1024):.2f} MB/s"
        eta_str = time.strftime("%M:%S", time.gmtime(eta))
        try:
            await message.edit_text(
                f"{prefix}: {percent}% {bar}\n"
                f"📦 {current // 1024} KB of {total // 1024} KB\n"
                f"🚀 Speed: {speed_str}\n"
                f"⏳ ETA: {eta_str}",
                reply_markup=cancel_markup
            )
        except MessageNotModified:
            pass
        last_update["current"] = current
        last_update["timestamp"] = now
    return progress

async def check_force_join(client, message):
    try:
        await client.get_chat_member(FORCE_JOIN_CHANNEL, message.from_user.id)
        return True
    except UserNotParticipant:
        link = await client.export_chat_invite_link(FORCE_JOIN_CHANNEL)
        await message.reply(
            "📢 <b>Join our updates channel to use this bot.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Join Channel", url=link)],
                [InlineKeyboardButton("🔁 I've Joined", callback_data="check_join")]
            ]),
            parse_mode=ParseMode.HTML
        )
        return False

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    if data == "check_join":
        if await check_force_join(client, callback_query.message):
            await callback_query.message.delete()
            await start_command(client, callback_query.message)
    elif data == "cancel_download":
        user_cancel_flags[user_id] = True
        task = download_tasks.get(user_id)
        if task: task.cancel()
    elif data == "cancel_upload":
        task = upload_tasks.get(user_id)
        if task: task.cancel()
    elif data == "cancel_rename":
        user_files.pop(user_id, None)
        await callback_query.message.edit_text("❌ Renaming cancelled.")
    elif data == "help":
        await callback_query.message.edit_text(HELP_MSG, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="back")]
        ]), parse_mode=ParseMode.HTML)
    elif data == "about":
        await callback_query.message.edit_text(ABOUT_MSG, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="back")]
        ]), parse_mode=ParseMode.HTML)
    elif data == "back":
        await callback_query.message.edit_text(
            START_MSG.format(user=callback_query.from_user.first_name, user_id=user_id),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ Help", callback_data="help"),
                 InlineKeyboardButton("ℹ️ About", callback_data="about")],
                [InlineKeyboardButton("OWNER 🤍", url="https://t.me/zeus_is_here")]
            ]),
            parse_mode=ParseMode.HTML
        )

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    if not await check_force_join(client, message):
        return
    await message.reply(
        START_MSG.format(user=message.from_user.first_name, user_id=message.from_user.id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ Help", callback_data="help"),
             InlineKeyboardButton("ℹ️ About", callback_data="about")],
            [InlineKeyboardButton("OWNER 🤍", url="https://t.me/zeus_is_here")]
        ]),
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client, message: Message):
    if not await check_force_join(client, message):
        return
    user_id = message.chat.id
    media = message.document or message.video or message.audio
    file_name = media.file_name or "file"
    await client.send_message(LOG_CHANNEL_ID, f"📥 File from [{message.from_user.first_name}](tg://user?id={user_id})", parse_mode=ParseMode.MARKDOWN)
    await client.forward_messages(LOG_CHANNEL_ID, user_id, message.id)
    progress_msg = await message.reply("⬇️ Downloading: 0%", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
    ]))
    user_cancel_flags[user_id] = False
    async def download_and_process():
        try:
            file_path = await client.download_media(message, progress=get_progress_fn(progress_msg, "⬇️ Downloading"))
            if user_cancel_flags.get(user_id):
                await message.reply("❌ Download cancelled.")
                return
            user_files[user_id] = {"path": file_path, "original_name": file_name, "mime": media.mime_type}
            await message.reply(RECEIVED_FILE_MSG.format(file_name=file_name), reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
            ]), parse_mode=ParseMode.HTML)
        except asyncio.CancelledError:
            await message.reply("❌ Download cancelled.")
        finally:
            download_tasks.pop(user_id, None)
            await progress_msg.delete()
    download_tasks[user_id] = asyncio.create_task(download_and_process())

@app.on_message(filters.text & filters.private)
async def rename_file(client, message: Message):
    user_id = message.chat.id
    if user_id not in user_files:
        await message.reply("⚠️ No file to rename. Please send a file first.")
        return
    new_name = message.text.strip()
    if '.' not in new_name or new_name.startswith('.'):
        await message.reply(INVALID_NAME_MSG, parse_mode=ParseMode.HTML)
        return
    file_info = user_files.pop(user_id)
    new_path = os.path.join(os.path.dirname(file_info["path"]), new_name)
    os.rename(file_info["path"], new_path)
    status_msg = await message.reply(WAIT_RENAME_MSG, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_upload")]
    ]))
    async def do_upload():
        try:
            await message.reply_document(
                new_path,
                caption=DONE_RENAME_MSG.format(new_name=new_name),
                parse_mode=ParseMode.HTML,
                progress=get_progress_fn(status_msg, "⬆️ Uploading")
            )
        except asyncio.CancelledError:
            await message.reply("❌ Upload cancelled.")
        finally:
            upload_tasks.pop(user_id, None)
            await status_msg.delete()
            if os.path.exists(new_path):
                os.remove(new_path)
    upload_tasks[user_id] = asyncio.create_task(do_upload())

def start_flask():
    flask_app.run("0.0.0.0", 5000)

if __name__ == "__main__":
    Thread(target=start_flask).start()
    app.start()
    print("Bot is running...")
    idle()
    app.stop()
