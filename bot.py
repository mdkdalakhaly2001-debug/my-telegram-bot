import logging
import json
import os
import re
import asyncio
import threading
import http.server
import socketserver
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, JobQueue

# ========== بيانات البوت ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود")

GROUP_ID = -1003367543007
ADMIN_CHANNEL_ID = -1003751647210
GROUP_LINK = "https://t.me/+fmOvJlfty01iZTBk"
STATS_FILE = "user_stats.json"
MAINTENANCE_FILE = "maintenance_data.json"
BOT_USERNAME = "InscripAtions_Archive_bot"
MAINTENANCE_ADMINS = [757897877, 7926761229, 8202260795]
# ===================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

def load_json(path, default):
    if not os.path.exists(path): return default
    with open(path, "r") as f:
        try: return json.load(f)
        except: return default

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def load_stats(): return load_json(STATS_FILE, {})
def save_stats(stats): save_json(STATS_FILE, stats)

def get_user_stats(user_id):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats: stats[uid] = {"warns": 0, "banned": False, "msg_count": 0, "ban_date": None}
    return stats[uid]

def update_user_stats(user_id, key, value):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats: stats[uid] = {"warns": 0, "banned": False, "msg_count": 0, "ban_date": None}
    stats[uid][key] = value
    save_stats(stats)

def increment_msg_count(user_id):
    s = get_user_stats(user_id)
    s["msg_count"] += 1
    update_user_stats(user_id, "msg_count", s["msg_count"])

def get_msg_count(user_id): return get_user_stats(user_id)["msg_count"]

def increment_warn(user_id):
    s = get_user_stats(user_id)
    s["warns"] += 1
    update_user_stats(user_id, "warns", s["warns"])

def set_banned(user_id, banned):
    s = get_user_stats(user_id)
    s["banned"] = banned
    s["ban_date"] = datetime.now().strftime("%y/%m/%d") if banned else None
    if banned: s["warns"] = 0
    update_user_stats(user_id, "warns", s["warns"])
    update_user_stats(user_id, "banned", banned)
    update_user_stats(user_id, "ban_date", s["ban_date"])

def is_banned(user_id): return get_user_stats(user_id)["banned"]

def get_banned_users():
    stats = load_stats()
    return [{"id": int(uid), "date": d.get("ban_date", "?")} for uid, d in stats.items() if d.get("banned")]

def load_maintenance(): return load_json(MAINTENANCE_FILE, {"mode": False, "users": [], "status_msg_id": None, "banned_page": 0})
def save_maintenance(data): save_json(MAINTENANCE_FILE, data)
def is_maintenance(): return load_maintenance().get("mode", False)

def set_maintenance(enabled):
    data = load_maintenance()
    data["mode"] = enabled
    if not enabled: data["users"] = []
    save_maintenance(data)

def add_contacted_user(user_id):
    data = load_maintenance()
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_maintenance(data)

def get_contacted_users(): return load_maintenance().get("users", [])

async def get_user_name(bot, user_id):
    try:
        u = await bot.get_chat(user_id)
        return u.first_name or str(user_id)
    except: return str(user_id)

async def post_init_handler(app: Application):
    await app.bot.delete_webhook(drop_pending_updates=True)
    await update_status_message(app.bot)
    await update_banned_list_message(app.bot, 0)
    app.job_queue.run_repeating(update_active_users_job, interval=21600, first=10)

async def update_active_users_job(context: ContextTypes.DEFAULT_TYPE):
    await update_active_users_message(context.bot)

async def update_active_users_message(bot):
    stats = load_stats()
    active = sum(1 for d in stats.values() if d.get("msg_count", 0) > 0)
    txt = f"📊 المستخدمون النشطون: {active}\n🕒 {datetime.now().strftime('%y/%m/%d %I:%M %p')}"
    data = load_maintenance()
    msg_id = data.get("active_users_msg_id")
    try:
        if msg_id:
            await bot.edit_message_text(txt, ADMIN_CHANNEL_ID, msg_id)
        else:
            msg = await bot.send_message(ADMIN_CHANNEL_ID, txt)
            data["active_users_msg_id"] = msg.message_id
            save_maintenance(data)
    except: pass

async def update_status_message(bot):
    mode = is_maintenance()
    txt = f"🚧 الصيانة: {'🟢 مفعلة' if mode else '🔴 معطلة'}"
    kb = [[InlineKeyboardButton("🔴 إيقاف" if mode else "🟢 تفعيل", callback_data="toggle_maintenance")]]
    data = load_maintenance()
    msg_id = data.get("status_msg_id")
    try:
        if msg_id:
            await bot.edit_message_text(txt, ADMIN_CHANNEL_ID, msg_id, reply_markup=InlineKeyboardMarkup(kb))
        else:
            msg = await bot.send_message(ADMIN_CHANNEL_ID, txt, reply_markup=InlineKeyboardMarkup(kb))
            data["status_msg_id"] = msg.message_id
            save_maintenance(data)
    except:
        msg = await bot.send_message(ADMIN_CHANNEL_ID, txt, reply_markup=InlineKeyboardMarkup(kb))
        data["status_msg_id"] = msg.message_id
        save_maintenance(data)

async def update_banned_list_message(bot, page):
    banned = get_banned_users()
    if not banned:
        txt = "🚫 لا يوجد محظورون"
        kb = None
    else:
        per_page = 8
        total = len(banned)
        pages = (total + per_page - 1) // per_page
        page = max(0, min(page, pages - 1))
        start = page * per_page
        end = start + per_page
        items = []
        for i, u in enumerate(banned[start:end], start=start + 1):
            name = await get_user_name(bot, u["id"])
            short = name[:20] + "..." if len(name) > 20 else name
            items.append(f"{i}. <a href='tg://user?id={u['id']}'>{short}</a> | {u['date']}")
        txt = f"🚫 المحظورون ({page+1}/{pages})\n" + "\n".join(items)
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"banpage_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{pages}", callback_data="ignore"))
        if page < pages - 1: nav.append(InlineKeyboardButton("➡️", callback_data=f"banpage_{page+1}"))
        kb = [nav] if nav else None
    data = load_maintenance()
    msg_id = data.get("banned_list_msg_id")
    try:
        if msg_id:
            await bot.edit_message_text(txt, ADMIN_CHANNEL_ID, msg_id, reply_markup=InlineKeyboardMarkup(kb) if kb else None, parse_mode="HTML", disable_web_page_preview=True)
        else:
            msg = await bot.send_message(ADMIN_CHANNEL_ID, txt, reply_markup=InlineKeyboardMarkup(kb) if kb else None, parse_mode="HTML", disable_web_page_preview=True)
            data["banned_list_msg_id"] = msg.message_id
            save_maintenance(data)
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name
    if context.args and context.args[0].startswith("reply_"):
        parts = context.args[0].split("_")
        if len(parts) >= 3:
            target_id = int(parts[1])
            target_name = await get_user_name(context.bot, target_id)
            context.user_data['replying_to'] = target_id
            context.user_data['replying_to_msg_id'] = int(parts[2])
            await update.message.reply_text(f"✏️ اكتب ردك على {target_name}:", parse_mode="HTML")
            return
    await update.message.reply_text(f"أهلاً بك {name} في بوت أرشيف النقشات! 🎨\nأرسل الصورة أو الملف.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    msg = update.message
    if is_banned(user_id): return
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        is_member = member.status in ['member', 'administrator', 'creator']
    except: is_member = False
    if is_maintenance():
        add_contacted_user(user_id)
        await msg.reply_text("🚧 البوت قيد التطوير.")
    else:
        if not is_member:
            await msg.reply_text(f"❌ للأعضاء فقط.\n🔗 {GROUP_LINK}")
            return
        cnt = get_msg_count(user_id)
        increment_msg_count(user_id)
        if cnt == 0 or cnt % 5 == 0: await msg.reply_text("✅ تم استلام رسالتك.")
    stats = get_user_stats(user_id)
    info = f"👤 {user.first_name}" + (f" (@{user.username})" if user.username else "")
    info += f"\n🆔 <code>{user_id}</code>\n📌 عضو: {'✅' if is_member else '❌'}"
    if not is_maintenance(): info += f"\n📊 إنذارات: {stats['warns']}"
    if stats['banned']: info += " | 🚫 محظور"
    if is_maintenance(): info += "\n🚧 صيانة"
    warn_btn = InlineKeyboardButton(f"⚠️ إنذار ({stats['warns']})", callback_data=f"warn_{user_id}")
    ban_btn = InlineKeyboardButton("🔓 رفع" if stats['banned'] else "🚫 حظر", callback_data=f"{'unban' if stats['banned'] else 'ban'}_{user_id}")
    cap = f"{info}\n\n📩 الرسالة:"
    try:
        if msg.text: sent = await context.bot.send_message(ADMIN_CHANNEL_ID, f"{cap}\n{msg.text}", parse_mode="HTML")
        elif msg.photo: sent = await context.bot.send_photo(ADMIN_CHANNEL_ID, msg.photo[-1].file_id, caption=cap, parse_mode="HTML")
        elif msg.document: sent = await context.bot.send_document(ADMIN_CHANNEL_ID, msg.document.file_id, caption=cap, parse_mode="HTML")
        else: sent = await context.bot.send_message(ADMIN_CHANNEL_ID, f"{cap}\n(نوع غير مدعوم)", parse_mode="HTML")
    except: return
    msg_id = sent.message_id
    reply_url = f"https://t.me/{BOT_USERNAME}?start=reply_{user_id}_{msg_id}"
    keyboard = [[InlineKeyboardButton("💬 رد", url=reply_url), ban_btn], [warn_btn, InlineKeyboardButton("🗑️ حذف", callback_data="delete")]]
    try:
        if sent.photo: await sent.edit_caption(caption=cap, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else: await sent.edit_text(f"{cap}\n{msg.text or ''}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except: pass
    if "reply_counts" not in context.bot_data: context.bot_data["reply_counts"] = {}
    context.bot_data["reply_counts"][str(msg_id)] = 0

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    msg = q.message
    if data == "delete": await msg.delete(); return
    if data == "ignore": return
    if data == "toggle_maintenance":
        if update.effective_user.id not in MAINTENANCE_ADMINS: await q.answer("غير مصرح", show_alert=True); return
        cur = is_maintenance()
        set_maintenance(not cur)
        await update_status_message(context.bot)
        if cur: await send_links_to_contacted_users(context)
        await q.answer()
        return
    if data.startswith("banpage_"):
        page = int(data.split("_")[1])
        await update_banned_list_message(context.bot, page)
        await q.answer()
        return
    action, uid = data.split("_", 1)
    uid = int(uid)
    if action == "ban":
        set_banned(uid, True)
        await update_banned_list_message(context.bot, 0)
        await context.bot.send_message(update.effective_user.id, f"🚫 تم حظر {uid}")
        try: await context.bot.send_message(uid, "⛔ تم حظرك")
        except: pass
    elif action == "unban":
        set_banned(uid, False)
        await update_banned_list_message(context.bot, 0)
        await context.bot.send_message(update.effective_user.id, f"🔓 تم رفع حظر {uid}")
        try: await context.bot.send_message(uid, "✅ تم رفع الحظر")
        except: pass
    elif action == "warn":
        increment_warn(uid)
        try: await context.bot.send_message(uid, "⚠️ إنذار.\n1- الاحترام\n2- عدم التكرار\n3- عدم الإكثار\n4- محتوى مناسب")
        except: pass
        await q.answer("تم الإنذار", show_alert=False)

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'replying_to' not in context.user_data: return
    target = context.user_data['replying_to']
    txt = update.message.text
    target_name = await get_user_name(context.bot, target)
    try:
        await context.bot.send_message(target, f"📩 رد من الإدارة:\n\n{txt}", parse_mode="HTML")
        await update.message.reply_text(f"✅ تم الرد على {target} ({target_name})", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل: {e}")
    finally:
        del context.user_data['replying_to']
        if 'replying_to_msg_id' in context.user_data: del context.user_data['replying_to_msg_id']

async def send_links_to_contacted_users(context: ContextTypes.DEFAULT_TYPE):
    users = get_contacted_users()
    sent = 0
    for uid in users:
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            if member.status not in ['member', 'administrator', 'creator']:
                await context.bot.send_message(uid, f"🔗 انضم للمجموعة:\n{GROUP_LINK}")
                sent += 1
        except: pass
    await context.bot.send_message(ADMIN_CHANNEL_ID, f"✅ تم إرسال الرابط لـ {sent} مستخدم.")

async def banned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update_banned_list_message(context.bot, 0)
    await update.message.reply_text("✅ تم تحديث قائمة المحظورين")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("/unban id"); return
    try: uid = int(context.args[0])
    except: await update.message.reply_text("معرف غير صالح"); return
    if not is_banned(uid): await update.message.reply_text("غير محظور"); return
    set_banned(uid, False)
    await update_banned_list_message(context.bot, 0)
    await update.message.reply_text(f"🔓 تم رفع حظر {uid}")

def main():
    port = int(os.environ.get("PORT", 10000))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is running")
        def log_message(self, format, *args): pass
    def run_server():
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd: httpd.serve_forever()
    threading.Thread(target=run_server, daemon=True).start()
    app = Application.builder().token(TOKEN).post_init(post_init_handler).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("banned", banned_command))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply), group=1)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(app.run_polling())
    except KeyboardInterrupt: pass
    finally: loop.close()

if __name__ == "__main__":
    main()
