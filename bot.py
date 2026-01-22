--- START OF FILE bot.py ---

import telebot
from telebot import types
import sqlite3
import time
import threading
import schedule
import requests
import random
import datetime
from collections import Counter

# --- CONFIGURATION ---
API_TOKEN = '8208827118:AAF5MAigzkWKwJIfMvunIMvvFYH1zsz_DgI'
OWNER_ID = 7371674958

bot = telebot.TeleBot(API_TOKEN, threaded=True)

# --- DATABASE CONNECTION ---
def get_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        role TEXT DEFAULT 'user', 
        phone TEXT,
        crazy_premium INTEGER DEFAULT 0,
        business_plan TEXT DEFAULT 'free',
        business_expiry TEXT,
        user_affiliate_id TEXT,
        earnkaro_id TEXT,
        my_channel_id INTEGER,
        my_channel_name TEXT
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS owner_channels (channel_id INTEGER PRIMARY KEY, channel_name TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS force_channels (channel_id INTEGER PRIMARY KEY, channel_name TEXT, invite_link TEXT)''')
    defaults = [('price_crazy', '99'), ('price_1m', '199'), ('price_3m', '499'), ('price_1y', '1499'), ('post_interval', '60')]
    conn.executemany("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", defaults)
    conn.commit()
    conn.close()

init_db()

# --- HELPERS ---
def get_config(key):
    conn = get_db()
    res = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    return res[0] if res else None

def set_config(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value).strip()))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    res = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res

# --- 🔒 FORCE JOIN CHECK ---
def check_join_status(user_id):
    if user_id == OWNER_ID: return True, []
    conn = get_db()
    channels = conn.execute("SELECT * FROM force_channels").fetchall()
    conn.close()
    if not channels: return True, []
    pending = []
    for ch in channels:
        try:
            stat = bot.get_chat_member(ch['channel_id'], user_id).status
            if stat not in ['member', 'administrator', 'creator']: pending.append(ch)
        except: pending.append(ch)
    return len(pending) == 0, pending

def force_join_markup(pending):
    markup = types.InlineKeyboardMarkup()
    for ch in pending:
        markup.add(types.InlineKeyboardButton(f"Join {ch['channel_name']}", url=ch['invite_link']))
    markup.add(types.InlineKeyboardButton("✅ Verify Join", callback_data="verify_join"))
    return markup

# --- 👑 OWNER PANEL ---
@bot.message_handler(commands=['owner'])
def owner_panel(message):
    if message.from_user.id != OWNER_ID: return
    send_owner_menu(message.chat.id)

def send_owner_menu(chat_id, msg_id=None):
    amz = "✅" if get_config("amazon_tag") else "❌"
    cue = "✅" if get_config("cuelinks_token") else "❌"
    ek = "✅" if get_config("earnkaro_id") else "❌"
    log = "✅" if get_config("logs_channel_id") else "❌"
    qr = "✅" if get_config("qr_code_id") else "❌"

    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        types.InlineKeyboardButton("➕ Add Premium", callback_data="op_add_prem"),
        types.InlineKeyboardButton("➖ Del Premium", callback_data="op_del_prem"),
        types.InlineKeyboardButton("📢 Owner Channels", callback_data="op_mng_post"),
        types.InlineKeyboardButton("🛡️ Force Channels", callback_data="op_mng_force"),
        types.InlineKeyboardButton(f"📝 Set Logs {log}", callback_data="op_set_logs"),
        types.InlineKeyboardButton("📡 Broadcast", callback_data="op_broadcast"),
        types.InlineKeyboardButton("📊 Status", callback_data="op_status"),
        types.InlineKeyboardButton(f"🆔 Amazon {amz}", callback_data="op_set_aff"),
        types.InlineKeyboardButton(f"🔗 Cuelinks {cue}", callback_data="op_set_cuelinks"),
        types.InlineKeyboardButton(f"💸 EarnKaro {ek}", callback_data="op_set_earnkaro"),
        types.InlineKeyboardButton(f"📸 Payment QR {qr}", callback_data="op_set_qr"),
        types.InlineKeyboardButton("💰 Set Prices", callback_data="op_set_prices"),
        types.InlineKeyboardButton("⏱️ Post Interval", callback_data="op_set_interval"),
        types.InlineKeyboardButton("👤 Check User", callback_data="op_check"),
        types.InlineKeyboardButton("🚀 Test Loot", callback_data="op_manual_loot"),
        types.InlineKeyboardButton("⚠️ FACTORY RESET", callback_data="op_reset")
    ]
    markup.add(*btns)
    text = "👑 **Owner Control Panel**"
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

# --- OWNER CALLBACKS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("op_"))
def owner_actions(call):
    try: bot.answer_callback_query(call.id)
    except: pass
    if call.from_user.id != OWNER_ID: return
    action = call.data

    if action == "op_back_main": send_owner_menu(call.message.chat.id, call.message.message_id)
    elif action == "op_set_aff":
        msg = bot.send_message(call.message.chat.id, "🆔 **Send Amazon Associate Tag:**")
        bot.register_next_step_handler(msg, step_save_amazon)
    elif action == "op_set_cuelinks":
        msg = bot.send_message(call.message.chat.id, "🔗 **Send Cuelinks API Token:**")
        bot.register_next_step_handler(msg, step_save_cuelinks)
    elif action == "op_set_earnkaro":
        msg = bot.send_message(call.message.chat.id, "💸 **Send EarnKaro ID (PID):**")
        bot.register_next_step_handler(msg, step_save_earnkaro)
    elif action == "op_set_qr":
        msg = bot.send_message(call.message.chat.id, "📸 **Send QR Code Image:**")
        bot.register_next_step_handler(msg, step_save_qr)
    elif action == "op_set_logs":
        msg = bot.send_message(call.message.chat.id, "📝 **Forward a message from Logs Channel:**")
        bot.register_next_step_handler(msg, step_save_logs)
    elif action == "op_add_prem":
        msg = bot.send_message(call.message.chat.id, "👤 **Send User ID for Premium:**")
        bot.register_next_step_handler(msg, step_update_prem, 1)
    elif action == "op_del_prem":
        msg = bot.send_message(call.message.chat.id, "👤 **Send User ID to Remove:**")
        bot.register_next_step_handler(msg, step_update_prem, 0)
    elif action == "op_check":
        msg = bot.send_message(call.message.chat.id, "👤 **Send User ID to Check:**")
        bot.register_next_step_handler(msg, step_check_user)
    elif action == "op_set_interval":
        mk = types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("30 Mins", callback_data="set_int_30"), types.InlineKeyboardButton("1 Hour", callback_data="set_int_60"), types.InlineKeyboardButton("2 Hours", callback_data="set_int_120"), types.InlineKeyboardButton("4 Hours", callback_data="set_int_240"), types.InlineKeyboardButton("🔙 Back", callback_data="op_back_main"))
        curr = get_config("post_interval")
        bot.edit_message_text(f"⏱️ **Interval:** {curr} mins", call.message.chat.id, call.message.message_id, reply_markup=mk)
    elif action == "op_status":
        try:
            conn = get_db()
            total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            crazy = conn.execute("SELECT COUNT(*) FROM users WHERE crazy_premium=1").fetchone()[0]
            plans = conn.execute("SELECT business_plan FROM users WHERE business_plan != 'free'").fetchall()
            conn.close()
            biz_total = len(plans)
            popular = f"{Counter([r[0] for r in plans]).most_common(1)[0][0].upper()}" if biz_total else "None"
            msg = (f"📊 **STATS**\n👥 Users: `{total}`\n💎 Crazy: `{crazy}`\n?? Biz: `{biz_total}`\n📈 Top: `{popular}`")
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        except: bot.send_message(call.message.chat.id, "❌ Error.")
    elif action == "op_manual_loot":
        bot.send_message(call.message.chat.id, "🚀 **Testing API (Auth Fix Mode)...**")
        threading.Thread(target=auto_post_task, args=(True, call.message.chat.id)).start()
    elif action == "op_broadcast":
        msg = bot.send_message(call.message.chat.id, "📡 **Send Message to Broadcast:**")
        bot.register_next_step_handler(msg, start_broadcast_thread)
    elif action == "op_mng_post":
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("➕ Add", callback_data="own_add_ch"), types.InlineKeyboardButton("🗑️ Del All", callback_data="own_del_all"), types.InlineKeyboardButton("🔙", callback_data="op_back_main")); bot.edit_message_text("📢 **Owner Channels**", call.message.chat.id, call.message.message_id, reply_markup=mk)
    elif action == "op_mng_force":
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("➕ Add", callback_data="force_add_ch"), types.InlineKeyboardButton("🗑️ Del All", callback_data="force_del_all"), types.InlineKeyboardButton("🔙", callback_data="op_back_main")); bot.edit_message_text("🛡️ **Force Join**", call.message.chat.id, call.message.message_id, reply_markup=mk)
    elif action == "op_set_prices":
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("Crazy", callback_data="set_pr_crazy"), types.InlineKeyboardButton("Business", callback_data="set_pr_biz"), types.InlineKeyboardButton("🔙", callback_data="op_back_main")); bot.edit_message_text("💰 **Prices**", call.message.chat.id, call.message.message_id, reply_markup=mk)
    elif action == "op_reset":
        mk = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ CONFIRM", callback_data="confirm_reset"), types.InlineKeyboardButton("❌", callback_data="op_back_main")); bot.edit_message_text("⚠️ **RESET ALL?**", call.message.chat.id, call.message.message_id, reply_markup=mk)

# --- STEP HANDLERS ---
def step_save_amazon(m): set_config("amazon_tag", m.text); bot.reply_to(m, "✅ Saved!"); send_owner_menu(m.chat.id)
def step_save_cuelinks(m): set_config("cuelinks_token", m.text); bot.reply_to(m, "✅ Saved!"); send_owner_menu(m.chat.id)
def step_save_earnkaro(m): set_config("earnkaro_id", m.text); bot.reply_to(m, "✅ Saved!"); send_owner_menu(m.chat.id)
def step_save_qr(m):
    if m.photo: set_config("qr_code_id", m.photo[-1].file_id); bot.reply_to(m, "✅ Saved!")
    else: bot.reply_to(m, "❌ Image Only.")
    send_owner_menu(m.chat.id)
def step_save_logs(m):
    if m.forward_from_chat: set_config("logs_channel_id", m.forward_from_chat.id); bot.reply_to(m, "✅ Saved!")
    else: bot.reply_to(m, "❌ Forward Only.")
    send_owner_menu(m.chat.id)
def step_update_prem(m, s):
    try: get_db().execute("UPDATE users SET crazy_premium=? WHERE user_id=?", (s, int(m.text))).connection.commit(); bot.reply_to(m, "✅ Done.")
    except: bot.reply_to(m, "❌ Invalid ID")
def step_check_user(m):
    u = get_user(m.text)
    if u: bot.reply_to(m, f"🆔 `{u['user_id']}`\n👤 {u['username']}\n💎 Crazy: {u['crazy_premium']}\n💼 Plan: {u['business_plan']}", parse_mode="Markdown")
    else: bot.reply_to(m, "❌ Not Found")

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_int_"))
def set_int(c): set_config("post_interval", c.data.split("_")[2]); bot.answer_callback_query(c.id, "✅ Saved!"); send_owner_menu(c.message.chat.id, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_pr_"))
def price_sel(c):
    if "crazy" in c.data: bot.send_message(c.message.chat.id, "💰 Enter Price:"); bot.register_next_step_handler(c.message, step_save_crazy_price)
    else:
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("1 Month", callback_data="inp_1m"), types.InlineKeyboardButton("3 Month", callback_data="inp_3m"), types.InlineKeyboardButton("1 Year", callback_data="inp_1y"))
        bot.edit_message_text("Select:", c.message.chat.id, c.message.message_id, reply_markup=mk)

def step_save_crazy_price(m):
    if m.text.isdigit(): set_config("price_crazy", m.text); bot.reply_to(m, "✅ Saved!")
    else: bot.reply_to(m, "❌ Number Only.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("inp_"))
def price_save_biz(c):
    key = "price_" + c.data.split("_")[1]
    bot.send_message(c.message.chat.id, f"💰 Enter Price for {key}:")
    bot.register_next_step_handler(c.message, step_save_biz_price, key)

def step_save_biz_price(m, key):
    if m.text.isdigit(): set_config(key, m.text); bot.reply_to(m, "✅ Saved!")
    else: bot.reply_to(m, "❌ Number Only.")

@bot.callback_query_handler(func=lambda c: c.data == "confirm_reset")
def do_reset(c):
    if c.from_user.id!=OWNER_ID: return
    conn=get_db(); conn.execute("DELETE FROM users"); conn.execute("DELETE FROM owner_channels"); conn.execute("DELETE FROM force_channels"); conn.execute("DELETE FROM config"); conn.commit(); conn.close(); init_db()
    bot.edit_message_text("✅ RESET DONE", c.message.chat.id, c.message.message_id)

def start_broadcast_thread(message):
    bot.reply_to(message, "🚀 **Broadcast Started!**")
    threading.Thread(target=run_broadcast, args=(message,)).start()

def run_broadcast(message):
    conn = get_db(); users = conn.execute("SELECT user_id FROM users").fetchall(); conn.close()
    for u in users:
        try: bot.copy_message(u['user_id'], message.chat.id, message.message_id); time.sleep(0.05)
        except: pass
    bot.send_message(OWNER_ID, "✅ **Broadcast Finished!**")

def save_qr(m):
    if m.photo: set_config("qr_code_id", m.photo[-1].file_id); bot.reply_to(m, "✅ Saved!")
    else: bot.reply_to(m, "❌ Image Only.")

# --- CHANNEL ADDING LOGIC ---
@bot.callback_query_handler(func=lambda c: c.data in ["own_add_ch", "force_add_ch"])
def add_ch_prompt(c):
    bot.send_message(c.message.chat.id, "📢 **Forward Message** OR send **Username** (@channel).")
    bot.register_next_step_handler(c.message, process_ch_add, c.data)

def process_ch_add(message, mode):
    cid, title, invite = None, None, None
    if message.forward_from_chat: cid = message.forward_from_chat.id; title = message.forward_from_chat.title
    elif message.text: 
        try: c=bot.get_chat(message.text); cid=c.id; title=c.title
        except: pass
    
    if cid:
        try:
            if bot.get_chat_member(cid, bot.get_me().id).status == 'administrator':
                conn = get_db()
                if "own" in mode: conn.execute("INSERT OR IGNORE INTO owner_channels (channel_id, channel_name) VALUES (?, ?)", (cid, title))
                else:
                    try: invite = bot.create_chat_invite_link(cid, name="Bot Join").invite_link
                    except: invite = f"https://t.me/{message.text.replace('@','')}"
                    conn.execute("INSERT OR IGNORE INTO force_channels (channel_id, channel_name, invite_link) VALUES (?, ?, ?)", (cid, title, invite))
                conn.commit(); conn.close()
                bot.reply_to(message, f"✅ Added: {title}")
            else: bot.reply_to(message, "❌ Not Admin")
        except Exception as e: bot.reply_to(message, f"❌ Error: {e}")
    else: bot.reply_to(message, "❌ Invalid")

@bot.callback_query_handler(func=lambda c: c.data.endswith("_del_all"))
def del_all_ch(c):
    table = "owner_channels" if "own" in c.data else "force_channels"
    conn=get_db(); conn.execute(f"DELETE FROM {table}"); conn.commit(); conn.close()
    bot.answer_callback_query(c.id, "Deleted!")

# --- 🚀 START ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    conn=get_db()
    exists = conn.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (uid, message.from_user.username, message.from_user.first_name))
    conn.commit(); conn.close()
    
    if not exists and uid != OWNER_ID:
        try: 
            logs_ch = get_config("logs_channel_id")
            target = int(logs_ch) if logs_ch else OWNER_ID
            bot.send_message(target, f"🆕 **New User!**\n{message.from_user.first_name} (`{uid}`)", parse_mode="Markdown")
        except: pass
    
    if uid == OWNER_ID: owner_panel(message); return
    j, p = check_join_status(uid)
    if not j: bot.send_message(message.chat.id, "🚫 **Access Denied!**", reply_markup=force_join_markup(p)); return
    send_main_menu(message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data == "verify_join")
def verify(c):
    try: bot.answer_callback_query(c.id)
    except: pass
    j, p = check_join_status(c.from_user.id)
    if j: bot.delete_message(c.message.chat.id, c.message.message_id); send_main_menu(c.message.chat.id)
    else: bot.delete_message(c.message.chat.id, c.message.message_id); bot.send_message(c.message.chat.id, "❌ **Still not joined!**", reply_markup=force_join_markup(p))

def send_main_menu(chat_id):
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("💼 Business / Earn", callback_data="menu_bus"), types.InlineKeyboardButton("🛍️ Loots / Deals", callback_data="menu_loot"))
    bot.send_message(chat_id, "🌟 **Welcome!**\nSelect option:", reply_markup=mk)

# --- LOOTS MENU ---
@bot.callback_query_handler(func=lambda c: c.data == "menu_loot")
def loot_menu(c):
    if not check_join_status(c.from_user.id)[0]: return
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True); mk.add("Normal Loots", "Crazy Loots 💎")
    bot.delete_message(c.message.chat.id, c.message.message_id)
    bot.send_message(c.message.chat.id, "🛍️ **Loots Section**", reply_markup=mk)

@bot.message_handler(func=lambda m: m.text == "Normal Loots")
def normal_loots(m):
    bot.send_message(m.chat.id, "🔍 **Fetching Deals...**")
    threading.Thread(target=auto_post_task, args=(True, m.chat.id)).start()

@bot.message_handler(func=lambda m: m.text == "Crazy Loots 💎")
def crazy_loots(m):
    if not check_join_status(m.from_user.id)[0]: return
    
    # --- FIX 1: HANDLE CRASH (NoneType Error) ---
    user = get_user(m.from_user.id)
    if not user:
        bot.send_message(m.chat.id, "⚠️ **Session Expired!**\nPlease /start again to update your profile.")
        return

    if user['crazy_premium']: bot.send_message(m.chat.id, "💎 **Premium Active**\nCheck channel for exclusive deals.")
    else:
        p = get_config("price_crazy")
        mk = types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton(f"Buy @ ₹{p}", callback_data="buy_crazy"))
        bot.send_message(m.chat.id, "❌ **Premium Only**", reply_markup=mk)

# --- BUSINESS MENU ---
@bot.callback_query_handler(func=lambda c: c.data == "menu_bus")
def business_menu(c):
    if not check_join_status(c.from_user.id)[0]: return
    user = get_user(c.from_user.id)
    if user['role'] == 'business': send_bus_panel(c.message.chat.id, user, c.message.message_id)
    else:
        mk = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        mk.add(types.KeyboardButton("Share Contact 📱", request_contact=True))
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.send_message(c.message.chat.id, "⚠️ **Register First**\nShare contact to proceed.", reply_markup=mk)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        logs_ch = get_config("logs_channel_id")
        target = int(logs_ch) if logs_ch else OWNER_ID
        user_info = f"👤 **New Registration**\nName: {message.from_user.first_name}\nID: `{message.from_user.id}`\nNum: `{message.contact.phone_number}`"
        bot.send_message(target, user_info, parse_mode="Markdown")
    except: pass
    conn=get_db(); conn.execute("UPDATE users SET role='business', phone=? WHERE user_id=?", (message.contact.phone_number, message.from_user.id)); conn.commit(); conn.close()
    bot.send_message(message.chat.id, "✅ **Registered Successfully!**", reply_markup=types.ReplyKeyboardRemove())
    send_bus_panel(message.chat.id, get_user(message.from_user.id))

def send_bus_panel(chat_id, user, msg_id=None):
    mk = types.InlineKeyboardMarkup(row_width=2)
    if user['my_channel_id']: mk.add(types.InlineKeyboardButton("📢 Manage Channel", callback_data="bus_mng_ch"))
    else: mk.add(types.InlineKeyboardButton("➕ Add Channel", callback_data="bus_add_ch"))
    mk.add(types.InlineKeyboardButton("🆔 Amazon ID", callback_data="bus_set_amz"))
    plan = user['business_plan']
    if plan == 'free': mk.add(types.InlineKeyboardButton("💎 Buy Premium", callback_data="bus_buy"))
    else:
        mk.add(types.InlineKeyboardButton("✅ Active Plan", callback_data="bus_status_upgrade"))
        mk.add(types.InlineKeyboardButton("💸 EarnKaro ID", callback_data="bus_ek"))
    mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="main_back"))
    text = f"💼 **Dashboard**\nPlan: {plan.upper()}\nAmz ID: {user['user_affiliate_id'] or 'None'}"
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=mk, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "main_back")
def mb(c): bot.delete_message(c.message.chat.id, c.message.message_id); send_main_menu(c.message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bus_"))
def bus_actions(c):
    bot.answer_callback_query(c.id)
    user_id = c.from_user.id
    if c.data == "bus_add_ch":
        msg = bot.send_message(c.message.chat.id, "📢 **Forward Message** from your channel.")
        bot.register_next_step_handler(msg, user_add_ch)
    elif c.data == "bus_mng_ch":
        mk = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🗑️ Delete", callback_data="bus_del_ch"), types.InlineKeyboardButton("🔙 Back", callback_data="bus_back"))
        bot.edit_message_text("📢 **Manage Channel**", c.message.chat.id, c.message.message_id, reply_markup=mk)
    elif c.data == "bus_back": send_bus_panel(c.message.chat.id, get_user(user_id), c.message.message_id)
    elif c.data == "bus_del_ch":
        conn=get_db(); conn.execute("UPDATE users SET my_channel_id=NULL WHERE user_id=?", (user_id,)); conn.commit(); conn.close()
        send_bus_panel(c.message.chat.id, get_user(user_id), c.message.message_id)
    elif c.data == "bus_set_amz":
        msg = bot.send_message(c.message.chat.id, "🆔 Send Amazon Tag:"); bot.register_next_step_handler(msg, lambda m: [get_db().execute("UPDATE users SET user_affiliate_id=? WHERE user_id=?",(m.text, user_id)).connection.commit(), bot.reply_to(m, "✅ Saved!")])
    elif c.data == "bus_ek":
        msg = bot.send_message(c.message.chat.id, "💸 Send EarnKaro ID:"); bot.register_next_step_handler(msg, lambda m: [get_db().execute("UPDATE users SET earnkaro_id=? WHERE user_id=?",(m.text, user_id)).connection.commit(), bot.reply_to(m, "✅ Saved!")])
    elif c.data == "bus_buy":
        show_buy_options(c.message.chat.id, c.message.message_id)
    elif c.data == "bus_status_upgrade":
        user = get_user(user_id)
        plan = user['business_plan']
        mk = types.InlineKeyboardMarkup()
        p1, p3, p1y = get_config("price_1m"), get_config("price_3m"), get_config("price_1y")
        if plan == '1m': mk.row(types.InlineKeyboardButton(f"Upgrade 3M (₹{p3})", callback_data="pay_3m"), types.InlineKeyboardButton(f"Upgrade 1Y (₹{p1y})", callback_data="pay_1y"))
        elif plan == '3m': mk.add(types.InlineKeyboardButton(f"Upgrade 1Y (₹{p1y})", callback_data="pay_1y"))
        mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="bus_back"))
        bot.edit_message_text(f"✅ **Active: {plan.upper()}**\nExpiry: {user['business_expiry']}", c.message.chat.id, c.message.message_id, reply_markup=mk, parse_mode="Markdown")

def show_buy_options(chat_id, msg_id):
    p1, p3, p1y = get_config("price_1m"), get_config("price_3m"), get_config("price_1y")
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton(f"1 Month - ₹{p1}", callback_data="pay_1m"))
    mk.add(types.InlineKeyboardButton(f"3 Months - ₹{p3}", callback_data="pay_3m"))
    mk.add(types.InlineKeyboardButton(f"1 Year - ₹{p1y}", callback_data="pay_1y"))
    mk.add(types.InlineKeyboardButton("🔙 Back", callback_data="bus_back"))
    bot.edit_message_text("💎 **Select Premium Plan:**", chat_id, msg_id, reply_markup=mk, parse_mode="Markdown")

def user_add_ch(m):
    cid, title, invite = None, None, None
    if m.forward_from_chat: cid=m.forward_from_chat.id; title=m.forward_from_chat.title
    elif m.text: 
        try: c=bot.get_chat(m.text); cid=c.id; title=c.title
        except: pass
    if cid:
        try:
            if bot.get_chat_member(cid, bot.get_me().id).status=='administrator':
                conn=get_db(); conn.execute("UPDATE users SET my_channel_id=?, my_channel_name=? WHERE user_id=?",(cid,title,m.from_user.id)); conn.commit(); conn.close()
                bot.reply_to(m, f"✅ Added: {title}")
            else: bot.reply_to(m, "❌ Not Admin")
        except: bot.reply_to(m, "❌ Error")
    else: bot.reply_to(m, "❌ Invalid")

# --- PAYMENT ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_") or c.data=="buy_crazy")
def pay(c):
    qr = get_config("qr_code_id")
    if not qr: bot.send_message(c.message.chat.id, "⚠️ No QR"); return
    pl = c.data.replace("pay_","").replace("buy_","")
    mk = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📤 Send Screenshot", callback_data=f"ss_{pl}"))
    bot.send_photo(c.message.chat.id, qr, caption=f"💰 Pay for {pl}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ss_"))
def ss(c):
    msg = bot.send_message(c.message.chat.id, "📸 **Upload Screenshot:**")
    bot.register_next_step_handler(msg, send_owner_ss, c.data.split("_")[1])

def send_owner_ss(m, pl):
    if m.photo:
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"ap_{m.from_user.id}_{pl}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"rj_{m.from_user.id}"))
        bot.send_photo(OWNER_ID, m.photo[-1].file_id, caption=f"💰 User: {m.from_user.id}\nPlan: {pl}", reply_markup=mk)
        bot.reply_to(m, "✅ Sent.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ap_"))
def ap(c):
    uid, pl = int(c.data.split("_")[1]), c.data.split("_")[2]
    conn=get_db()
    if pl=="crazy": conn.execute("UPDATE users SET crazy_premium=1 WHERE user_id=?",(uid,))
    else: 
        days = 30 if pl == '1m' else 90 if pl == '3m' else 365
        exp = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        conn.execute("UPDATE users SET business_plan=?, business_expiry=? WHERE user_id=?",(pl, exp, uid))
    conn.commit(); conn.close()
    bot.edit_message_caption("✅ APPROVED", c.message.chat.id, c.message.message_id)
    try: bot.send_message(uid, f"✅ **Plan {pl.upper()} Activated!**")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("rj_"))
def rj(c):
    bot.edit_message_caption("❌ REJECTED", c.message.chat.id, c.message.message_id)
    try: bot.send_message(int(c.data.split("_")[1]), "❌ Rejected.")
    except: pass

# --- AUTO POST (FIXED FOR 2026 HEADER AUTH) ---
def auto_post_task(manual=False, chat_id=None):
    # Retrieve the Cuelinks token from the database
    token_raw = get_config("cuelinks_token")
    token = token_raw.strip() if token_raw else None
    
    caption, img = None, None
    
    # --- UPDATED AUTHENTICATION LOGIC ---
    # According to the user's snippet/2026 update, we must use:
    # Header: "Authorization: Token token=YOUR_API_KEY"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json",
        "Authorization": f"Token token={token}" if token else ""  # Secure Header Auth
    }

    if not token:
        if manual: bot.send_message(chat_id, "⚠️ No Token. Using Dummy."); 
        caption="🔥 **Demo Deal**\nPrice: ₹99\n[Buy](https://google.com)"; img=None
    else:
        try:
            # We use offers.json to GET deals, but with the NEW HEADER AUTH
            url = f"https://www.cuelinks.com/api/v2/offers.json?limit=1"
            
            # Requesting with the new Header format (Token token=...)
            r = requests.get(url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                if manual: bot.send_message(chat_id, f"❌ API Error Code: {r.status_code}\nResp: {r.text[:100]}"); return
                return
            
            data = r.json()
            if not data.get('offers'):
                if manual: bot.send_message(chat_id, "❌ API OK but No Offers."); return
                return
            o = data['offers'][0]
            caption = f"🔥 **{o['title']}**\n💰 ₹{o['price']}\n👉 [Buy]({o['url']})"; img = o.get('image_url')
        except Exception as e:
            if manual: bot.send_message(chat_id, f"❌ Cloud API Error: {e}"); return
            print(f"Post Error: {e}")
            return

    conn = get_db()
    uch = conn.execute("SELECT my_channel_id, business_plan, user_affiliate_id FROM users WHERE my_channel_id IS NOT NULL").fetchall()
    och = conn.execute("SELECT channel_id FROM owner_channels").fetchall()
    conn.close()
    
    for ch in och:
        try:
            if img: bot.send_photo(ch['channel_id'], img, caption=caption, parse_mode="Markdown")
            else: bot.send_message(ch['channel_id'], caption, parse_mode="Markdown")
        except: pass
        
    own_tag = get_config("amazon_tag")
    count = 0
    for u in uch:
        final_cap = caption
        if not final_cap: continue
        if u['business_plan'] == 'free' and random.random() < 0.2 and own_tag: final_cap = caption 
        elif u['user_affiliate_id']: final_cap = caption.replace("tag=", f"tag={u['user_affiliate_id']}")
        try:
            if img: bot.send_photo(u['my_channel_id'], img, caption=final_cap, parse_mode="Markdown")
            else: bot.send_message(u['my_channel_id'], final_cap, parse_mode="Markdown")
            count += 1
        except: pass

    if manual: bot.send_message(chat_id, f"✅ Sent to {count} user channels.")

def run_sched():
    while True:
        try:
            interval = int(get_config("post_interval") or 60)
            schedule.every(interval).minutes.do(auto_post_task)
            schedule.run_pending()
        except: pass
        time.sleep(60)

threading.Thread(target=run_sched, daemon=True).start()

print("✅ Bot Started on Cloud...")
try: bot.infinity_polling(timeout=10, long_polling_timeout=5)
except Exception as e: print(e)