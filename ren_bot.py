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

START_MSG = """<b>Hello <a href="tg://user?id={user_id}">{user}</a>! 👋🏻</b>

<i>Welcome to <b>File Renaming Bot!</b> ✂️</i>
<i>I can help you rename files Easily 💖</i>
<i>Send me any document, audio, or video file and See the Magic 🪄</i>"""

RECEIVED_FILE_MSG = """<b>📄 File received:</b> <code>{file_name}</code>
<b>Now, please send the new file name (with extension).</b>"""

WAIT_RENAME_MSG = "<b>⚙️ Uploading your file... Please wait.</b>"
DONE_RENAME_MSG = "<b>✅ Done!</b> Your file has been renamed to: <code>{new_name}</code>"
INVALID_NAME_MSG = "<b>⚠️ Invalid format!</b> <i>Include a valid extension (e.g., .txt, .pdf).</i>"

ABOUT_MSG = """<i>🤖 <b>About File Renaming Bot:</b>
This bot allows you to rename any document, video, or audio file in just seconds!

👨‍💻 Developer: <a href="https://t.me/zeus_is_here">ZEUS</a>
⚡ Fast, simple, and efficient!</i>"""

HELP_MSG = """<i>❓ <b>How to use the bot:</b>
1️⃣ Send me any document, audio, or video file.
2️⃣ I’ll ask you to provide the new file name (include extension).
3️⃣ I’ll send back your renamed file — like magic! ✨</i>"""

def progress_bar(percent):
    full = int(percent / 10)
    empty = 10 - full
    return f"[{'█' * full}{'░' * empty}]"

def convert_size(size_bytes):
    """Convert bytes to the most appropriate unit (KB, MB, GB)."""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} Bytes"

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
            
        # Calculate speed
        speed = diff / elapsed if elapsed > 0 else 0
        speed_str = f"{speed / 1024:.2f} KB/s" if speed < 1024 * 1024 else f"{speed / (1024 * 1024):.2f} MB/s"
        
        # Calculate ETA
        eta = (total - current) / speed if speed > 0 else 0
        eta_str = time.strftime("%M:%S", time.gmtime(eta))
        
        # Calculate percentage and bar
        percent = int(current * 100 / total)
        bar = progress_bar(percent)
        
        # Use the new helper function to format size
        current_size_str = convert_size(current)
        total_size_str = convert_size(total)

        try:
            await message.edit_text(
                f"{prefix}: {percent}% {bar}\n"
                f"📦 {current_size_str} of {total_size_str}\n"
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
    except Exception as e:
        # Assuming we don't want to block users if we can't check the channel
        print(f"Error checking force join: {e}")
        return True

async def recheck_join(client, callback_query):
    user_id = callback_query.from_user.id
    try:
        member = await client.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            await callback_query.message.edit_text(
                START_MSG.format(user=callback_query.from_user.first_name, user_id=user_id),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❓ Help", callback_data="help"),
                     InlineKeyboardButton("ℹ️ About", callback_data="about")],
                    [InlineKeyboardButton("OWNER 💝", url="https://t.me/zeus_is_here")]
                ]),
                parse_mode=ParseMode.HTML
            )
            await callback_query.answer("✅ Thanks for joining!", show_alert=True)
        else:
            await callback_query.answer("⚠️ You haven't joined yet!", show_alert=True)
    except UserNotParticipant:
        await callback_query.answer("⚠️ You haven't joined yet!", show_alert=True)
    except Exception as e:
        await callback_query.answer("An error occurred. Please try again later.", show_alert=True)
        print(f"Error during recheck_join: {e}")


@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    await callback_query.answer() # Acknowledge the callback

    if data == "check_join":
        await recheck_join(client, callback_query)
    elif data == "txt_rename":
        file_info = user_files.get(user_id)
        if file_info:
            await callback_query.message.reply(
                f"✏️ <b>You chose to rename:</b>\n<code>{file_info['original_name']}</code>\n\n"
                f"📜 Please send the new name including extension (e.g., <code>document.txt</code>)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
                ]),
                parse_mode=ParseMode.HTML
            )
            await callback_query.message.delete()
    elif data == "split_txt":
        file_info = user_files.get(user_id)
        if file_info and file_info['original_name'].lower().endswith((".txt", ".text")):
            awaiting_split_lines[user_id] = True
            await callback_query.message.reply("✂️ Send number of lines per split (default is 100):")
            await callback_query.message.delete()
        else:
            await callback_query.message.edit_text("❌ This file type cannot be split.")
    elif data == "cancel_download":
        user_cancel_flags[user_id] = True
        task = download_tasks.pop(user_id, None)
        if task: task.cancel()
        await callback_query.message.edit_text("❌ Download cancelled.")
        file_info = user_files.pop(user_id, None)
        if file_info and os.path.exists(file_info["path"]):
            os.remove(file_info["path"])
    elif data == "cancel_upload":
        task = upload_tasks.pop(user_id, None)
        if task: task.cancel()
        await callback_query.message.edit_text("❌ Upload cancelled.")
        # Try to clean up the file after rename but before upload
        # Note: If the file was renamed, we need to know the 'new_path' which is lost here.
        # A safer approach for cancel_upload would be to rely on the upload function's 'finally' block
        # to clean up the file using its path (`new_path`).
        # For immediate clean up here, we'll try to guess the path if it was in user_files (which it isn't anymore).
        # We'll stick to the cleanup in do_upload's finally block for renamed files.
    elif data == "cancel_rename":
        file_info = user_files.pop(user_id, None)
        if file_info and os.path.exists(file_info["path"]):
            os.remove(file_info["path"])
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
                [InlineKeyboardButton("OWNER 💝", url="https://t.me/zeus_is_here")]
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
            [InlineKeyboardButton("OWNER 💝", url="https://t.me/zeus_is_here")]
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

    # Log file reception
    try:
        await client.send_message(LOG_CHANNEL_ID, f"📥 File received from [{message.from_user.first_name}](tg://user?id={user_id})\nFile: `{file_name}`", parse_mode=ParseMode.MARKDOWN)
        await client.forward_messages(LOG_CHANNEL_ID, message.chat.id, message.id)
    except Exception as e:
        print(f"Could not log message: {e}")

    progress_msg = await message.reply("⬇️ Downloading: 0%", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
    ]))

    user_cancel_flags[user_id] = False

    async def download_and_process():
        file_path = None
        try:
            file_path = await client.download_media(message, progress=get_progress_fn(progress_msg, "⬇️ Downloading"))
            
            if user_cancel_flags.get(user_id):
                await message.reply("❌ Download cancelled.")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                return

            user_files[user_id] = {
                "path": file_path,
                "original_name": file_name,
                "mime": media.mime_type
            }
            
            # Check if it's a text file to offer the split option
            # Check for file extension and size limit for safety
            if file_name.lower().endswith((".txt", ".text")) and media.file_size < 50 * 1024 * 1024:
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Rename", callback_data="txt_rename"),
                     InlineKeyboardButton("✂️ Split", callback_data="split_txt")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
                ])
            else:
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Rename", callback_data="txt_rename")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
                ])

            await progress_msg.edit_text("📄 Choose what to do:", reply_markup=markup)
            
        except asyncio.CancelledError:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            try:
                await progress_msg.edit_text("❌ Download cancelled.")
            except:
                pass # Message might be deleted
        except Exception as e:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            try:
                await progress_msg.edit_text(f"❌ An error occurred during download: {e}")
            except:
                await message.reply(f"❌ An error occurred during download: {e}")
        finally:
            user_cancel_flags.pop(user_id, None)
            download_tasks.pop(user_id, None)

    download_tasks[user_id] = asyncio.create_task(download_and_process())

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.chat.id
    
    if awaiting_split_lines.get(user_id):
        awaiting_split_lines.pop(user_id)
        
        file_info = user_files.pop(user_id, None)
        if not file_info or not os.path.exists(file_info['path']):
            return await message.reply("❌ File not found for splitting or already processed.")
            
        try:
            count = int(message.text.strip())
            if count <= 0:
                count = 100
        except ValueError:
            count = 100
        
        reply_msg = await message.reply(f"✂️ Splitting file into chunks of {count} lines...")
        
        try:
            with open(file_info['path'], "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            chunks = [lines[i:i+count] for i in range(0, len(lines), count)]
            
            if not chunks:
                 await reply_msg.edit_text("⚠️ File is empty or line count is too large. Split cancelled.")
                 return

            temp_dir = os.path.dirname(file_info['path'])
            original_base_name = os.path.splitext(file_info['original_name'])[0]
            
            await reply_msg.edit_text(f"✅ File split into {len(chunks)} parts. Starting upload...")

            for i, chunk in enumerate(chunks, start=1):
                name = f"{original_base_name}_part{i}.txt"
                path = os.path.join(temp_dir, name)
                
                with open(path, "w", encoding="utf-8") as f2:
                    f2.writelines(chunk)
                
                await message.reply_document(path, caption=f"Part {i}/{len(chunks)} of `{file_info['original_name']}`")
                os.remove(path)
                
            await message.reply("🥳 All parts uploaded successfully!")

        except Exception as e:
            await message.reply(f"❌ An error occurred during splitting/uploading: {e}")
        finally:
            if os.path.exists(file_info['path']):
                os.remove(file_info['path'])
            try:
                await reply_msg.delete()
            except:
                pass
        return

    if user_id not in user_files:
        return await message.reply("⚠️ No file is currently waiting for a new name. Please send a file first.")
    
    new_name = message.text.strip()
    if not new_name or '.' not in new_name or new_name.startswith('.'):
        return await message.reply(INVALID_NAME_MSG, parse_mode=ParseMode.HTML)

    file_info = user_files.pop(user_id)
    original_path = file_info["path"]
    new_path = os.path.join(os.path.dirname(original_path), new_name)

    if not os.path.exists(original_path):
        return await message.reply("❌ Original file not found on server. Please re-upload.")
        
    try:
        os.rename(original_path, new_path)
    except Exception as e:
        user_files[user_id] = file_info
        return await message.reply(f"❌ Failed to rename file locally: {e}\n\nPlease try again with a different name or cancel.")

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
            await message.reply(f"❌ An error occurred during upload: {e}")
        finally:
            try:
                await status_msg.delete()
            except:
                pass
            if os.path.exists(new_path):
                os.remove(new_path)
            upload_tasks.pop(user_id, None)

    upload_tasks[user_id] = asyncio.create_task(do_upload())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # Run Flask in a separate thread/executor
    loop.run_in_executor(None, flask_app.run, "0.0.0.0", 5000)
    # Start the Pyrogram client
    app.run()
