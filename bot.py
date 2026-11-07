import telebot
from telebot import types
import sqlite3
import random
import os
from flask import Flask
from threading import Thread

# === НАСТРОЙКИ ===
TOKEN = "8541203372:AAFbKxzI-opzdHfEl-d5lQ1UxIyhvjgtaAs"
ADMIN_ID = 8192413936  # Твой ID
bot = telebot.TeleBot(TOKEN)

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is alive"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
def keep_alive(): Thread(target=run_flask).start()

# === БАЗА ДАННЫХ ===
conn = sqlite3.connect('roulette.db', check_same_thread=False)
cursor = conn.cursor()
# Добавил колонку nickname в базу
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, nickname TEXT, gems INTEGER DEFAULT 10, banned INTEGER DEFAULT 0, rating INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS queue (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS active_chats (user1 INTEGER, user2 INTEGER)''')
conn.commit()

# Временный словарь для тех, кто вводит ник
registering_users = {}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def get_user(uid):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    return cursor.fetchone()

def get_partner(uid):
    cursor.execute("SELECT user2 FROM active_chats WHERE user1 = ?", (uid,))
    res = cursor.fetchone()
    if res: return res[0]
    cursor.execute("SELECT user1 FROM active_chats WHERE user2 = ?", (uid,))
    res = cursor.fetchone()
    return res[0] if res else None

def end_chat(uid, reason="Собеседник завершил чат."):
    partner = get_partner(uid)
    if partner:
        cursor.execute("DELETE FROM active_chats WHERE user1 = ? OR user2 = ?", (uid, uid))
        conn.commit()
        bot.send_message(uid, f"🛑 {reason}", reply_markup=main_menu())
        bot.send_message(partner, f"🛑 {reason}", reply_markup=main_menu())
        return True
    return False

# === КЛАВИАТУРЫ ===
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🔍 Искать собеседника", "👤 Моя анкета")
    markup.add("📖 Помощь")
    return markup

def chat_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛑 Завершить", callback_data="stop_chat"),
        types.InlineKeyboardButton("🚨 Жалоба", callback_data="report_start"),
        types.InlineKeyboardButton("👍 Лайк", callback_data="rate_like"),
        types.InlineKeyboardButton("👎 Дизлайк", callback_data="rate_dislike")
    )
    return markup

# === СТАРТ И РЕГИСТРАЦИЯ ===
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    user = get_user(uid)
    
    # Если юзера нет в базе ИЛИ у него нет ника
    if not user or not user[1]: 
        registering_users[uid] = True
        bot.send_message(uid, "👋 Привет! Давай зарегистрируемся.\n\nПридумай себе ник (от 4 до 16 символов, только буквы и цифры):", reply_markup=types.ReplyKeyboardRemove())
    else:
        if user[3] == 1:
            bot.send_message(uid, "🚫 Ты забанен.")
            return
        bot.send_message(uid, f"С возвращением, {user[1]}!", reply_markup=main_menu())

# === ОБРАБОТКА ВСЕХ ТЕКСТОВ ===
@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'voice'])
def handle_messages(message):
    uid = message.from_user.id
    
    # --- ЕСЛИ В ПРОЦЕССЕ РЕГИСТРАЦИИ ---
    if uid in registering_users:
        nick = message.text.strip()
        if 4 <= len(nick) <= 16 and nick.isalnum():
            user = get_user(uid)
            if user:
                cursor.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nick, uid))
            else:
                cursor.execute("INSERT INTO users (user_id, nickname) VALUES (?, ?)", (uid, nick))
            conn.commit()
            del registering_users[uid]
            bot.send_message(uid, f"✅ Отлично, {nick}! Ты зарегистрирован. Теперь ищи собеседника!", reply_markup=main_menu())
        else:
            bot.send_message(uid, "❌ Ник должен быть от 4 до 16 символов (только буквы и цифры). Попробуй еще раз:")
        return

    # --- ОБЫЧНЫЕ КОМАНДЫ ---
    if message.text == "🔍 Искать собеседника":
        find_partner(message)
        return
    elif message.text == "👤 Моя анкета":
        show_profile(message)
        return
    elif message.text == "📖 Помощь":
        bot.send_message(uid, "📖 **Помощь**\n\n🔍 Ищи собеседника кнопкой ниже.\n🛑 /stop - завершить чат.\n🚨 /pol - пожаловаться.", parse_mode="Markdown", reply_markup=main_menu())
        return

    # --- ОБЫЧНЫЙ ЧАТ ---
    partner = get_partner(uid)
    if partner:
        if message.text == "/stop":
            end_chat(uid)
        elif message.text == "/pol":
            report_start_logic(uid)
        else:
            try:
                bot.copy_message(partner, uid, message.message_id)
            except:
                bot.send_message(uid, "⚠️ Ошибка. Возможно, собеседник заблокировал бота.")
                end_chat(uid, "Собеседник отключился.")
    else:
        # Если просто пишет текст вне чата и не в меню
        bot.send_message(uid, "❌ Ты не в чате. Нажми '🔍 Искать собеседника' или /start", reply_markup=main_menu())

# === ПОИСК ===
def find_partner(message):
    uid = message.from_user.id
    if get_partner(uid):
        bot.send_message(uid, "⚠️ Ты уже в чате!")
        return

    cursor.execute("SELECT user_id FROM queue WHERE user_id != ?", (uid,))
    partner = cursor.fetchone()
    
    if partner:
        partner_id = partner[0]
        cursor.execute("DELETE FROM queue WHERE user_id = ?", (partner_id,))
        cursor.execute("INSERT INTO active_chats (user1, user2) VALUES (?, ?)", (uid, partner_id))
        conn.commit()
        
        bot.send_message(uid, "✅ Собеседник найден! Общайтесь.\n/stop - чтобы выйти.", reply_markup=chat_menu())
        bot.send_message(partner_id, "✅ Собеседник найден! Общайтесь.\n/stop - чтобы выйти.", reply_markup=chat_menu())
    else:
        cursor.execute("INSERT OR IGNORE INTO queue (user_id) VALUES (?)", (uid,))
        conn.commit()
        bot.send_message(uid, "⏳ Ищем собеседника... Ожидай.")

def show_profile(message):
    uid = message.from_user.id
    user = get_user(uid)
    if user:
        bot.send_message(uid, f"👤 **Твой профиль**\nНик: {user[1]}\nID: `{uid}`\n💎 Гемы: {user[2]}\n👍 Рейтинг: {user[4]}", parse_mode="Markdown", reply_markup=main_menu())

# === ЖАЛОБЫ ===
def report_start_logic(uid):
    partner_id = get_partner(uid)
    if not partner_id: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🤬 Оскорбления / Мат", callback_data=f"rep_insult_{partner_id}"),
        types.InlineKeyboardButton("🔞 18+ / Порно", callback_data=f"rep_nsfw_{partner_id}"),
        types.InlineKeyboardButton("💊 Наркотики / Спам", callback_data=f"rep_spam_{partner_id}"),
        types.InlineKeyboardButton("📞 Слив личных данных", callback_data=f"rep_dox_{partner_id}")
    )
    bot.send_message(uid, "Выбери причину жалобы:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rep_"))
def report_process(call):
    data = call.data.split("_")
    reason_code, violator_id = data[1], int(data[2])
    reporter_id = call.from_user.id
    reasons = {"insult": "🤬 Оскорбления", "nsfw": "🔞 18+", "spam": "💊 Спам", "dox": "📞 Слив данных"}
    
    admin_text = f"🚨 **ЖАЛОБА**\nПричина: {reasons.get(reason_code)}\n\n**Отправитель:** `{reporter_id}`\n**Нарушитель:** `{violator_id}`"
    admin_markup = types.InlineKeyboardMarkup()
    admin_markup.add(types.InlineKeyboardButton("🔨 Забанить", callback_data=f"admin_ban_{violator_id}"), types.InlineKeyboardButton("✅ Игнор", callback_data="admin_ignore"))
    
    bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup)
    bot.answer_callback_query(call.id, "✅ Жалоба отправлена!", show_alert=True)
    end_chat(reporter_id, "Чат завершен из-за жалобы.")

# === КНОПКИ В ЧАТЕ ===
@bot.callback_query_handler(func=lambda call: call.data in ["stop_chat", "rate_like", "rate_dislike"])
def chat_actions(call):
    uid = call.from_user.id
    if call.data == "stop_chat":
        if end_chat(uid): bot.answer_callback_query(call.id, "Чат завершен.")
    elif call.data == "rate_like":
        partner = get_partner(uid)
        if partner:
            cursor.execute("UPDATE users SET rating = rating + 1 WHERE user_id = ?", (partner,))
            conn.commit()
            bot.answer_callback_query(call.id, "👍 Лайк отправлен!")
    elif call.data == "rate_dislike":
        partner = get_partner(uid)
        if partner:
            cursor.execute("UPDATE users SET rating = rating - 1 WHERE user_id = ?", (partner,))
            conn.commit()
            bot.answer_callback_query(call.id, "👎 Дизлайк отправлен!")

# === АДМИН ПАНЕЛЬ ===
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"), types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"))
    bot.send_message(ADMIN_ID, "👑 **Админ-панель**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    if call.data == "admin_ignore":
        bot.edit_message_text("Жалоба проигнорирована.", call.message.chat.id, call.message.message_id)
    elif call.data.startswith("admin_ban_"):
        ban_id = int(call.data.split("_")[2])
        cursor.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (ban_id,))
        conn.commit()
        end_chat(ban_id, "Вы были забанены.")
        bot.edit_message_text(f"✅ Юзер `{ban_id}` забанен.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    elif call.data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users"); u = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM active_chats"); c = cursor.fetchone()[0]
        bot.answer_callback_query(call.id, f"Юзеров: {u}\nАктивных чатов: {c}", show_alert=True)
    elif call.data == "admin_broadcast":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(ADMIN_ID, "Введи текст для рассылки (или /cancel):")
        bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    if message.text == "/cancel": return
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    success = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **Сообщение от админа:**\n\n{message.text}", parse_mode="Markdown")
            success += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Рассылка завершена. Доставлено: {success}")

# === ЗАПУСК ===
if __name__ == '__main__':
    keep_alive()
    print("Бот запущен...")
    bot.infinity_polling()
