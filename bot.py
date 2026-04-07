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
ADMIN_ID = 5766538286  # Your admin ID

# FastAPI app
app = FastAPI()

# Telegram bot application
bot_app = Application.builder().token(TOKEN).build()

# Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Short-term memory storage (per user)
user_memory = {}   # {user_id: [ {role, content}, ... ] }
user_language = {} # {user_id: "en"}
MAX_MEMORY = 10

# Blocked users
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
    return user_id == ADMIN_ID


# -----------------------------
# Language detection
# -----------------------------
def detect_language(text: str) -> str:
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "Detect the language of the text. Respond ONLY with ISO code (en, ar, es, ru, ja, zh, fr, de, etc)."
                },
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content.strip().lower()
    except:
        return "en"


# -----------------------------
# Smart Mode Language Logic
# -----------------------------
def update_user_language(user_id: int, text: str):
    lang = detect_language(text)

    # If user has no language yet → set it
    if user_id not in user_language:
        user_language[user_id] = lang
        return

    # Smart Mode:
    # If message is long enough → switch language
    if len(text.split()) > 2:
        user_language[user_id] = lang


# -----------------------------
# Translate bot replies
# -----------------------------
def translate_text(text: str, target_lang: str) -> str:
    if target_lang == "en":
        return text

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": f"Translate the following text into {target_lang}. Keep meaning exactly the same."
                },
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content
    except:
        return text


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
        "/image <prompt> - Generate a real image from Unsplash\n"
        "/admin - Admin panel (only for admin)\n\n"
        "You can also send voice messages — I will transcribe and reply.\n"
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
# /image – real images from Unsplash
# -----------------------------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    await update.message.reply_chat_action("upload_photo")

    prompt = " ".join(context.args)
    if not prompt:
        return await update.message.reply_text("Usage: /image <prompt>")

    try:
        # Improve prompt using Groq
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Rewrite the prompt as a detailed image description."},
                {"role": "user", "content": prompt},
            ],
        )
        refined = response.choices[0].message.content

        # REAL IMAGE (Unsplash)
        image_url = f"https://source.unsplash.com/featured/512x512/?{prompt}"

        caption = f"🖼️ Image for: {prompt}\n\nPrompt detail:\n{refined}"

        await update.message.reply_photo(photo=image_url, caption=caption)

    except Exception as e:
        print("IMAGE ERROR:", e)
        await update.message.reply_text("Image generation failed.")


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

        text = transcription
        await update.message.reply_text(f"🗣 Transcribed: {text}")

        # Update language preference
        update_user_language(user_id, text)

        # Build conversation
        remember(user_id, "user", text)
        messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
        messages.extend(user_memory.get(user_id, []))

        # AI reply
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
        )
        answer = response.choices[0].message.content

        # Translate AI reply
        target_lang = user_language.get(user_id, "en")
        translated = translate_text(answer, target_lang)

        remember(user_id, "assistant", translated)

        await update.message.reply_text(translated)

    except Exception as e:
        print("GROQ VOICE ERROR:", e)
        await update.message.reply_text("Sorry, something went wrong with voice processing.")


# -----------------------------
# AI chat with memory + language detection
# -----------------------------
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_blocked(user_id):
        return

    user_text = update.message.text
    await update.message.reply_chat_action("typing")

    # Update language preference
    update_user_language(user_id, user_text)

    # Build conversation
    remember(user_id, "user", user_text)
    messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
    messages.extend(user_memory.get(user_id, []))

    try:
        # AI reply
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
        )

        answer = response.choices[0].message.content

        # Translate AI reply
        target_lang = user_language.get(user_id, "en")
        translated = translate_text(answer, target_lang)

        remember(user_id, "assistant", translated)

        await update.message.reply_text(translated)

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
        await query.edit_message_text("Use /image <prompt> to generate an image.")
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
