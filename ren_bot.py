import os
import asyncio
import time
from pyrogram import Client, filters
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

app = Client("file_renamer_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
flask_app = Flask(__name__)

user_files = {}
user_cancel_flags = {}
download_tasks = {}
upload_tasks = {}
awaiting_split_lines = {}

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
RENAME_FAILED_MSG = "<b>❌ Renaming Failed!</b> <i>The file could not be renamed. It might be open, or the new name contains invalid characters. Try a simpler name.</i>" # Added for rename error handling

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

def format_size(size_bytes):
    """Converts bytes to the most appropriate human-readable format (B, KB, MB, GB)."""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(os.path.floor(os.path.log(size_bytes, 1024)))
    p = 1024 ** i
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_progress_fn(message, prefix):
    start_time = time.time()
    last_update = {"current": 0, "timestamp": start_time}
    is_download = "Download" in prefix or "⬇️" in prefix
    cancel_callback = "cancel_download" if is_download else "cancel_upload"
    cancel_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)]
    ])
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
        
        # Use the new format_size function
        current_size_str = format_size(current)
        total_size_str = format_size(total)

        try:
            await message.edit_text(
                f"{prefix}: {percent}% {bar}\n"
                f"📦 **{current_size_str}** of **{total_size_str}**\n"
                f"🚀 Speed: {speed_str}\n"
                f"⏳ ETA: {eta_str}",
                reply_markup=cancel_markup,
                parse_mode=ParseMode.HTML # Ensure HTML parsing is used for bold text
            )
        except MessageNotModified:
            pass
        last_update["current"] = current
        last_update["timestamp"] = now
    return progress

async def check_force_join(client, message):
    try:
        member = await client.get_chat_member(FORCE_JOIN_CHANNEL, message.from_user.id)
        if member.status in ["kicked", "banned"]:
            await message.reply("🚫 You are banned from using this bot.")
            return False
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
async def handle_callbacks(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    if data == "check_join":
        # The recheck_join function is missing, but assuming its purpose
        # is to check membership again and edit the message if successful.
        # For now, we'll keep the structure.
        member = await client.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            await callback_query.message.edit_text("✅ You are now a member! Please try sending your file again.", reply_markup=None)
        else:
            await callback_query.answer("⚠️ You still need to join the channel.", show_alert=True)
    elif data == "txt_rename":
        file_info = user_files.get(user_id)
        if file_info:
            await callback_query.message.reply(
                f"✏️ <b>You chose to rename:</b>\n<code>{file_info['original_name']}</code>\n\n"
                f"📌 Please send the new name including extension (e.g., <code>document.txt</code>)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
                ]),
                parse_mode=ParseMode.HTML
            )
    elif data == "split_txt":
        awaiting_split_lines[user_id] = True
        await callback_query.message.reply("✂️ Send number of lines per split (default is 100):")
    elif data == "cancel_download":
        user_cancel_flags[user_id] = True
        task = download_tasks.get(user_id)
        if task: task.cancel()
        await callback_query.message.edit_text("❌ Download cancelled.")
    elif data == "cancel_upload":
        task = upload_tasks.get(user_id)
        if task: task.cancel()
        await callback_query.message.edit_text("❌ Upload cancelled.")
    elif data == "cancel_rename":
        # Delete the downloaded file on cancel
        file_info = user_files.pop(user_id, None)
        if file_info and os.path.exists(file_info['path']):
            os.remove(file_info['path'])
        await callback_query.message.edit_text("❌ Renaming cancelled. Local file deleted.")
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
async def start_command(client, message):
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
async def handle_file(client, message):
    if not await check_force_join(client, message):
        return
    media = message.document or message.video or message.audio
    user_id = message.chat.id
    file_name = media.file_name or "unnamed"

    await client.send_message(LOG_CHANNEL_ID, f"📥 File received from [{message.from_user.first_name}](tg://user?id={user_id})", parse_mode=ParseMode.MARKDOWN)
    await client.forward_messages(LOG_CHANNEL_ID, message.chat.id, message.id)

    progress_msg = await message.reply("⬇️ Downloading: 0%", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
    ]))

    user_cancel_flags[user_id] = False

    async def download_and_process():
        try:
            file_path = await client.download_media(message, progress=get_progress_fn(progress_msg, "⬇️ Downloading"))
            if user_cancel_flags.get(user_id):
                # Clean up the downloaded file on cancel
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                await message.reply("❌ Download cancelled. Local file deleted.")
                await progress_msg.delete()
                return
            user_files[user_id] = {
                "path": file_path,
                "original_name": file_name,
                "mime": media.mime_type
            }
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Rename", callback_data="txt_rename"),
                 InlineKeyboardButton("✂️ Split", callback_data="split_txt")] if file_name.endswith(".txt")
                else [InlineKeyboardButton("✏️ Rename", callback_data="txt_rename")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
            ])
            await message.reply("📄 Choose what to do:", reply_markup=markup)
            await progress_msg.delete()
        except asyncio.CancelledError:
            await progress_msg.edit_text("❌ Download cancelled.")
        finally:
            user_cancel_flags.pop(user_id, None)
            download_tasks.pop(user_id, None)

    download_tasks[user_id] = asyncio.create_task(download_and_process())

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.chat.id

    if awaiting_split_lines.get(user_id):
        awaiting_split_lines.pop(user_id)
        try: count = int(message.text.strip())
        except: count = 100
        file_info = user_files.pop(user_id, None)
        if not file_info: return await message.reply("❌ File not found.")
        try:
            with open(file_info['path'], "r", encoding="utf-8") as f:
                lines = f.readlines()
            chunks = [lines[i:i+count] for i in range(0, len(lines), count)]
            for i, chunk in enumerate(chunks, start=1):
                name = f"{os.path.splitext(file_info['original_name'])[0]}_part{i}.txt"
                path = os.path.join(os.path.dirname(file_info['path']), name)
                with open(path, "w", encoding="utf-8") as f2:
                    f2.writelines(chunk)
                await message.reply_document(path)
                os.remove(path)
            os.remove(file_info['path'])
        except Exception as e:
            await message.reply(f"❌ Split Failed! Error: {e}")
            # Ensure file cleanup if split fails mid-process
            if os.path.exists(file_info['path']):
                os.remove(file_info['path'])
        return

    if user_id not in user_files:
        return await message.reply("⚠️ No file to rename.")
    new_name = message.text.strip()
    if '.' not in new_name or new_name.startswith('.'):
        return await message.reply(INVALID_NAME_MSG, parse_mode=ParseMode.HTML)

    file_info = user_files.pop(user_id)
    old_path = file_info["path"]
    new_path = os.path.join(os.path.dirname(old_path), new_name)

    # --- FIX: Asynchronous File Rename with Error Handling ---
    try:
        # Use asyncio.to_thread for better async handling of synchronous file ops
        await asyncio.to_thread(os.rename, old_path, new_path)
    except FileNotFoundError:
        await message.reply("❌ Renaming Failed! The original file was not found.")
        return
    except OSError:
        # This catches "file in use," "permission denied," or "invalid character" errors.
        await message.reply(RENAME_FAILED_MSG, parse_mode=ParseMode.HTML)
        # Put the file back in the user_files map in case they want to retry
        user_files[user_id] = file_info
        return
    except Exception as e:
        await message.reply(f"❌ An unexpected error occurred during rename: {e}")
        user_files[user_id] = file_info
        return
    # --------------------------------------------------------
    
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
        except Exception as e:
            await message.reply(f"❌ Upload failed: {e}")
        finally:
            await status_msg.delete()
            if os.path.exists(new_path):
                os.remove(new_path)
            upload_tasks.pop(user_id, None)

    upload_tasks[user_id] = asyncio.create_task(do_upload())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, flask_app.run, "0.0.0.0", 5000)
    app.run()
