import os
import sqlite3
import datetime
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
DB = "subscriptions.db"

# ================== FLASK (Render Free) ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ================== DATABASE ==================
def db():
    return sqlite3.connect(DB)

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS subs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            service TEXT,
            start_date TEXT,
            end_date TEXT,
            remind_date TEXT,
            chat_id INTEGER
        )
        """)

# ================== PROGRESS BAR (COLORED) ==================
def progress_bar(start, end):
    today = datetime.date.today()
    total = (end - start).days
    used = (today - start).days
    used = max(0, min(used, total))

    percent = int((used / total) * 100) if total else 100
    blocks = int(percent / 10)

    if percent >= 70:
        block = "🟩"
    elif percent >= 40:
        block = "🟨"
    else:
        block = "🟥"

    bar = block * blocks + "⬜" * (10 - blocks)
    return percent, bar

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Private bot")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Add Subscription", callback_data="add")],
        [InlineKeyboardButton("📋 View Subscriptions", callback_data="view")]
    ]
    await update.message.reply_text(
        "📦 Subscription Manager",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== MENU ==================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "add":
        context.user_data.clear()
        context.user_data["step"] = "name"
        await q.message.reply_text("👤 Customer name?")

    elif q.data == "view":
        with db() as con:
            rows = con.execute(
                "SELECT id,name,service,start_date,end_date FROM subs ORDER BY end_date"
            ).fetchall()

        if not rows:
            await q.message.reply_text("📭 No subscriptions found")
            return

        for r in rows:
            start = datetime.date.fromisoformat(r[3])
            end = datetime.date.fromisoformat(r[4])
            percent, bar = progress_bar(start, end)

            msg = (
                f"#{r[0]} | {r[1] or '-'} – {r[2] or '-'}\n"
                f"⏳ Ends: {r[4]}\n"
                f"{bar} {percent}%"
            )

            keyboard = [
                [
                    InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{r[0]}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{r[0]}")
                ]
            ]

            await q.message.reply_text(
                msg,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

# ================== TEXT HANDLER ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "name":
        context.user_data["name"] = update.message.text
        context.user_data["step"] = "service"
        await update.message.reply_text("🛠 Service name?")

    elif step == "service":
        context.user_data["service"] = update.message.text
        keyboard = [
            [InlineKeyboardButton("1 Month", callback_data="dur_1")],
            [InlineKeyboardButton("3 Months", callback_data="dur_3")],
            [InlineKeyboardButton("6 Months", callback_data="dur_6")],
            [InlineKeyboardButton("1 Year", callback_data="dur_12")]
        ]
        await update.message.reply_text(
            "⏱ Select duration:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data["step"] = None

    elif step == "edit_name":
        if update.message.text != "-":
            context.user_data["new_name"] = update.message.text
        context.user_data["step"] = "edit_service"
        await update.message.reply_text("🛠 New service name? (or - to skip)")

    elif step == "edit_service":
        if update.message.text != "-":
            context.user_data["new_service"] = update.message.text

        keyboard = [
            [InlineKeyboardButton("1 Month", callback_data="editdur_1")],
            [InlineKeyboardButton("3 Months", callback_data="editdur_3")],
            [InlineKeyboardButton("6 Months", callback_data="editdur_6")],
            [InlineKeyboardButton("1 Year", callback_data="editdur_12")]
        ]
        await update.message.reply_text(
            "⏱ Select new duration:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data["step"] = None

# ================== ADD ==================
async def duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    months = int(q.data.replace("dur_", ""))
    start = datetime.date.today()
    end = start + datetime.timedelta(days=30 * months)
    remind = end - datetime.timedelta(days=2)

    with db() as con:
        con.execute(
            "INSERT INTO subs (name,service,start_date,end_date,remind_date,chat_id) VALUES (?,?,?,?,?,?)",
            (
                context.user_data.get("name"),
                context.user_data.get("service"),
                start.isoformat(),
                end.isoformat(),
                remind.isoformat(),
                q.message.chat_id
            )
        )

    context.user_data.clear()
    await q.message.reply_text(f"✅ Subscription saved\n⏳ Ends: {end}")

# ================== DELETE ==================
async def delete_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sub_id = q.data.split("_")[1]

    with db() as con:
        con.execute("DELETE FROM subs WHERE id=?", (sub_id,))

    await q.message.reply_text("🗑️ Subscription deleted")

# ================== EDIT ==================
async def edit_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    context.user_data.clear()
    context.user_data["edit_id"] = q.data.split("_")[1]
    context.user_data["step"] = "edit_name"

    await q.message.reply_text("✏️ New customer name? (or - to skip)")

async def edit_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    months = int(q.data.replace("editdur_", ""))
    sub_id = context.user_data["edit_id"]

    start = datetime.date.today()
    end = start + datetime.timedelta(days=30 * months)
    remind = end - datetime.timedelta(days=2)

    with db() as con:
        if "new_name" in context.user_data:
            con.execute("UPDATE subs SET name=? WHERE id=?", (context.user_data["new_name"], sub_id))
        if "new_service" in context.user_data:
            con.execute("UPDATE subs SET service=? WHERE id=?", (context.user_data["new_service"], sub_id))

        con.execute(
            "UPDATE subs SET start_date=?, end_date=?, remind_date=? WHERE id=?",
            (start.isoformat(), end.isoformat(), remind.isoformat(), sub_id)
        )

    context.user_data.clear()
    await q.message.reply_text("✅ Subscription updated")

# ================== REMINDER ==================
async def reminder(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today().isoformat()
    with db() as con:
        rows = con.execute(
            "SELECT name,service,chat_id FROM subs WHERE remind_date=?",
            (today,)
        ).fetchall()

    for r in rows:
        await context.bot.send_message(
            chat_id=r[2],
            text=f"🔔 Reminder: {r[0]} ({r[1]}) expires in 2 days"
        )

# ================== MAIN ==================
def main():
    init_db()
    bot = ApplicationBuilder().token(TOKEN).build()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(duration, pattern="^dur_"))
    bot.add_handler(CallbackQueryHandler(edit_duration, pattern="^editdur_"))
    bot.add_handler(CallbackQueryHandler(delete_sub, pattern="^del_"))
    bot.add_handler(CallbackQueryHandler(edit_sub, pattern="^edit_"))
    bot.add_handler(CallbackQueryHandler(menu))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    bot.job_queue.run_daily(reminder, time=datetime.time(hour=9))
    bot.run_polling()

if __name__ == "__main__":
    main()
