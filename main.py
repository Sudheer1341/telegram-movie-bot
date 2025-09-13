# COPY-PASTE THIS WHOLE FILE (replace your main.py)
import os
import json
import firebase_admin
from thefuzz import process
from firebase_admin import credentials, db
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------ CONFIG ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1623981166  # <-- replace with your Telegram numeric ID if different

# Firebase init (either env var FIREBASE_KEY or file 'firebase_key.json')
if os.getenv("FIREBASE_KEY"):
    firebase_key = json.loads(os.getenv("FIREBASE_KEY"))
    cred = credentials.Certificate(firebase_key)
else:
    cred = credentials.Certificate("firebase_key.json")

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://moviebotdb-28e2b-default-rtdb.firebaseio.com/'  # <-- change to your DB URL
})

# ------------------ STATE ------------------
pending_requests = {}     # fuzzy-search confirmations for users: {user_id: {"matches": [...]}}
pending_admin_files = {}  # admin file metadata flow: {admin_id: file_id}

# ------------------ HELPERS ------------------
async def send_movie(update: Update, movie_name: str, movie_links: dict):
    """
    Sends a movie to the user. Supports:
      - Telegram file_id values (non-http strings) -> sent as documents
      - External URLs (starting with http/https) -> shown as inline buttons
    """
    # Separate file_ids vs links
    file_items = {}
    link_items = {}
    for quality, value in (movie_links or {}).items():
        if not isinstance(value, str):
            # If DB stored dicts (future-proof), handle common shapes:
            # { "type":"file", "id":"<file_id>" } OR { "type":"link", "url":"..." }
            if isinstance(value, dict):
                if value.get("type") == "file" and value.get("id"):
                    file_items[quality] = value["id"]
                elif value.get("type") == "link" and value.get("url"):
                    link_items[quality] = value["url"]
            continue
        v = value.strip()
        if v.startswith("http://") or v.startswith("https://"):
            link_items[quality] = v
        else:
            # assume it's a Telegram file_id
            file_items[quality] = v

    # First send any file-type qualities (these are actual Telegram files)
    if file_items:
        for quality, file_id in file_items.items():
            try:
                # send as document (works for large files); include caption
                await update.message.reply_document(document=file_id, caption=f"{movie_name.title()} - {quality}")
            except Exception as e:
                # fallback to telling user it's available
                await update.message.reply_text(f"Could not send file {quality}. (Error: {e})")

    # Then offer link-type qualities as inline buttons
    if link_items:
        keyboard = [[InlineKeyboardButton(q, url=url)] for q, url in link_items.items()]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"✅ Found *{movie_name.title()}* (external links available):",
                                        parse_mode="Markdown", reply_markup=reply_markup)

# ------------------ COMMANDS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send me a movie name and I'll find it for you!\n\nAdmin: send a file (with caption name|quality) or forward channel file to me.")

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /addmovie <name> <quality> <link_or_fileid>")
        return
    name, quality, link = context.args[0].lower(), context.args[1], context.args[2]
    ref = db.reference(f"movies/{name}")
    ref.update({quality: link})
    await update.message.reply_text(f"✅ Added {name.title()} - {quality}")

async def request_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /request <movie name>")
        return
    movie_name = " ".join(context.args)
    ref = db.reference("requests")
    ref.push({"user": update.message.from_user.username or "Unknown", "movie": movie_name})
    await update.message.reply_text(f"📩 Your request for *{movie_name}* has been noted.", parse_mode="Markdown")

async def show_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ------------------ MESSAGE ROUTER (ALL non-command messages) ------------------
async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Single router that:
      - captures admin file uploads / forwards and stores file_id
      - handles admin reply to complete metadata
      - handles user's fuzzy-confirm flow and movie searches
    """
    message = update.message
    if not message:
        return

    user_id = message.from_user.id

    # 1) If message contains a file (document/video) and sender is ADMIN -> capture file
    file_obj = None
    if message.document:
        file_obj = message.document
    elif message.video:
        file_obj = message.video
    elif message.audio:
        file_obj = message.audio
    elif message.voice:
        file_obj = message.voice

    if file_obj:
        # Accept only admin uploads (security)
        if user_id != ADMIN_ID:
            await message.reply_text("🚫 Only admin can upload files that will be stored as Telegram file IDs.")
            return

        file_id = file_obj.file_id
        caption = (message.caption or "").strip()
        if "|" in caption:
            # direct save using caption format: name|quality
            name, quality = [s.strip().lower() for s in caption.split("|", 1)]
            db.reference(f"movies/{name}").update({quality: file_id})
            await message.reply_text(f"✅ Saved *{name.title()}* - {quality} (as Telegram file).", parse_mode="Markdown")
        else:
            # request metadata: store file temporarily and ask admin to reply with name|quality
            pending_admin_files[user_id] = file_id
            await message.reply_text("File received. Now reply with movie name and quality in format: `name|quality`", parse_mode="Markdown")
        return

    # 2) If admin has a pending file waiting for metadata, accept the next text as name|quality
    if user_id in pending_admin_files and message.text:
        text = message.text.strip()
        if "|" not in text:
            await message.reply_text("Please send in format: name|quality (e.g., inception|720p)")
            return
        name, quality = [s.strip().lower() for s in text.split("|", 1)]
        file_id = pending_admin_files.pop(user_id)
        db.reference(f"movies/{name}").update({quality: file_id})
        await message.reply_text(f"✅ Saved *{name.title()}* - {quality} (file_id stored).", parse_mode="Markdown")
        return

    # 3) If user is answering a fuzzy-confirmation (yes/1/2/etc.)
    if user_id in pending_requests and message.text:
        matches = pending_requests[user_id]["matches"]
        txt = message.text.lower().strip()
        if txt in ["yes", "y", "yeah", "correct"]:
            best = matches[0]
            movie_links = db.reference(f"movies/{best}").get() or {}
            await send_movie(update, best, movie_links)
            del pending_requests[user_id]
            return
        elif txt.isdigit():
            idx = int(txt) - 1
            if 0 <= idx < len(matches):
                chosen = matches[idx]
                movie_links = db.reference(f"movies/{chosen}").get() or {}
                await send_movie(update, chosen, movie_links)
                del pending_requests[user_id]
                return
            else:
                await message.reply_text("⚠️ Number out of range — reply with the option number from the list.")
                return
        else:
            await message.reply_text("⚠️ Please reply with 'yes' or a number from the list.")
            return

    # 4) Otherwise: treat as a movie search (text)
    if message.text:
        query = message.text.lower().strip()
        movies_db = db.reference("movies").get() or {}

        # exact match
        if query in movies_db:
            await send_movie(update, query, movies_db[query])
            return

        # fuzzy suggestions
        matches = process.extract(query, list(movies_db.keys()), limit=3)
        good_matches = [m[0] for m in matches if m[1] >= 60]  # threshold, tweak if needed

        if not good_matches:
            await message.reply_text("❌ Sorry, movie not available. Use /request to ask for it.")
        elif len(good_matches) == 1:
            pending_requests[user_id] = {"matches": good_matches}
            await message.reply_text(f"❓ Did you mean *{good_matches[0].title()}*? (yes/no)", parse_mode="Markdown")
        else:
            pending_requests[user_id] = {"matches": good_matches}
            reply_text = "❓ Did you mean:\n\n"
            for i, title in enumerate(good_matches, 1):
                reply_text += f"{i}. {title.title()}\n"
            reply_text += "\n👉 Reply with a number."
            await message.reply_text(reply_text)

# ------------------ MAIN ------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CommandHandler("request", request_movie))
    app.add_handler(CommandHandler("showrequests", show_requests))

    # All non-command messages go to message_router (captures files, admin flows, searches)
    app.add_handler(MessageHandler(~filters.COMMAND, message_router))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
