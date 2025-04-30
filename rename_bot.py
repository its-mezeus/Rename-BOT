from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, CallbackContext
)

ALLOWED_USERS = set()
ADMIN_ID = 1694669957

FILE, NEW_NAME = range(2)

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS and user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    keyboard = [
        [InlineKeyboardButton("BOT UPDATES", url="https://t.me/botsproupdates")],
        [InlineKeyboardButton("OWNER", callback_data="owner")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Hello! I'm a File Rename Bot.\n\nSend me any file, and I'll help you rename it.",
        reply_markup=reply_markup
    )

async def owner_button(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("NO OWNER FOR THIS BOT 😅")

async def add_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if context.args:
        new_user_id = int(context.args[0])
        ALLOWED_USERS.add(new_user_id)
        await update.message.reply_text(f"User {new_user_id} has been added to the allowed list.")
    else:
        await update.message.reply_text("Please provide the user ID to add.")

async def remove_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if context.args:
        remove_user_id = int(context.args[0])
        if remove_user_id in ALLOWED_USERS:
            ALLOWED_USERS.remove(remove_user_id)
            await update.message.reply_text(f"User {remove_user_id} has been removed from the allowed list.")
        else:
            await update.message.reply_text("User ID not found in the allowed list.")
    else:
        await update.message.reply_text("Please provide the user ID to remove.")

async def list_users(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if ALLOWED_USERS:
        users_list = "\n".join([str(user) for user in ALLOWED_USERS])
        await update.message.reply_text(f"Allowed users:\n{users_list}")
    else:
        await update.message.reply_text("No users in the allowed list.")

async def handle_file(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS and user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    if update.message.document:
        context.user_data['file_id'] = update.message.document.file_id
        context.user_data['file_name'] = update.message.document.file_name
        await update.message.reply_text("Please send me the new name for the file (with extension).")
        return NEW_NAME

async def rename_file(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS and user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    new_name = update.message.text.strip()
    if not new_name:
        await update.message.reply_text("Invalid file name.")
        return NEW_NAME

    file = await context.bot.get_file(context.user_data['file_id'])
    await file.download_to_drive(new_name)

    with open(new_name, 'rb') as f:
        await update.message.reply_document(f, filename=new_name, caption="Thanks for using Bot!")

    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("File renaming cancelled.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token("6030851492:AAFCx-U9U6YF0erojkKYk0ieUGulV_IexpA").build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, handle_file)],
        states={
            NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_file)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("listusers", list_users))
    app.add_handler(CallbackQueryHandler(owner_button, pattern="^owner$"))
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == '__main__':
    main()
