import os
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load movies database from movies.json
def load_movies():
    with open("movies.json", "r") as f:
        return json.load(f)

movies_db = load_movies()

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Create a numbered movie list
    movie_list = "\n".join([f"{i+1}. {m.title()}" for i, m in enumerate(movies_db.keys())])

    welcome_text = (
        "🍿 Hey there! Welcome to *CineHD Vault Bot* 🎬\n\n"
        "👉 Just send me the name of a movie, and I’ll get it for you in different qualities.\n\n"
        "🎥 Currently available movies:\n"
        f"{movie_list}\n\n"
        "✨ More movies will be added soon, so stay tuned!"
    )

    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# /movies command
async def movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_list = "\n".join([f"{i+1}. {m.title()}" for i, m in enumerate(movies_db.keys())])
    await update.message.reply_text(f"🎥 Available Movies:\n\n{movie_list}")

# Handle movie requests
async def movie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower().strip()
    
    if query in movies_db:
        movie_links = movies_db[query]
        reply_text = f"✅ Found *{query.title()}*:\n\n"
        for quality, link in movie_links.items():
            reply_text += f"🔹 {quality}: {link}\n"
        await update.message.reply_text(reply_text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Sorry, movie not available.")

def main():
    token = os.getenv("BOT_TOKEN")  # Get token from Render environment
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("movies", movies))  # new command
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
