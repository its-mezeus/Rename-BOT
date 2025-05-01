import os
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Bot token and other configurations
API_TOKEN = '6030851492:AAFCx-U9U6YF0erojkKYk0ieUGulV_IexpA'
FORCE_JOIN_CHANNEL = 'botsproupdates'  # username only, no @
ADMIN_IDS = [1694669957]

# Initialize the Pyrogram client with just the Bot Token (no need for API ID and API Hash)
app = Client("file_rename_bot", bot_token=API_TOKEN)

# Force join check
async def is_user_joined(user_id):
    try:
        member = await app.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# Start command
@app.on_message(filters.command('start'))
async def start_msg(client, message):
    user_id = message.from_user.id
    if not await is_user_joined(user_id):
        markup = InlineKeyboardMarkup()
        join_btn = InlineKeyboardButton("JOIN CHANNEL 🤍", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        markup.add(join_btn)
        await message.reply(
            "**You need to join our channel to use this bot. Please join the channel first 🥇**\n\n"
            "**After joining, press /start again to continue using the bot ✨**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    name = message.from_user.first_name
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("**BOT UPDATES**", url="https://t.me/botsproupdates"),
        InlineKeyboardButton("**OWNER**", url="https://t.me/zeus_is_here")
    )
    await message.reply(
        f"**Hello {name} 👋🏻**\n\n"
        "**I am a Simple File Rename Bot 📂**\n"
        "**Just Send a File and See the magic ✨**\n\n"
        "**Thanks for Using Our Bot 😄💓**",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# Help command
@app.on_message(filters.command('help'))
async def help_cmd(client, message):
    await message.reply(
        "**Bot Commands:**\n"
        "`/start` - Show the welcome message\n"
        "`/help` - Show this help message\n\n"
        "**How to Use:**\n"
        "1. **Join the updates channel**\n"
        "2. **Send me any document/file**\n"
        "3. **It will be renamed and sent back**\n\n"
        "**Enjoy the bot!**",
        parse_mode="Markdown"
    )

# Handle file messages
@app.on_message(filters.document)
async def handle_file(client, message):
    user_id = message.from_user.id
    if not await is_user_joined(user_id):
        markup = InlineKeyboardMarkup()
        join_btn = InlineKeyboardButton("JOIN CHANNEL 🤍", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")
        markup.add(join_btn)
        await message.reply(
            "**You need to join our channel to use this bot. Please join the channel first 🥇**\n\n"
            "**After joining, press /start again to continue using the bot ✨**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    # Download the file
    file_info = await message.download()
    original_filename = message.document.file_name
    file_ext = os.path.splitext(original_filename)[1]

    # Rename the file
    new_filename = f"renamed_{user_id}{file_ext}"

    # Sending animated responses
    msg = await message.reply("**Receiving your file... 📨**", parse_mode="Markdown")
    await msg.edit("**Renaming your file... 🔄**")
    await msg.edit("**Uploading your file... ⏫**")

    # Send the renamed file back
    await app.send_document(
        chat_id=message.chat.id,
        document=file_info,
        caption="**Here is your renamed file! ✨**",
        parse_mode="Markdown"
    )

    await msg.delete()
    await message.reply("**THANKS FOR USING THIS BOT 💓**", parse_mode="Markdown")

    # Clean up the downloaded file
    os.remove(file_info)

# Run the bot
app.run()
