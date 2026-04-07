import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from groq import Groq

# Environment variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# FastAPI app
app = FastAPI()

# Telegram bot application
bot_app = Application.builder().token(TOKEN).build()

# Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Short-term memory storage (per user)
user_memory = {}  # {user_id: [ {role, content}, ... ] }
MAX_MEMORY = 10   # last 10 messages


# -----------------------------
# Helper: Add message to memory
# -----------------------------
def remember(user_id, role, content):
    if user_id not in user_memory:
        user_memory[user_id] = []
    user_memory[user_id].append({"role": role, "content": content})

    # Keep only last 10 messages
    if len(user_memory[user_id]) > MAX_MEMORY:
        user_memory[user_id] = user_memory[user_id][-MAX_MEMORY:]


# -----------------------------
# /start command
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! I’m your AI assistant. Ask me anything.")


# -----------------------------
# /help command
# -----------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Here are my commands:\n\n"
        "/help - Show this help message\n"
        "/translate <text> - Translate text to English\n"
        "/summarize <text> - Summarize long text\n"
        "/image <prompt> - Generate an image description\n"
        "\nJust chat normally and I will respond with AI."
    )
    await update.message.reply_text(text)


# -----------------------------
# /translate command
# -----------------------------
async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
# /summarize command
# -----------------------------
async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
# /image command (text description)
# -----------------------------
async def image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action("typing")

    prompt = " ".join(context.args)
    if not prompt:
        return await update.message.reply_text("Usage: /image <prompt>")

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Describe an image based on the prompt."},
            {"role": "user", "content": prompt},
        ],
    )

    answer = response.choices[0].message.content
    await update.message.reply_text("🖼️ *Image Description:*\n" + answer)


# -----------------------------
# AI Chat Handler (with memory)
# -----------------------------
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_text = update.message.text

    # Typing indicator
    await update.message.reply_chat_action("typing")

    # Save user message
    remember(user_id, "user", user_text)

    # Build conversation history
    messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
    messages.extend(user_memory.get(user_id, []))

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
        )

        answer = response.choices[0].message.content

        # Save assistant reply
        remember(user_id, "assistant", answer)

        await update.message.reply_text(answer)

    except Exception as e:
        print("GROQ ERROR:", e)
        await update.message.reply_text("Sorry, something went wrong with the AI service.")


# Register handlers
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_cmd))
bot_app.add_handler(CommandHandler("translate", translate))
bot_app.add_handler(CommandHandler("summarize", summarize))
bot_app.add_handler(CommandHandler("image", image))
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
# Startup: initialize bot + webhook
# -----------------------------
@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
