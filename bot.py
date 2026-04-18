import logging
import json
import os
import re
import asyncio
import threading
import http.server
import socketserver
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== بيانات البوت ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8251573860:AAE29C3t7x0xeMbYeQQ05nEkdTyGTRjo82M")
GROUP_ID = -1003367543007
ADMIN_CHANNEL_ID = -1003751647210
GROUP_LINK = "https://t.me/+fmOvJlfty01iZTBk"
STATS_FILE = "user_stats.json"
MAINTENANCE_FILE = "maintenance_data.json"
BOT_USERNAME = "InscripAtions_Archive_bot"
MAINTENANCE_ADMINS = [757897877, 7926761229, 8202260795]
# ===================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ========== إدارة الملفات ==========
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        try:
            return json.load(f)
        except:
            return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_stats():
    return load_json(STATS_FILE, {})

def save_stats(stats):
    save_json(STATS_FILE, stats)

def get_user_stats(user_id):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats:
        stats[uid] = {"warns": 0, "banned": False, "msg_count": 0}
    return stats[uid]

def update_user_stats(user_id, key, value):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats:
        stats[uid] = {"warns": 0, "banned": False, "msg_count": 0}
    stats[uid][key] = value
    save_stats(stats)

def increment_msg_count(user_id):
    s = get_user_stats(user_id)
    s["msg_count"] += 1
    update_user_stats(user_id, "msg_count", s["msg_count"])

def get_msg_count(user_id):
    return get_user_stats(user_id)["msg_count"]

def increment_warn(user_id):
    s = get_user_stats(user_id)
    s["warns"] += 1
    update_user_stats(user_id, "warns", s["warns"])

def set_banned(user_id, banned):
    s = get_user_stats(user_id)
    s["banned"] = banned
    if banned:
        s["warns"] = 0
    update_user_stats(user_id, "warns", s["warns"])
    update_user_stats(user_id, "banned", banned)

def is_banned(user_id):
    return get_user_stats(user_id)["banned"]

def load_maintenance():
    return load_json(MAINTENANCE_FILE, {"mode": False, "users": [], "status_msg_id": None})

def save_maintenance(data):
    save_json(MAINTENANCE_FILE, data)

def is_maintenance():
    return load_maintenance().get("mode", False)

def set_maintenance(enabled):
    data = load_maintenance()
    data["mode"] = enabled
    if not enabled:
        data["users"] = []
    save_maintenance(data)

def add_contacted_user(user_id):
    data = load_maintenance()
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_maintenance(data)

def get_contacted_users():
    return load_maintenance().get("users", [])

def set_status_msg_id(msg_id):
    data = load_maintenance()
    data["status_msg_id"] = msg_id
    save_maintenance(data)

def get_status_msg_id():
    return load_maintenance().get("status_msg_id")
# ===============================

async def post_init_handler(app: Application):
    print("🧹 تنظيف الجلسات القديمة...")
    await app.bot.delete_webhook(drop_pending_updates=True)
    print("✅ جاهز")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("reply_"):
        parts = context.args[0].split("_")
        if len(parts) >= 3:
            context.user_data['replying_to'] = int(parts[1])
            context.user_data['replying_to_msg_id'] = int(parts[2])
            await update.message.reply_text(
                f"✏️ اكتب ردك على المستخدم <code>{parts[1]}</code>:",
                parse_mode="HTML"
            )
            return
    welcome = (
        "أهلاً بك في بوت أرشيف النقشات! 🎨\n\n"
        "أرسل الصورة أو الملف مباشرة هنا.\n"
        "الخدمة متاحة لأعضاء مجموعة *ارشيف النقشات* فقط."
    )
    await update.message.reply_text(welcome)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    msg = update.message

    if is_banned(user_id):
        return

    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        is_member = member.status in ['member', 'administrator', 'creator']
    except:
        is_member = False

    maintenance = is_maintenance()

    if maintenance:
        add_contacted_user(user_id)
        await msg.reply_text("🚧 البوت والمجموعة قيد التطوير. سيتم التواصل معك لاحقًا.")
    else:
        if not is_member:
            await msg.reply_text(f"❌ الخدمة للأعضاء فقط.\n🔗 {GROUP_LINK}")
            return
        cnt = get_msg_count(user_id)
        increment_msg_count(user_id)
        if cnt == 0 or cnt % 5 == 0:
            await msg.reply_text("✅ تم استلام رسالتك.")

    # إرسال للقناة
    stats = get_user_stats(user_id)
    info = f"👤 {user.first_name}"
    if user.username:
        info += f" (@{user.username})"
    info += f"\n🆔 <code>{user_id}</code>\n📌 عضو: {'✅' if is_member else '❌'}"
    if not maintenance:
        info += f"\n📊 إنذارات: {stats['warns']}"
    if stats['banned']:
        info += " | 🚫 محظور"
    if maintenance:
        info += "\n🚧 وضع الصيانة"

    warn_btn = InlineKeyboardButton(f"⚠️ إنذار ({stats['warns']})", callback_data=f"warn_{user_id}")
    ban_btn = InlineKeyboardButton("🚫 محظور" if stats['banned'] else "🚫 حظر", callback_data="already_banned" if stats['banned'] else f"ban_{user_id}")

    cap = f"{info}\n\n📩 الرسالة:"
    try:
        if msg.text:
            sent = await context.bot.send_message(ADMIN_CHANNEL_ID, f"{cap}\n{msg.text}", parse_mode="HTML")
        elif msg.photo:
            sent = await context.bot.send_photo(ADMIN_CHANNEL_ID, msg.photo[-1].file_id, caption=cap, parse_mode="HTML")
        elif msg.document:
            sent = await context.bot.send_document(ADMIN_CHANNEL_ID, msg.document.file_id, caption=cap, parse_mode="HTML")
        else:
            sent = await context.bot.send_message(ADMIN_CHANNEL_ID, f"{cap}\n(نوع غير مدعوم)", parse_mode="HTML")
    except Exception as e:
        print(f"خطأ: {e}")
        return

    msg_id = sent.message_id
    reply_url = f"https://t.me/{BOT_USERNAME}?start=reply_{user_id}_{msg_id}"
    keyboard = [
        [InlineKeyboardButton("💬 رد", url=reply_url), ban_btn, InlineKeyboardButton("🔓 إلغاء", callback_data=f"unban_{user_id}")],
        [warn_btn, InlineKeyboardButton("🗑️ حذف", callback_data="delete")]
    ]
    try:
        if sent.photo:
            await sent.edit_caption(caption=cap, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await sent.edit_text(f"{cap}\n{msg.text or ''}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except:
        pass

    if "reply_counts" not in context.bot_data:
        context.bot_data["reply_counts"] = {}
    context.bot_data["reply_counts"][str(msg_id)] = 0

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    msg = q.message

    if data == "delete":
        await msg.delete()
        return
    if data == "already_banned":
        await q.answer("محظور بالفعل", show_alert=False)
        return
    if data == "toggle_maintenance":
        if update.effective_user.id not in MAINTENANCE_ADMINS:
            await q.answer("غير مصرح", show_alert=True)
            return
        current = is_maintenance()
        set_maintenance(not current)
        await update_status_message(context)
        await q.answer(f"الصيانة {'مفعلة' if not current else 'معطلة'}", show_alert=False)
        # إذا تم إيقاف الصيانة، أرسل الروابط
        if current:
            await send_links_to_contacted_users(context)
        return

    action, uid = data.split("_", 1)
    uid = int(uid)

    if action == "ban":
        set_banned(uid, True)
        await update_message_after_action(msg, uid, context)
        await context.bot.send_message(update.effective_user.id, f"🚫 تم حظر {uid}")
        try:
            await context.bot.send_message(uid, "⛔ تم حظرك من البوت")
        except:
            pass
    elif action == "unban":
        set_banned(uid, False)
        await update_message_after_action(msg, uid, context)
        await context.bot.send_message(update.effective_user.id, f"🔓 تم إلغاء حظر {uid}")
        try:
            await context.bot.send_message(uid, "✅ تم إلغاء حظرك")
        except:
            pass
    elif action == "warn":
        increment_warn(uid)
        rules = "⚠️ إنذار.\n1- الاحترام\n2- عدم تكرار السؤال\n3- عدم الإكثار\n4- محتوى مناسب"
        try:
            await context.bot.send_message(uid, rules)
        except:
            pass
        await update_message_after_action(msg, uid, context)
        await q.answer("تم الإنذار", show_alert=False)

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'replying_to' not in context.user_data:
        return
    target = context.user_data['replying_to']
    txt = update.message.text
    try:
        await context.bot.send_message(target, f"📩 رد من الإدارة:\n\n{txt}", parse_mode="HTML")
        msg_id = context.user_data.get('replying_to_msg_id')
        if msg_id and "reply_counts" in context.bot_data:
            key = str(msg_id)
            context.bot_data["reply_counts"][key] = context.bot_data["reply_counts"].get(key, 0) + 1
            await update_message_reply_count(msg_id, context.bot_data["reply_counts"][key], context)
        await update.message.reply_text(f"✅ تم الرد على {target}")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل: {e}")
    finally:
        del context.user_data['replying_to']
        if 'replying_to_msg_id' in context.user_data:
            del context.user_data['replying_to_msg_id']

async def update_message_after_action(msg, uid, context):
    stats = get_user_stats(uid)
    warns = stats["warns"]
    banned = stats["banned"]
    new_cap = msg.caption or msg.text or ""
    pattern = r"📊 إنذارات: \d+"
    new_stat = f"📊 إنذارات: {warns}"
    if banned:
        new_stat += " | 🚫 محظور"
    if re.search(pattern, new_cap):
        new_cap = re.sub(pattern, new_stat, new_cap)
    else:
        new_cap += f"\n{new_stat}"
    warn_btn = InlineKeyboardButton(f"⚠️ إنذار ({warns})", callback_data=f"warn_{uid}")
    ban_btn = InlineKeyboardButton("🚫 محظور" if banned else "🚫 حظر", callback_data="already_banned" if banned else f"ban_{uid}")
    reply_url = f"https://t.me/{BOT_USERNAME}?start=reply_{uid}_{msg.message_id}"
    keyboard = [
        [InlineKeyboardButton("💬 رد", url=reply_url), ban_btn, InlineKeyboardButton("🔓 إلغاء", callback_data=f"unban_{uid}")],
        [warn_btn, InlineKeyboardButton("🗑️ حذف", callback_data="delete")]
    ]
    try:
        if msg.photo:
            await msg.edit_caption(caption=new_cap, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await msg.edit_text(new_cap, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except:
        pass

async def update_message_reply_count(msg_id, count, context):
    try:
        msg = await context.bot.get_message(ADMIN_CHANNEL_ID, msg_id)
        new_cap = (msg.caption or msg.text or "")
        new_cap = re.sub(r"(📊 الردود: )\d+", rf"\g<1>{count}", new_cap)
        if msg.photo:
            await msg.edit_caption(caption=new_cap, reply_markup=msg.reply_markup, parse_mode="HTML")
        else:
            await msg.edit_text(new_cap, reply_markup=msg.reply_markup, parse_mode="HTML")
    except:
        pass

async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = load_stats()
    banned = [uid for uid, d in stats.items() if d.get("banned")]
    if not banned:
        await update.message.reply_text("📭 لا يوجد محظورون")
        return
    txt = "🚫 المحظورون:\n"
    kb = []
    for uid in banned:
        try:
            u = await context.bot.get_chat(int(uid))
            name = u.first_name
        except:
            name = uid
        txt += f"\n🆔 {uid} - {name}"
        kb.append([InlineKeyboardButton(f"🔓 إلغاء {uid}", callback_data=f"unban_{uid}")])
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/unban id")
        return
    try:
        uid = int(context.args[0])
    except:
        await update.message.reply_text("معرف غير صالح")
        return
    if not is_banned(uid):
        await update.message.reply_text("غير محظور")
        return
    set_banned(uid, False)
    await update.message.reply_text(f"🔓 تم إلغاء حظر {uid}")
    try:
        await context.bot.send_message(uid, "✅ تم إلغاء حظرك")
    except:
        pass

async def send_links_to_contacted_users(context: ContextTypes.DEFAULT_TYPE):
    users = get_contacted_users()
    sent = 0
    for uid in users:
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            if member.status not in ['member', 'administrator', 'creator']:
                await context.bot.send_message(uid, f"🔗 انضم للمجموعة:\n{GROUP_LINK}")
                sent += 1
        except:
            pass
    await context.bot.send_message(ADMIN_CHANNEL_ID, f"✅ تم إرسال الرابط لـ {sent} مستخدم.")

async def update_status_message(context: ContextTypes.DEFAULT_TYPE):
    mode = is_maintenance()
    text = f"🚧 حالة الصيانة: {'🟢 مفعلة' if mode else '🔴 معطلة'}"
    kb = [[InlineKeyboardButton("🔴 إيقاف" if mode else "🟢 تفعيل", callback_data="toggle_maintenance")]]
    msg_id = get_status_msg_id()
    try:
        if msg_id:
            await context.bot.edit_message_text(text, ADMIN_CHANNEL_ID, msg_id, reply_markup=InlineKeyboardMarkup(kb))
        else:
            msg = await context.bot.send_message(ADMIN_CHANNEL_ID, text, reply_markup=InlineKeyboardMarkup(kb))
            set_status_msg_id(msg.message_id)
    except:
        msg = await context.bot.send_message(ADMIN_CHANNEL_ID, text, reply_markup=InlineKeyboardMarkup(kb))
        set_status_msg_id(msg.message_id)

async def init_status_message(app: Application):
    await update_status_message(app)

def main():
    port = int(os.environ.get("PORT", 10000))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, format, *args):
            pass
    def run_server():
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
            httpd.serve_forever()
    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).post_init(post_init_handler).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("banned", banned_list))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply), group=1)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_status_message(app))
    try:
        loop.run_until_complete(app.run_polling())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

if __name__ == "__main__":
    main()
