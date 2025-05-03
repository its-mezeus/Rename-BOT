import telebot
from telebot import types
import os
import time
import re
import sys
import signal

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

user_files = {}

FORCE_JOIN_CHANNEL = "botsproupdates"
TEMP_DIR = "/tmp"  # safer file write path on Render

START_MSG = """<b> Hello <a href="tg://user?id={user_id}">{user}</a>!</b> 👋🏻

<i>Welcome to <b>File Renaming Bot!</b> ✂️</i>
<i>I can help you rename files Easily 💓</i>
<i>Send me any document, audio, or video file and See the Magic 🪄</i>
"""
RECEIVED_FILE_MSG = """<b>📄 File received:</b> <code>{file_name}</code>
<b>Now, please send the new file name (with extension).</b>"""
ASK_NEW_NAME_MSG = """<b>🔄 Send the new name for your file.</b>
<i>Example: newfile.pdf</i>"""
WAIT_RENAME_MSG = "<b>🔨 Renaming your file... Please wait a moment.</b>"
DONE_RENAME_MSG = "<b>✅ Done!</b> Your file has been renamed to: <code>{new_name}</code>"
INVALID_NAME_MSG = """<b>⚠️ Invalid format!</b> <i>Include a valid extension (e.g., .txt, .pdf).</i>"""
CANCEL_MSG = "<b>❌ Operation canceled. Send a new file to restart.</b>"
DOWNLOAD_PROGRESS_MSG = "<b>⏬ Downloading your file... {percent}%</b>"
UPLOAD_PROGRESS_MSG = "<b>⏫ Uploading your file... {percent}%</b>"
ABOUT_MSG = """<i>🤖 <b>About File Renaming Bot:</b>

This bot allows you to rename any document, video, or audio file in just seconds!

👨‍💻 Developer: <a href="https://t.me/zeus_is_here">ZEUS</a>
🔄 Fast, simple, and efficient!</i>"""
HELP_MSG = """<i>❓ <b>How to use the bot:</b>

1️⃣ Send me any document, audio, or video file.
2️⃣ I’ll ask you to provide the new file name (include extension).
3️⃣ I’ll send back your renamed file — like magic!</i>"""

def get_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"

def check_force_join(user_id):
    try:
        member = bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    if not check_force_join(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("JOIN CHANNEL ✅", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        markup.add(btn)
        bot.send_message(message.chat.id, "<b>🚫 You must join our updates channel to use this bot.</b>", reply_markup=markup)
        return

    markup = types.InlineKeyboardMarkup()
    help_btn = types.InlineKeyboardButton("❓ Help", callback_data="help")
    about_btn = types.InlineKeyboardButton("ℹ️ About", callback_data="about")
    owner_btn = types.InlineKeyboardButton("OWNER 🤍", url="https://t.me/zeus_is_here")
    markup.row(help_btn, about_btn)
    markup.add(owner_btn)

    bot.send_message(
        message.chat.id,
        START_MSG.format(user=message.from_user.first_name, user_id=message.from_user.id),
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_callback(call):
    markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("⬅️ Back", callback_data="back")
    markup.add(back_btn)
    bot.edit_message_text(HELP_MSG, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "about")
def about_callback(call):
    markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("⬅️ Back", callback_data="back")
    markup.add(back_btn)
    bot.edit_message_text(ABOUT_MSG, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back_callback(call):
    send_welcome(call.message)

@bot.message_handler(content_types=['document', 'video', 'audio'])
def handle_file(message):
    if not check_force_join(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("JOIN CHANNEL ✅", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        markup.add(btn)
        bot.send_message(message.chat.id, "<b>🚫 You must join our updates channel to use this bot.</b>", reply_markup=markup)
        return

    file = message.document or message.video or message.audio

    if file.file_size > 2 * 1024 * 1024 * 1024:
        bot.send_message(message.chat.id, "<b>⚠️ File too large! Max allowed size is 2GB.</b>")
        return

    msg = bot.send_message(message.chat.id, DOWNLOAD_PROGRESS_MSG.format(percent=0))
    for percent in [10, 30, 60, 90, 100]:
        time.sleep(0.2)
        bot.edit_message_text(DOWNLOAD_PROGRESS_MSG.format(percent=percent), message.chat.id, msg.message_id)

    try:
        file_info = bot.get_file(file.file_id)
        file_data = bot.download_file(file_info.file_path)
        file_name = file.file_name
        file_size = get_size(file.file_size)
        file_type = file.mime_type
    except Exception as e:
        bot.send_message(message.chat.id, f"<b>Error downloading file:</b> {str(e)}")
        return

    user_files[message.chat.id] = {
        "data": file_data,
        "mime": file_type,
        "original_name": file_name,
    }

    bot.edit_message_text(
        f"<b>✅ File downloaded!</b>\n\n"
        f"<b>Name:</b> <code>{file_name}</code>\n"
        f"<b>Size:</b> <code>{file_size}</code>\n"
        f"<b>Type:</b> <code>{file_type}</code>",
        message.chat.id,
        msg.message_id
    )

    bot.send_message(message.chat.id, RECEIVED_FILE_MSG.format(file_name=file_name))

@bot.message_handler(func=lambda m: m.chat.id in user_files)
def rename_file(message):
    new_name = message.text.strip()
    if '.' not in new_name or new_name.startswith('.'):
        bot.send_message(message.chat.id, INVALID_NAME_MSG)
        return

    # Sanitize filename
    new_name = re.sub(r'[\\/*?:"<>|]', "_", new_name)
    file_path = os.path.join(TEMP_DIR, new_name)

    bot.send_message(message.chat.id, WAIT_RENAME_MSG)

    file_data = user_files.pop(message.chat.id)

    try:
        with open(file_path, "wb") as f:
            f.write(file_data["data"])
    except Exception as e:
        bot.send_message(message.chat.id, f"<b>Error writing file:</b> {str(e)}")
        return

    status_msg = bot.send_message(message.chat.id, UPLOAD_PROGRESS_MSG.format(percent=0))
    for percent in [15, 35, 55, 75, 100]:
        time.sleep(0.2)
        bot.edit_message_text(UPLOAD_PROGRESS_MSG.format(percent=percent), message.chat.id, status_msg.message_id)

    try:
        with open(file_path, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                visible_file_name=new_name,
                caption=DONE_RENAME_MSG.format(new_name=new_name)
            )
    except Exception as e:
        bot.send_message(message.chat.id, f"<b>Error sending file:</b> {str(e)}")
    finally:
        os.remove(file_path)

    bot.edit_message_text("<b>✅ File uploaded and sent!</b>", message.chat.id, status_msg.message_id)

# Optional: handle graceful shutdown
def cleanup(signal_num, frame):
    print("Shutting down cleanly...")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

bot.infinity_polling()