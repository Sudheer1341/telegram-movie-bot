import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from rapidfuzz import process

# ---------------- Firebase Setup ----------------
firebase_key = os.getenv("FIREBASE_KEY")  # Railway environment variable
cred_dict = json.loads(firebase_key)
cred = credentials.Certificate(cred_dict)

firebase_admin.initialize_app(cred)
db = firestore.client()
movies_ref = db.collection("movies")

# ---------------- Config ----------------
ADMIN_ID = 1623981166  # replace with your Telegram user ID

# ---------------- Load Movies ----------------
def get_all_movies():
    docs = movies_ref.stream()
    movies = {}
    for doc in docs:
        movies[doc.id.lower()] = doc.to_dict()
    return movies

# ---------------- Bot Commands ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send me a movie name and I'll find it for you!")

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 You are not allowed to add movies.")

    try:
        text = " ".join(context.args)
        name, links = text.split("|")
        links_parts = links.split(",")
        movie_data = {}
        for part in links_parts:
            quality, link = part.split("=")
            movie_data[quality.strip()] = link.strip()

        movies_ref.document(name.strip().lower()).set(movie_data)
        await update.message.reply_text(f"✅ Added {name.strip()} to database!")
    except Exception as e:
        await update.message.reply_text("⚠️ Usage: /add movie_name | 720p=link, 1080p=link")

# ---------------- Movie Search ----------------
async def movie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower().strip()
    movies_db = get_all_movies()

    # Exact match
    if query in movies_db:
        await send_movie_links(update, movies_db[query], query)
        return

    # Fuzzy match
    choices = list(movies_db.keys())
    matches = process.extract(query, choices, limit=3, score_cutoff=60)

    if not matches:
        return await update.message.reply_text("❌ Sorry, movie not available.")

    # If 1 close match → ask yes/no
    if len(matches) == 1:
        best_match = matches[0][0]
        context.user_data["pending_movie"] = best_match
        await update.message.reply_text(f"❓ Did you mean *{best_match.title()}*? (yes/no)", parse_mode="Markdown")
    else:
        # Multiple matches → ask user to pick
        options_text = "I found similar movies:\n"
        for i, (name, score, _) in enumerate(matches, start=1):
            options_text += f"{i}. {name.title()}\n"
        context.user_data["options"] = [m[0] for m in matches]
        await update.message.reply_text(options_text + "\nReply with 1, 2, or 3.")

# ---------------- Helper to send movie links ----------------
async def send_movie_links(update: Update, movie_links, name):
    reply_text = f"✅ Found *{name.title()}*:\n\n"
    for quality, link in movie_links.items():
        reply_text += f"🔹 {quality}: {link}\n"
    await update.message.reply_text(reply_text, parse_mode="Markdown")

# ---------------- Handle Yes/No or Option ----------------
async def response_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()

    # Yes/No for single suggestion
    if "pending_movie" in context.user_data:
        movie_name = context.user_data.pop("pending_movie")
        if text in ["yes", "yeah", "y"]:
            movies_db = get_all_movies()
            await send_movie_links(update, movies_db[movie_name], movie_name)
        else:
            await update.message.reply_text("❌ Okay, not found.")
        return

    # Number choice for multiple matches
    if "options" in context.user_data and text.isdigit():
        choice_index = int(text) - 1
        options = context.user_data.pop("options")
        if 0 <= choice_index < len(options):
            selected_movie = options[choice_index]
            movies_db = get_all_movies()
            await send_movie_links(update, movies_db[selected_movie], selected_movie)
        else:
            await update.message.reply_text("⚠️ Invalid choice.")
        return

# ---------------- Main ----------------
def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_movie))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, response_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
