import os
import json
import firebase_admin
from thefuzz import process
from firebase_admin import credentials, db
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------ CONFIG ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Railway env variable
ADMIN_ID = 1623981166  # 🔹 Replace with your Telegram numeric ID

# Firebase setup
if os.getenv("FIREBASE_KEY"):  # Railway env variable
    firebase_key = json.loads(os.getenv("FIREBASE_KEY"))
    cred = credentials.Certificate(firebase_key)
else:  # local file
    cred = credentials.Certificate("firebase_key.json")

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://moviebotdb-28e2b-default-rtdb.firebaseio.com/'  # 🔹 Replace with your DB URL
})

# ------------------ STATE ------------------
pending_requests = {}  # {user_id: {"matches": [...]}}

# ------------------ HELPERS ------------------
async def send_movie(update, movie_name, movie_links):
    """Send movie links as inline buttons."""
    keyboard = [
        [InlineKeyboardButton(quality, url=link)]
        for quality, link in movie_links.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Found *{movie_name.title()}*:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ------------------ COMMANDS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send me a movie name and I'll find it for you!")

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add movies."""
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /addmovie <name> <quality> <link>")
        return
    
    name, quality, link = context.args[0].lower(), context.args[1], context.args[2]
    ref = db.reference(f"movies/{name}")
    ref.update({quality: link})
    
    await update.message.reply_text(f"✅ Added {name.title()} - {quality}")

async def request_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Users can request unavailable movies."""
    if not context.args:
        await update.message.reply_text("Usage: /request <movie name>")
        return
    
    movie_name = " ".join(context.args)
    ref = db.reference("requests")
    ref.push({
        "user": update.message.from_user.username or "Unknown",
        "movie": movie_name
    })
    
    await update.message.reply_text(f"📩 Your request for *{movie_name}* has been noted.", parse_mode="Markdown")

async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view all requests."""
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Only admin can use this command.")
        return
    
    ref = db.reference("requests")
    requests = ref.get() or {}
    
    if not requests:
        await update.message.reply_text("📂 No movie requests yet.")
        return
    
    text = "📋 *Requested Movies:*\n\n"
    for r in requests.values():
        text += f"👤 {r['user']} → 🎬 {r['movie']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ------------------ MOVIE HANDLER ------------------
async def movie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    query = update.message.text.lower().strip()

    ref = db.reference("movies")
    movies_db = ref.get() or {}

    # 🔹 Check if user is confirming a suggestion
    if user_id in pending_requests:
        matches = pending_requests[user_id]["matches"]

        if query in ["yes", "yeah", "y"]:  # single match confirmed
            best_match = matches[0]
            await send_movie(update, best_match, movies_db[best_match])
            del pending_requests[user_id]
            return

        elif query.isdigit() and 1 <= int(query) <= len(matches):  # user picks a number
            chosen = matches[int(query) - 1]
            await send_movie(update, chosen, movies_db[chosen])
            del pending_requests[user_id]
            return

        else:
            await update.message.reply_text("⚠️ Please reply with 'yes' or a number from the list.")
            return

    # 🔹 Exact match
    if query in movies_db:
        await send_movie(update, query, movies_db[query])
    else:
        # 🔹 Fuzzy search for close matches
        matches = process.extract(query, movies_db.keys(), limit=3)
        good_matches = [m[0] for m in matches if m[1] >= 60]  # threshold 60

        if not good_matches:
            await update.message.reply_text("❌ Sorry, movie not available. Use /request to ask for it.")
        elif len(good_matches) == 1:
            pending_requests[user_id] = {"matches": good_matches}
            await update.message.reply_text(f"❓ Did you mean *{good_matches[0].title()}*? (yes/no)", parse_mode="Markdown")
        else:
            pending_requests[user_id] = {"matches": good_matches}
            reply_text = "❓ Did you mean:\n\n"
            for i, title in enumerate(good_matches, 1):
                reply_text += f"{i}. {title.title()}\n"
            reply_text += "\n👉 Reply with a number."
            await update.message.reply_text(reply_text)

# ------------------ MAIN ------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CommandHandler("request", request_movie))
    app.add_handler(CommandHandler("showrequests", show_requests))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
