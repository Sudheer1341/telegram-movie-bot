import os
import difflib
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient

# ------------------ MongoDB Setup ------------------
client = MongoClient(os.getenv("MONGO_URI"))  # Railway env var
db = client["moviesdb"]
movies_collection = db["movies"]
requests_collection = db["requests"]

# ------------------ DB Helpers ------------------
def get_movie(name: str):
    return movies_collection.find_one({"name": name.lower()})

def add_movie_db(name: str, quality: str, link: str):
    movies_collection.update_one(
        {"name": name.lower()},
        {"$set": {f"links.{quality}": link}},
        upsert=True
    )

def get_all_movies():
    return list(movies_collection.find())

def add_request(user: str, movie_name: str):
    requests_collection.insert_one({"user": user, "movie": movie_name})

def get_requests():
    return list(requests_collection.find())

# ------------------ Utils ------------------
def find_movie(query: str):
    """Fuzzy match search for movie names from DB."""
    query = query.lower().strip()
    movie = get_movie(query)
    if movie:
        return movie, None
    
    # Fuzzy match with all movie names
    all_movies = [m["name"] for m in get_all_movies()]
    matches = difflib.get_close_matches(query, all_movies, n=3, cutoff=0.4)
    if matches:
        return None, matches
    return None, None

async def send_movie(update, movie):
    """Send movie with inline buttons for qualities."""
    keyboard = []
    for quality, link in movie["links"].items():
        keyboard.append([InlineKeyboardButton(quality, url=link)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Found *{movie['name'].title()}*:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ------------------ Commands ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send me a movie name and I'll find it for you!")

ADMIN_ID = 1623981166  # replace with your Telegram ID

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /addmovie <name> <quality> <link>")
        return
    
    name, quality, link = context.args[0].lower(), context.args[1], context.args[2]
    add_movie_db(name, quality, link)
    await update.message.reply_text(f"✅ Added {name.title()} - {quality}")

async def request_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /request <movie name>")
        return
    
    movie_name = " ".join(context.args)
    add_request(update.message.from_user.username or "Unknown", movie_name)
    await update.message.reply_text(
        f"📩 Your request for *{movie_name}* has been noted.",
        parse_mode="Markdown"
    )

async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Only admin can use this command.")
        return

    requests = get_requests()
    if not requests:
        await update.message.reply_text("📂 No movie requests yet.")
    else:
        text = "📋 *Requested Movies:*\n\n"
        for r in requests:
            text += f"👤 {r['user']} → 🎬 {r['movie']}\n"
        await update.message.reply_text(text, parse_mode="Markdown")

# ------------------ Movie Handler ------------------
async def movie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower().strip()
    movie, suggestions = find_movie(query)

    if movie:
        await send_movie(update, movie)
    elif suggestions:
        await update.message.reply_text(
            "❓ Did you mean:\n" + "\n".join([f"🔹 {s}" for s in suggestions])
        )
    else:
        await update.message.reply_text(
            "❌ Sorry, movie not available. Use /request to ask for it."
        )

# ------------------ Main ------------------
def main():
    token = os.getenv("BOT_TOKEN")  # Railway env var
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CommandHandler("request", request_movie))
    app.add_handler(CommandHandler("showrequests", show_requests))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
