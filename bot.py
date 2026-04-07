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


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! I’m your AI assistant. Ask me anything.")


bot_app.add_handler(CommandHandler("start", start))


# AI assistant handler
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",   # ✅ Correct model name
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": user_text},
            ],
        )

        answer = response.choices[0].message["content"]
        await update.message.reply_text(answer)

    except Exception as e:
        print("GROQ ERROR:", e)  # Logs the real error in Render
        await update.message.reply_text("Sorry, something went wrong with the AI service.")


bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_reply))


# Webhook endpoint
@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


# Startup: initialize bot + set webhook
@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
