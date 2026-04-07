import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# Example command
async def start(update: Update, context):
    await update.message.reply_text("Bot is running via webhook!")

bot_app.add_handler(CommandHandler("start", start))

# Example message handler
async def echo(update: Update, context):
    await update.message.reply_text(update.message.text)

bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def startup():
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
