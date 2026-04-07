import os
import tempfile
from fastapi import FastAPI, Request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from groq import Groq

# Environment variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # set your Telegram user ID in Render

# FastAPI app
app = FastAPI()

# Telegram bot application
bot_app = Application.builder().token(TOKEN).build()

# Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Short-term memory storage (per user)
user_memory = {}   # {user_id: [ {role, content}, ... ] }
MAX_MEMORY = 10

# Blocked users (in-memory)
blocked_users = set()


# -----------------------------
# Helper: memory
# -----------------------------
def remember(user_id, role, content):
    if user_id not in user_memory:
        user_memory[user_id] = []
    user_memory[user_id].append({"role": role, "content": content})
    if len(user_memory[user_id]) > MAX_MEMORY:
        user_memory[user_id] = user_memory[user_id][-MAX_MEMORY:]


def is_blocked(user_id: int) -> bool:
    return user_id in blocked_users


def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID


# -----------------------------
# /start
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Help", callback_data="help"),
            InlineKeyboardButton("Translate", callback_data="quick_translate"),
        ],
        [
            InlineKeyboardButton("Summarize", callback_data="quick_summarize"),
            InlineKeyboardButton("Image", callback_data="quick_image"),
        ],
    ]
    await update.message.reply_text(
        "Hi! I’m your AI assistant. Use /help to see what I can do.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# -----------------------------
# /help
# -----------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Here are my commands:\n\n"
        "/help - Show this help message\n"
        "/translate <text> - Translate text to English\n"
        "/summarize <text> - Summarize long text\n"
        "/image <prompt> - Generate an image (URL) from a prompt\n"
        "/admin - Admin panel (only for admin)\n\n"
        "You can also send voice messages, and I’ll transcribe + answer.\n"
        "Just chat normally and I will respond with AI."
    )
    await update.message.reply_text(text)


# -----------------------------
# /translate
# -----------------------------
async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    await update.message.reply_chat_action("typing")

    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("Usage: /translate <text>")

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Translate the text to English."},
            {"role": "user", "content": text},
        ],
    )

    answer = response.choices[0].message.content
    await update.message.reply_text(answer)


# -----------------------------
# /summarize
# -----------------------------
async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    await update.message.reply_chat_action("typing")

    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("Usage: /summarize <text>")

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Summarize the text concisely."},
            {"role": "user", "content": text},
        ],
    )

    answer = response.choices[0].message.content
    await update.message.reply_text(answer)


# -----------------------------
# /image – real image via URL
# -----------------------------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    await update.message.reply_chat_action("upload_photo")

    prompt = " ".join(context.args)
    if not prompt:
        return await update.message.reply_text("Usage: /image <prompt>")

    # Use Groq to refine the prompt (optional)
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": "Rewrite the prompt as a detailed image generation prompt.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    refined = response.choices[0].message.content

    # Simple example: use a placeholder image service with the prompt in caption
    image_url = "https://picsum.photos/512"  # placeholder real image
    caption = f"🖼️ Image for: {prompt}\n\nPrompt detail:\n{refined}"

    await update.message.reply_photo(photo=image_url, caption=caption)


# -----------------------------
# Voice handler – Whisper STT + AI reply
# -----------------------------
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    await update.message.reply_chat_action("typing")

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    file = await voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        file_path = tmp.name
        await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as f:
            transcription = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("audio.ogg", f),
                response_format="text",
            )

        text = transcription  # already plain text
        await update.message.reply_text(f"🗣 Transcribed: {text}")

        # Use same AI chat flow with memory
        remember(user_id, "user", text)
        messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
        messages.extend(user_memory.get(user_id, []))

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
        )
        answer = response.choices[0].message.content
        remember(user_id, "assistant", answer)

        await update.message.reply_text(answer)

    except Exception as e:
        print("GROQ VOICE ERROR:", e)
        await update.message.reply_text("Sorry, something went wrong with voice processing.")


# -----------------------------
# AI chat with memory
# -----------------------------
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    user_text = update.message.text
    await update.message.reply_chat_action("typing")

    remember(user_id, "user", user_text)
    messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
    messages.extend(user_memory.get(user_id, []))

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
        )

        answer = response.choices[0].message.content
        remember(user_id, "assistant", answer)

        await update.message.reply_text(answer)

    except Exception as e:
        print("GROQ ERROR:", e)
        await update.message.reply_text("Sorry, something went wrong with the AI service.")


# -----------------------------
# Admin: /admin, /block, /unblock
# -----------------------------
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        return await update.message.reply_text("You are not admin.")

    keyboard = [
        [InlineKeyboardButton("List blocked users", callback_data="admin_list_blocked")],
    ]
    text = (
        "👑 Admin Panel\n\n"
        f"Total users with memory: {len(user_memory)}\n"
        f"Blocked users: {len(blocked_users)}\n\n"
        "Commands:\n"
        "/block <user_id>\n"
        "/unblock <user_id>\n"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        return await update.message.reply_text("Usage: /block <user_id>")

    try:
        target_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("User ID must be a number.")

    blocked_users.add(target_id)
    await update.message.reply_text(f"User {target_id} blocked.")


async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        return await update.message.reply_text("Usage: /unblock <user_id>")

    try:
        target_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("User ID must be a number.")

    blocked_users.discard(target_id)
    await update.message.reply_text(f"User {target_id} unblocked.")


# -----------------------------
# Callback queries (inline buttons)
# -----------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "help":
        return await help_cmd(update, context)

    if query.data == "quick_translate":
        await query.edit_message_text("Use /translate <text> to translate to English.")
    elif query.data == "quick_summarize":
        await query.edit_message_text("Use /summarize <text> to summarize content.")
    elif query.data == "quick_image":
        await query.edit_message_text("Use /image <prompt> to generate an image URL.")
    elif query.data == "admin_list_blocked":
        if not is_admin(user_id):
            return
        if not blocked_users:
            text = "No blocked users."
        else:
            text = "Blocked users:\n" + "\n".join(str(u) for u in blocked_users)
        await query.edit_message_text(text)


# -----------------------------
# Register handlers
# -----------------------------
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_cmd))
bot_app.add_handler(CommandHandler("translate", translate))
bot_app.add_handler(CommandHandler("summarize", summarize))
bot_app.add_handler(CommandHandler("image", image))
bot_app.add_handler(CommandHandler("admin", admin_cmd))
bot_app.add_handler(CommandHandler("block", block_cmd))
bot_app.add_handler(CommandHandler("unblock", unblock_cmd))
bot_app.add_handler(CallbackQueryHandler(button_handler))
bot_app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_reply))


# -----------------------------
# Webhook endpoint
# -----------------------------
@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


# -----------------------------
# Startup
# -----------------------------
@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
