
import os
import sqlite3
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
DB = "subscriptions.db"

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

def months_to_int(label):
    return {"1 شهر":1,"3 أشهر":3,"6 أشهر":6,"سنة":12}[label]

def progress_bar(start, end):
    today = datetime.date.today()
    total = (end - start).days
    used = (today - start).days
    used = max(0, min(used, total))
    percent = int((used / total) * 100) if total else 100
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return percent, bar

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ هذا البوت خاص")
        return
    kb = [
        [InlineKeyboardButton("➕ Add", callback_data="add")],
        [InlineKeyboardButton("📋 View", callback_data="view")],
    ]
    await update.message.reply_text("📦 Subscription Manager (Progress)", reply_markup=InlineKeyboardMarkup(kb))

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "add":
        context.user_data.clear()
        context.user_data["step"] = "name"
        await q.message.reply_text("اسم الزبون؟")

    elif q.data == "view":
        with db() as con:
            rows = con.execute(
                "SELECT id,name,service,start_date,end_date FROM subs ORDER BY end_date"
            ).fetchall()
        if not rows:
            await q.message.reply_text("لا يوجد اشتراكات")
            return
        msg = "📋 الاشتراكات:\n\n"
        for r in rows:
            start = datetime.date.fromisoformat(r[3])
            end = datetime.date.fromisoformat(r[4])
            percent, bar = progress_bar(start, end)
            msg += (
                f"#{r[0]} | {r[1]} – {r[2]}\n"
                f"⏳ {r[4]}\n"
                f"{bar} {percent}%\n\n"
            )
        await q.message.reply_text(msg)

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "name":
        context.user_data["name"] = update.message.text
        context.user_data["step"] = "service"
        await update.message.reply_text("اسم الخدمة؟")

    elif step == "service":
        context.user_data["service"] = update.message.text
        kb = [
            [InlineKeyboardButton("1 شهر", callback_data="dur_1 شهر")],
            [InlineKeyboardButton("3 أشهر", callback_data="dur_3 أشهر")],
            [InlineKeyboardButton("6 أشهر", callback_data="dur_6 أشهر")],
            [InlineKeyboardButton("سنة", callback_data="dur_سنة")]
        ]
        await update.message.reply_text("المدة؟", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data["step"] = None

async def duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    months = months_to_int(q.data.replace("dur_",""))
    start = datetime.date.today()
    end = start + datetime.timedelta(days=30*months)
    remind = end - datetime.timedelta(days=2)

    with db() as con:
        con.execute(
            "INSERT INTO subs (name,service,start_date,end_date,remind_date,chat_id) VALUES (?,?,?,?,?,?)",
            (
                context.user_data["name"],
                context.user_data["service"],
                start.isoformat(),
                end.isoformat(),
                remind.isoformat(),
                q.message.chat_id
            )
        )

    await q.message.reply_text(f"✅ تم الإضافة\n⏳ ينتهي: {end}")
    context.user_data.clear()

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
            text=f"🔔 تذكير: اشتراك {r[0]} ({r[1]}) ينتهي بعد يومين"
        )

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu))
    app.add_handler(CallbackQueryHandler(duration, pattern="^dur_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))

    app.job_queue.run_daily(reminder, time=datetime.time(hour=9))
    app.run_polling()

if __name__ == "__main__":
    main()
