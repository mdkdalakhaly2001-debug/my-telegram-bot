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
BOT_USERNAME = "InscripAtions_Archive_bot"
# ===================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ========== إدارة إحصائيات المستخدمين ==========
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {}
    with open(STATS_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

def get_user_stats(user_id):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats:
        stats[uid] = {"warns": 0, "banned": False}
    return stats[uid]

def update_user_stats(user_id, key, value):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats:
        stats[uid] = {"warns": 0, "banned": False}
    stats[uid][key] = value
    save_stats(stats)

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
# =============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("reply_"):
            parts = arg.split("_")
            if len(parts) >= 3:
                target_user_id = int(parts[1])
                msg_id = int(parts[2])
                context.user_data['replying_to'] = target_user_id
                context.user_data['replying_to_msg_id'] = msg_id
                await update.message.reply_text(
                    f"✏️ اكتب ردك على المستخدم <code>{target_user_id}</code> (سيصله الرد من البوت ولن تظهر هويتك):",
                    parse_mode="HTML"
                )
                return

    welcome_text = (
        "أهلاً بك في بوت أرشيف النقشات! 🎨\n\n"
        "هذا البوت مخصص لاستقبال رسائلكم للرسومات الجديدة أو غير الموجودة (هندسية، نباتية، تجريدية الخ...)"
        " أو أي ملاحظات أخرى من أعضاء مجموعة *ارشيف النقشات*.\n\n"
        "🔹 أرسل الصورة أو الملف مباشرة هنا.\n"
        "🔹 إذا لم تكن عضواً في المجموعة، لن يتم استلام إرسالك.\n\n"
        "شكراً لمساهمتك!"
    )
    await update.message.reply_text(welcome_text)

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

    if not is_member:
        await msg.reply_text(
            f"❌ عذرًا، هذه الخدمة متاحة فقط لأعضاء مجموعة *ارشيف النقشات*.\n\n"
            f"🔗 يرجى الانضمام للمجموعة أولاً:\n{GROUP_LINK}"
        )
        return

    user_stats = get_user_stats(user_id)
    warns_count = user_stats["warns"]
    user_info = f"👤 <b>المستخدم:</b> {user.first_name}"
    if user.username:
        user_info += f" (@{user.username})"
    user_info += f"\n🆔 <code>{user_id}</code>"
    user_info += f"\n📌 <b>عضو في المجموعة:</b> ✅ نعم"
    user_info += f"\n📊 <b>الردود:</b> 0 | <b>الإنذارات:</b> {warns_count}"
    if user_stats["banned"]:
        user_info += " | <b>🚫 محظور</b>"

    warn_button = InlineKeyboardButton(f"⚠️ إنذار ({warns_count})", callback_data=f"warn_{user_id}")
    ban_button = InlineKeyboardButton("🚫 محظور" if user_stats["banned"] else "🚫 حظر من البوت",
                                      callback_data="already_banned" if user_stats["banned"] else f"ban_{user_id}")

    caption = f"{user_info}\n\n📩 <b>الرسالة:</b>"
    sent_msg = None
    try:
        if msg.text:
            sent_msg = await context.bot.send_message(
                chat_id=ADMIN_CHANNEL_ID,
                text=f"{caption}\n{msg.text}",
                parse_mode="HTML"
            )
        elif msg.photo:
            sent_msg = await context.bot.send_photo(
                chat_id=ADMIN_CHANNEL_ID,
                photo=msg.photo[-1].file_id,
                caption=caption,
                parse_mode="HTML"
            )
        elif msg.document:
            sent_msg = await context.bot.send_document(
                chat_id=ADMIN_CHANNEL_ID,
                document=msg.document.file_id,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            sent_msg = await context.bot.send_message(
                chat_id=ADMIN_CHANNEL_ID,
                text=f"{caption}\n(نوع رسالة غير مدعوم)",
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"خطأ في إرسال الرسالة إلى قناة المشرف: {e}")
        return

    msg_id = sent_msg.message_id
    reply_url = f"https://t.me/{BOT_USERNAME}?start=reply_{user_id}_{msg_id}"

    keyboard = [
        [
            InlineKeyboardButton("💬 رد", url=reply_url),
            ban_button,
            InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"unban_{user_id}"),
        ],
        [
            warn_button,
            InlineKeyboardButton("🗑️ حذف", callback_data="delete"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if sent_msg.photo:
            await sent_msg.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await sent_msg.edit_text(text=f"{caption}\n{msg.text if msg.text else ''}", reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        print(f"خطأ في إضافة الأزرار: {e}")

    if "reply_counts" not in context.bot_data:
        context.bot_data["reply_counts"] = {}
    context.bot_data["reply_counts"][str(msg_id)] = 0

    await msg.reply_text("✅ تم استلام رسالتك. سنتواصل معك قريباً.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    message = query.message

    if data == "delete":
        await message.delete()
        return
    if data == "already_banned":
        await query.answer("هذا المستخدم محظور بالفعل.", show_alert=False)
        return

    action, target_user_id = data.split("_", 1)
    target_user_id = int(target_user_id)

    if action == "ban":
        set_banned(target_user_id, True)
        await update_message_after_action(message, target_user_id, context)
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"🚫 تم حظر المستخدم <code>{target_user_id}</code> من استخدام البوت."
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text="⛔ لقد تم حظرك من استخدام بوت أرشيف النقشات.")
        except:
            pass
    elif action == "unban":
        set_banned(target_user_id, False)
        await update_message_after_action(message, target_user_id, context)
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"🔓 تم إلغاء حظر المستخدم <code>{target_user_id}</code>."
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text="✅ تم إلغاء حظرك من بوت أرشيف النقشات.")
        except:
            pass
    elif action == "warn":
        increment_warn(target_user_id)
        rules_text = (
            "⚠️ <b>إنذار من إدارة مجموعة أرشيف النقشات</b> ⚠️\n\n"
            "قواعد الاستخدام:\n"
            "1- الاحترام وعدم التلفظ بأي ألفاظ مخلة.\n"
            "2- عدم تكرار السؤال خلال 24 ساعة.\n"
            "3- عدم الإكثار من الرسائل.\n"
            "4- عدم إرسال أشياء خارج إطار المجموعة.\n\n"
            "يرجى الالتزام بهذه القواعد لتجنب الحظر."
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text=rules_text, parse_mode="HTML")
        except:
            pass
        await update_message_after_action(message, target_user_id, context)
        await query.answer("تم إرسال الإنذار.", show_alert=False)

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'replying_to' not in context.user_data:
        return
    target_user_id = context.user_data['replying_to']
    reply_text = update.message.text
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📩 <b>رد من إدارة أرشيف النقشات:</b>\n\n{reply_text}",
            parse_mode="HTML"
        )
        msg_id = context.user_data.get('replying_to_msg_id')
        if msg_id and "reply_counts" in context.bot_data:
            key = str(msg_id)
            context.bot_data["reply_counts"][key] = context.bot_data["reply_counts"].get(key, 0) + 1
            new_reply_count = context.bot_data["reply_counts"][key]
            try:
                await update_message_reply_count(msg_id, new_reply_count, context)
            except:
                pass
        await update.message.reply_text(f"✅ تم إرسال الرد إلى المستخدم <code>{target_user_id}</code>.")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الرد: {e}")
    finally:
        del context.user_data['replying_to']
        if 'replying_to_msg_id' in context.user_data:
            del context.user_data['replying_to_msg_id']

async def update_message_after_action(message, user_id, context):
    user_stats = get_user_stats(user_id)
    warns = user_stats["warns"]
    banned = user_stats["banned"]

    new_caption = message.caption or message.text or ""
    stats_pattern = r"📊 <b>الردود:</b> \d+ \| <b>الإنذارات:</b> \d+( \| <b>🚫 محظور</b>)?"
    new_stats = f"📊 <b>الردود:</b> {context.bot_data['reply_counts'].get(str(message.message_id), 0)} | <b>الإنذارات:</b> {warns}"
    if banned:
        new_stats += " | <b>🚫 محظور</b>"
    if re.search(stats_pattern, new_caption):
        new_caption = re.sub(stats_pattern, new_stats, new_caption)
    else:
        new_caption += f"\n{new_stats}"

    warn_button = InlineKeyboardButton(f"⚠️ إنذار ({warns})", callback_data=f"warn_{user_id}")
    ban_button = InlineKeyboardButton("🚫 محظور" if banned else "🚫 حظر من البوت",
                                      callback_data="already_banned" if banned else f"ban_{user_id}")

    reply_url = f"https://t.me/{BOT_USERNAME}?start=reply_{user_id}_{message.message_id}"

    keyboard = [
        [
            InlineKeyboardButton("💬 رد", url=reply_url),
            ban_button,
            InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"unban_{user_id}"),
        ],
        [
            warn_button,
            InlineKeyboardButton("🗑️ حذف", callback_data="delete"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if message.photo:
            await message.edit_caption(caption=new_caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await message.edit_text(text=new_caption, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        print(f"خطأ في تحديث الرسالة: {e}")

async def update_message_reply_count(message_id, count, context):
    try:
        chat = await context.bot.get_chat(ADMIN_CHANNEL_ID)
        msg = await context.bot.get_message(chat_id=ADMIN_CHANNEL_ID, message_id=message_id)
        new_caption = msg.caption or msg.text or ""
        new_caption = re.sub(r"(📊 <b>الردود:</b> )\d+", rf"\g<1>{count}", new_caption)
        if msg.photo:
            await msg.edit_caption(caption=new_caption, reply_markup=msg.reply_markup, parse_mode="HTML")
        else:
            await msg.edit_text(text=new_caption, reply_markup=msg.reply_markup, parse_mode="HTML")
    except Exception as e:
        print(f"خطأ في تحديث عدد الردود: {e}")

# ========== أوامر المشرف ==========
async def banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = load_stats()
    banned_users = [uid for uid, data in stats.items() if data.get("banned", False)]
    if not banned_users:
        await update.message.reply_text("📭 لا يوجد مستخدمون محظورون حالياً.")
        return
    text = "🚫 <b>قائمة المحظورين من البوت:</b>\n"
    keyboard = []
    for uid in banned_users:
        try:
            user = await context.bot.get_chat(int(uid))
            name = user.first_name
            if user.username:
                name += f" (@{user.username})"
        except:
            name = uid
        text += f"\n🆔 <code>{uid}</code> - {name}"
        keyboard.append([InlineKeyboardButton(f"🔓 إلغاء حظر {uid}", callback_data=f"unban_{uid}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("الرجاء إدخال معرف المستخدم: /unban 123456789")
        return
    try:
        uid = int(context.args[0])
    except:
        await update.message.reply_text("معرف غير صالح.")
        return
    if not is_banned(uid):
        await update.message.reply_text("هذا المستخدم ليس محظوراً.")
        return
    set_banned(uid, False)
    await update.message.reply_text(f"🔓 تم إلغاء حظر المستخدم <code>{uid}</code>.")
    try:
        await context.bot.send_message(chat_id=uid, text="✅ تم إلغاء حظرك من بوت أرشيف النقشات.")
    except:
        pass

async def run_bot():
    """تشغيل البوت بشكل غير متزامن مع معالجة حلقة الأحداث"""
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("banned", banned_list))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & filters.UpdateType.MESSAGE, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply), group=1)
    print("✅ البوت يعمل الآن على Render...")
    await app.run_polling()

def main():
    # تشغيل خادم HTTP الوهمي في خيط منفصل (دون تعارض مع المنفذ)
    port = int(os.environ.get("PORT", 10000))
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, format, *args):
            pass  # إيقاف طباعة الطلبات لتقليل التشويش
    def run_server():
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
            print(f"خادم HTTP الوهمي يعمل على المنفذ {port}")
            httpd.serve_forever()
    threading.Thread(target=run_server, daemon=True).start()

    # تشغيل البوت مع asyncio
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
