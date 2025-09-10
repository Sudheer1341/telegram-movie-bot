import os
import json
import difflib
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------ Load Movies ------------------
def load_movies():
    if os.path.exists("movies.json"):
        with open("movies.json", "r") as f:
            return json.load(f)
    return {}

movies_db = load_movies()

# ------------------ Helpers ------------------
def save_movies():
    with open("movies.json", "w") as f:
        json.dump(movies_db, f, indent=2)

def find_movie(query):
    """Fuzzy match search for movie names."""
    query = query.lower().strip()
    if query in movies_db:
        return query, None
    matches = difflib.get_close_matches(query, movies_db.keys(), n=3, cutoff=0.4)
    if matches:
        return None, matches
    return None, None

async def send_movie(update, movie_name, movie_links):
    """Send movie with inline buttons (qualities)."""
    keyboard = []
    for quality, link in movie_links.items():
        keyboard.append([InlineKeyboardButton(quality, url=link)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Found *{movie_name.title()}*:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ------------------ Commands ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send me a movie name and I'll find it for you!")

ADMIN_ID = 1623981166  # replace with your Telegram ID

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add movies."""
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /addmovie <name> <quality> <link>")
        return
    
    name, quality, link = context.args[0].lower(), context.args[1], context.args[2]
    if name not in movies_db:
        movies_db[name] = {}
    movies_db[name][quality] = link
    save_movies()
    
    await update.message.reply_text(f"✅ Added {name.title()} - {quality}")

async def request_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Users can request movies."""
    if not context.args:
        await update.message.reply_text("Usage: /request <movie name>")
        return
    
    movie_name = " ".join(context.args)
    
    requests = []
    if os.path.exists("requests.json"):
        with open("requests.json", "r") as f:
            requests = json.load(f)
    requests.append({"user": update.message.from_user.username, "movie": movie_name})
    with open("requests.json", "w") as f:
        json.dump(requests, f, indent=2)
    
    await update.message.reply_text(f"📩 Your request for *{movie_name}* has been noted.", parse_mode="Markdown")

# ------------------ Movie Handler ------------------
async def movie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower().strip()
    
    # Exact or fuzzy search
    exact, suggestions = find_movie(query)
    if exact:
        await send_movie(update, exact, movies_db[exact])
    elif suggestions:
        await update.message.reply_text(
            "❓ Did you mean:\n" + "\n".join([f"🔹 {s}" for s in suggestions])
        )
    else:
        await update.message.reply_text("❌ Sorry, movie not available. Use /request to ask for it.")

# ------------------ Main ------------------
def main():
    token = os.getenv("BOT_TOKEN")  # Railway environment variable
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CommandHandler("request", request_movie))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
