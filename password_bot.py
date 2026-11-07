import telebot
from telebot import types
import random
import string
import math
import sqlite3
import time

# === НАСТРОЙКИ ===
TOKEN = "8541203372:AAFbKxzI-opzdHfEl-d5lQ1UxIyhvjgtaAs"
bot = telebot.TeleBot(TOKEN)

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('passwords.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, gems INTEGER DEFAULT 0, ref_id INTEGER DEFAULT 0)''')
conn.commit()

# --- ФУНКЦИИ ГЕНЕРАЦИИ ---
def gen_simple():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(8))

def gen_memorable():
    words = ["Apple", "Tiger", "Sky", "Moon", "Fire", "Water", "Rock", "Star", "Wolf", "Sun"]
    return f"{random.choice(words)}{random.choice(words)}{random.randint(10,99)}!{random.choice(string.ascii_uppercase)}"

def check_strength(password):
    length = len(password)
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in string.punctuation for c in password)
    
    score = 0
    if length >= 8: score += 1
    if length >= 12: score += 1
    if has_upper: score += 1
    if has_lower: score += 1
    if has_digit: score += 1
    if has_special: score += 1
    
    if score <= 2: return "Слабый 🟥"
    elif score <= 4: return "Средний 🟨"
    else: return "Сложный 🟩"

# --- КЛАВИАТУРЫ ---
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔑 Простой пароль (1 гем)", callback_data="gen_simple"),
        types.InlineKeyboardButton("🧠 Сложный, но запоминающийся (2 гема)", callback_data="gen_memorable"),
        types.InlineKeyboardButton("🕵️ Проверить пароль на утечки (5 гемов)", callback_data="check_leak"),
        types.InlineKeyboardButton("💀 Сколько взламывают мой пароль? (Бесплатно)", callback_data="crack_time"),
        types.InlineKeyboardButton("💰 Купить гемы / Рефералка / Подписка", callback_data="earn_gems")
    )
    return markup

# --- ХЕНДЛЕРЫ ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    cursor.execute("SELECT gems FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO users (user_id, gems) VALUES (?, ?)", (user_id, 10))
        conn.commit()
        bot.send_message(message.chat.id, f"Привет! Я бот-генератор паролей. Твой ранг: Новичок. Тебе начислено 10 гемов для старта!")
    else:
        bot.send_message(message.chat.id, f"С возвращением! У тебя {res[0]} гемов.")

    bot.send_message(message.chat.id, "Выбери действие:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    user_id = call.from_user.id
    
    cursor.execute("SELECT gems FROM users WHERE user_id = ?", (user_id,))
    gems = cursor.fetchone()[0]

    if call.data == "gen_simple":
        if gems < 1:
            bot.answer_callback_query(call.id, "Недостаточно гемов! Заработай их в меню 'Купить гемы'.", show_alert=True)
            return
        password = gen_simple()
        cursor.execute("UPDATE users SET gems = gems - 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        rank = check_strength(password)
        bot.edit_message_text(f"🔑 Пароль: `{password}`\nРанг: {rank}\nОсталось гемов: {gems-1}", 
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu())

    elif call.data == "gen_memorable":
        if gems < 2:
            bot.answer_callback_query(call.id, "Недостаточно гемов!", show_alert=True)
            return
        password = gen_memorable()
        cursor.execute("UPDATE users SET gems = gems - 2 WHERE user_id = ?", (user_id,))
        conn.commit()
        rank = check_strength(password)
        bot.edit_message_text(f"🧠 Пароль: `{password}`\nРанг: {rank}\nОсталось гемов: {gems-2}", 
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu())

    elif call.data == "check_leak":
        if gems < 5:
            bot.answer_callback_query(call.id, "Недостаточно гемов!", show_alert=True)
            return
        cursor.execute("UPDATE users SET gems = gems - 5 WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.edit_message_text(f"🕵️ Твой пароль проверен! (Заглушка)\nОсталось гемов: {gems-5}", 
                              call.message.chat.id, call.message.message_id, reply_markup=main_menu())

    elif call.data == "crack_time":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Введи свой пароль, и я скажу, сколько лет его будут взламывать:")
        bot.register_next_step_handler(msg, calculate_crack_time)

    elif call.data == "earn_gems":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👥 Пригласить друга (Рефералка)", callback_data="ref_link"),
            types.InlineKeyboardButton("📢 Подписаться на @bubmagnat", url="https://t.me/bubmagnat"),
            types.InlineKeyboardButton("⭐ Купить гемы за звезды", callback_data="buy_stars")
        )
        bot.edit_message_text("Выбери способ заработка гемов:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "ref_link":
        bot.answer_callback_query(call.id, "Скоро тут будет ссылка! Пока не работает.", show_alert=True)

    elif call.data == "buy_stars":
        bot.answer_callback_query(call.id, "Оплата звездами скоро будет доступна!", show_alert=True)

def calculate_crack_time(message):
    password = message.text
    charset_size = 0
    if any(c.islower() for c in password): charset_size += 26
    if any(c.isupper() for c in password): charset_size += 26
    if any(c.isdigit() for c in password): charset_size += 10
    if any(c in string.punctuation for c in password): charset_size += 32
    
    if charset_size == 0: charset_size = 1
    combinations = charset_size ** len(password)
    
    seconds = combinations / 10_000_000_000
    years = seconds / (60 * 60 * 24 * 365)
    
    if years > 1_000_000:
        time_str = f"{years / 1_000_000:.2f} миллионов лет"
    elif years > 1:
        time_str = f"{years:.2f} лет"
    elif seconds > 3600:
        time_str = f"{seconds/3600:.2f} часов"
    else:
        time_str = f"{seconds:.2f} секунд"
    
    rank = check_strength(password)
    bot.reply_to(message, f"💀 Твой пароль взломают за: **{time_str}**\nРанг пароля: {rank}\n\n(Игрушка бесплатная, можешь проверять сколько хочешь!)", parse_mode="Markdown")

print("Бот запущен...")
bot.infinity_polling()
