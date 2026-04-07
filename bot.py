import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = FastAPI()

# Telegram application
bot_app = Application.builder().token(TOKEN).build()

# Groq client
groq_client = Groq(api_key=GROQ_API_KEY)


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! I’m an AI assistant. Ask me anything.")


bot_app.add_handler(CommandHandler("start", start))


# AI assistant handler
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "You are a helpful, friendly AI assistant."},
                {"role": "user", "content": user_text},
            ],
        )

        answer = response.choices[0].message["content"]
        await update.message.reply_text(answer)

    except Exception as e:
        await update.message.reply_text("Sorry, something went wrong with the AI service.")


bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_reply))


@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def startup():
    # Initialize telegram-application and set webhook
    await bot_app.initialize()
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
