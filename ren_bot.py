import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified
from flask import Flask

# Load environment variables
load_dotenv("config.env")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_files = {}

# Flask app for uptime monitoring
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Bot is running!"

# Text templates
START_MSG = """<b> Hello <a href="tg://user?id={user_id}">{user}</a>!</b> 👋🏻
<i>Welcome to <b>File Renaming Bot!</b> ✂️</i>
<i>I can help you rename files Easily 💓</i>
<i>Send me any document, audio, or video file and See the Magic 🪄</i>"""
RECEIVED_FILE_MSG = """<b>📄 File received:</b> <code>{file_name}</code>
<b>Now, please send the new file name (with extension).</b>"""
WAIT_RENAME_MSG = "<b>🔨 Uploading your file... Please wait.</b>"
DONE_RENAME_MSG = "<b>✅ Done!</b> Your file has been renamed to: <code>{new_name}</code>"
INVALID_NAME_MSG = """<b>⚠️ Invalid format!</b> <i>Include a valid extension (e.g., .txt, .pdf).</i>"""
ABOUT_MSG = """<i>🤖 <b>About File Renaming Bot:</b>
This bot allows you to rename any document, video, or audio file in just seconds!
👨‍💻 Developer: <a href="https://t.me/zeus_is_here">ZEUS</a>
🔄 Fast, simple, and efficient!</i>"""
HELP_MSG = """<i>❓ <b>How to use the bot:</b>
1️⃣ Send me any document, audio, or video file.
2️⃣ I’ll ask you to provide the new file name (include extension).
3️⃣ I’ll send back your renamed file — like magic!</i>"""

# Progress bar visuals
def progress_bar(percentage):
    full = int(percentage / 10)
    empty = 10 - full
    return f"[{'█' * full}{'▒' * empty}]"

def get_progress_fn(message, prefix):
    async def progress(current, total):
        percent = int(current * 100 / total)
        bar = progress_bar(percent)
        try:
            await message.edit_text(f"{prefix}: {percent}% {bar}")
        except MessageNotModified:
            pass
    return progress

@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client, message: Message):
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❓ Help", callback_data="help"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("OWNER 🤍", url="https://t.me/zeus_is_here")]
    ])
    await message.reply(
        START_MSG.format(user=message.from_user.first_name, user_id=message.from_user.id),
        reply_markup=markup
    )

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    if data == "help":
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        await callback_query.message.edit_text(HELP_MSG, reply_markup=markup)
    elif data == "about":
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        await callback_query.message.edit_text(ABOUT_MSG, reply_markup=markup)
    elif data == "back":
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ Help", callback_data="help"),
             InlineKeyboardButton("ℹ️ About", callback_data="about")],
            [InlineKeyboardButton("OWNER 🤍", url="https://t.me/zeus_is_here")]
        ])
        await callback_query.message.edit_text(
            START_MSG.format(user=callback_query.from_user.first_name, user_id=callback_query.from_user.id),
            reply_markup=markup
        )

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_file(client, message: Message):
    media = message.document or message.video or message.audio
    progress_msg = await message.reply("⬇️ Downloading: 0% [▒▒▒▒▒▒▒▒▒▒]")

    file_path = await client.download_media(
        message,
        progress=get_progress_fn(progress_msg, "⬇️ Downloading")
    )

    file_name = media.file_name
    user_files[message.chat.id] = {
        "path": file_path,
        "original_name": file_name,
        "mime": media.mime_type
    }

    await message.reply(
        f"<b>✅ File downloaded!</b>\n\n"
        f"<b>Name:</b> <code>{file_name}</code>\n"
        f"<b>Size:</b> <code>{media.file_size // 1024} KB</code>\n"
        f"<b>Type:</b> <code>{media.mime_type}</code>"
    )
    await message.reply(RECEIVED_FILE_MSG.format(file_name=file_name))

@app.on_message(filters.text & filters.private)
async def rename_file(client, message: Message):
    if message.chat.id not in user_files:
        return

    new_name = message.text.strip()
    if '.' not in new_name or new_name.startswith('.'):
        await message.reply(INVALID_NAME_MSG)
        return

    file_info = user_files.pop(message.chat.id)
    new_path = os.path.join(os.path.dirname(file_info["path"]), new_name)
    os.rename(file_info["path"], new_path)

    status_msg = await message.reply("✏️ Renaming file...")

    await status_msg.edit_text("⬆️ Uploading: 0% [▒▒▒▒▒▒▒▒▒▒]")

    try:
        await message.reply_document(
            document=new_path,
            caption=DONE_RENAME_MSG.format(new_name=new_name),
            progress=get_progress_fn(status_msg, "⬆️ Uploading")
        )
    except Exception as e:
        await message.reply(f"❌ Upload failed: {e}")
        return

    await asyncio.sleep(1)
    if os.path.exists(new_path):
        os.remove(new_path)

# Start Flask app + bot
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, flask_app.run, "0.0.0.0", 5000)
    app.run()
