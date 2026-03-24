import telebot
from telebot import types
import datetime
import os
import json
from flask import Flask, send_from_directory  # <--- ДОБАВИТЬ ЭТО

app = Flask(__name__) # <--- ДОБАВИТЬ ЭТО

@app.route('/')
def main_page():
    return send_from_directory('.', 'index') # <--- ЭТО ОТКРЫВАЕТ ТВОЙ ФАЙЛ index

import os
import json

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

ADMIN_ID =  1873195803 # <--- ВСТАВЬ СВОИ ЦИФРЫ (из @userinfobot)

# Ссылка на Mini App (ЗАМЕНИ НА СВОЮ!)
MINI_APP_URL = "https://tltakso.github.io/название-репозитория/tl-takso-app.html"

orders = {}
user_state = {}
drivers = {}
pending_drivers = {}
order_counter = [1]

def new_order_id():
    oid = f"TL{order_counter[0]:04d}"
    order_counter[0] += 1
    return oid

def now_str():
    return datetime.datetime.now().strftime("%H:%M")

def is_admin(uid):
    return uid == ADMIN_ID

def is_approved_driver(uid):
    return uid in drivers and drivers[uid].get("approved")

def get_lang(uid):
    return user_state.get(uid, {}).get("lang", "ru")

def has_active_order(driver_id):
    for order in orders.values():
        if order.get("driver_id") == driver_id and order.get("status") in ["accepted", "arrived"]:
            return True
    return False

# ── ПЕРЕВОДЫ ──
T = {
    "welcome": {
        "ru": "🚖 *TL.TAKSO*\n\nТакси по Таллинну\n• 8€ — Мустамяэ\n• 10€ — По городу\n• 15€ — Далеко\n• 20€ — Аэропорт/пригород\n\nКто вы?",
        "et": "🚖 *TL.TAKSO*\n\nTakso Tallinnas\n• 8€ — Mustamäe\n• 10€ — Linnas\n• 15€ — Kaugele\n• 20€ — Lennujaam/eeslinn\n\nKes te olete?",
        "en": "🚖 *TL.TAKSO*\n\nTaxi in Tallinn\n• 8€ — Mustamäe\n• 10€ — City\n• 15€ — Far\n• 20€ — Airport/suburb\n\nWho are you?"
    },
    "i_client": {"ru": "🚖 Я клиент", "et": "🚖 Olen klient", "en": "🚖 I'm a client"},
    "i_driver": {"ru": "🧑‍✈️ Я водитель", "et": "🧑‍✈️ Olen juht", "en": "🧑‍✈️ I'm a driver"},
    "welcome_client": {
        "ru": "👋 Добро пожаловать!\n\nНажмите кнопку чтобы заказать такси.",
        "et": "👋 Tere tulemast!\n\nVajutage nuppu takso tellimiseks.",
        "en": "👋 Welcome!\n\nPress the button to order a taxi."
    },
    "order_taxi": {"ru": "🚖 Заказать такси", "et": "🚖 Telli takso", "en": "🚖 Order taxi"},
    "my_trips": {"ru": "📋 Мои поездки", "et": "📋 Minu sõidud", "en": "📋 My trips"},
    "support": {"ru": "💬 Поддержка", "et": "💬 Tugi", "en": "💬 Support"},
    "online": {"ru": "🟢 Я онлайн", "et": "🟢 Olen online", "en": "🟢 I'm online"},
    "offline": {"ru": "⚫ Я офлайн", "et": "⚫ Olen offline", "en": "⚫ I'm offline"},
    "earnings": {"ru": "📊 Заработок сегодня", "et": "📊 Täna teenitud", "en": "📊 Today's earnings"},
    "ask_from": {"ru": "📍 Откуда едем?\n\nВведите адрес:", "et": "📍 Kust sõidate?\n\nSisestage aadress:", "en": "📍 Where from?\n\nEnter address:"},
    "ask_to": {"ru": "🏁 Куда едем?\n\nВведите адрес назначения:", "et": "🏁 Kuhu sõidate?\n\nSisestage sihtkoha aadress:", "en": "🏁 Where to?\n\nEnter destination address:"},
    "ask_time": {"ru": "⏰ Когда нужна машина?", "et": "⏰ Millal vajate autot?", "en": "⏰ When do you need the car?"},
    "now": {"ru": "⚡ Сейчас", "et": "⚡ Kohe", "en": "⚡ Now"},
    "in15": {"ru": "⏱ +15 мин", "et": "⏱ +15 min", "en": "⏱ +15 min"},
    "in30": {"ru": "⏱ +30 мин", "et": "⏱ +30 min", "en": "⏱ +30 min"},
    "ask_price": {"ru": "💰 Выберите тариф:", "et": "💰 Valige tariif:", "en": "💰 Choose tariff:"},
    "ask_payment": {"ru": "💳 Способ оплаты?", "et": "💳 Makseviis?", "en": "💳 Payment method?"},
    "card": {"ru": "💳 Карта", "et": "💳 Kaart", "en": "💳 Card"},
    "cash": {"ru": "💵 Наличные", "et": "💵 Sularaha", "en": "💵 Cash"},
    "cancel_order": {"ru": "❌ Отменить заказ", "et": "❌ Tühista tellimus", "en": "❌ Cancel order"},
    "order_cancelled": {"ru": "❌ Заказ отменён. Что-то ещё?", "et": "❌ Tellimus tühistatud. Veel midagi?", "en": "❌ Order cancelled. Anything else?"},
    "driver_cancelled": {"ru": "⚠️ Клиент отменил заказ.", "et": "⚠️ Klient tühistas tellimuse.", "en": "⚠️ Client cancelled the order."},
    "waiting": {"ru": "Ожидайте, водитель скоро примет заказ 🚖", "et": "Oodake, juht võtab tellimuse varsti vastu 🚖", "en": "Please wait, driver will accept soon 🚖"},
    "no_drivers": {"ru": "😔 Сейчас нет свободных водителей. Попробуйте через несколько минут.", "et": "😔 Praegu pole vabu juhte. Proovige mõne minuti pärast.", "en": "😔 No drivers available. Please try again in a few minutes."},
    "driver_found": {"ru": "🚖 *Водитель найден!*\n\n👤 Водитель: {name}\n🚗 Машина: {car}\n⏱ Едет к вам...", "et": "🚖 *Juht leitud!*\n\n👤 Juht: {name}\n🚗 Auto: {car}\n⏱ Sõidab teie juurde...", "en": "🚖 *Driver found!*\n\n👤 Driver: {name}\n🚗 Car: {car}\n⏱ On the way..."},
    "arrived": {"ru": "📍 *Водитель прибыл!*\n\n🚖 {name} ждёт вас. Выходите! 😊", "et": "📍 *Juht on kohal!*\n\n🚖 {name} ootab teid. Tulge välja! 😊", "en": "📍 *Driver arrived!*\n\n🚖 {name} is waiting. Please come out! 😊"},
    "trip_done": {"ru": "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!", "et": "🏁 *Sõit lõpetatud!*\n\nTäname, et valisite TL.TAKSO!", "en": "🏁 *Trip completed!*\n\nThank you for choosing TL.TAKSO!"},
    "reg_driver": {"ru": "🧑‍✈️ *Регистрация водителя*\n\nВведите ваше полное имя:", "et": "🧑‍✈️ *Juhi registreerimine*\n\nSisestage oma täisnimi:", "en": "🧑‍✈️ *Driver registration*\n\nEnter your full name:"},
    "ask_car": {"ru": "🚗 Введите марку и номер машины:\n\n_Пример: Toyota Camry · 123 ABC_", "et": "🚗 Sisestage auto mark ja number:\n\n_Näide: Toyota Camry · 123 ABC_", "en": "🚗 Enter car model and plate:\n\n_Example: Toyota Camry · 123 ABC_"},
    "ask_phone": {"ru": "📱 Введите ваш номер телефона:", "et": "📱 Sisestage oma telefoninumber:", "en": "📱 Enter your phone number:"},
    "pending": {"ru": "⏳ Ваша заявка на рассмотрении. Ожидайте одобрения.", "et": "⏳ Teie taotlus on läbivaatamisel. Oodake kinnitust.", "en": "⏳ Your application is under review. Please wait."},
    "approved": {"ru": "🎉 *Поздравляем! Ваша заявка одобрена!*\n\nНажмите '🟢 Я онлайн' чтобы начать!", "et": "🎉 *Palju õnne! Teie taotlus on kinnitatud!*\n\nVajutage '🟢 Olen online' alustamiseks!", "en": "🎉 *Congratulations! Your application is approved!*\n\nPress '🟢 I'm online' to start!"},
    "rejected": {"ru": "😔 Ваша заявка была отклонена. Обратитесь к поддержке.", "et": "😔 Teie taotlus lükati tagasi. Võtke ühendust toega.", "en": "😔 Your application was rejected. Please contact support."},
    "balance": {"ru": "💰 Ваш баланс: *{bal}€*\n\nПри наличной оплате списывается 1€ за поездку.", "et": "💰 Teie saldo: *{bal}€*\n\nSularaha maksmisel arvestatakse 1€ sõidu kohta.", "en": "💰 Your balance: *{bal}€*\n\n1€ is deducted per cash trip."},
    "low_balance": {"ru": "⚠️ Ваш баланс низкий: *{bal}€*. Пополните счёт!", "et": "⚠️ Teie saldo on madal: *{bal}€*. Täiendage kontot!", "en": "⚠️ Your balance is low: *{bal}€*. Please top up!"},
    "no_balance": {"ru": "❌ Недостаточно средств на балансе. Пополните счёт чтобы получать заказы.", "et": "❌ Kontol pole piisavalt vahendeid. Täiendage kontot tellimuste saamiseks.", "en": "❌ Insufficient balance. Top up to receive orders."},
    "driver_busy": {"ru": "⚠️ У вас уже есть активный заказ. Завершите его перед принятием нового.", "et": "⚠️ Teil on juba aktiivne tellimus. Lõpetage see enne uue vastuvõtmist.", "en": "⚠️ You already have an active order. Please complete it first."},
    "msg_sent_driver": {"ru": "✉️ Сообщение отправлено водителю", "et": "✉️ Sõnum saadetud juhile", "en": "✉️ Message sent to driver"},
    "msg_sent_client": {"ru": "✉️ Сообщение отправлено клиенту", "et": "✉️ Sõnum saadetud kliendile", "en": "✉️ Message sent to client"},
    "no_active_order": {"ru": "У вас нет активного заказа. Нажмите кнопку чтобы заказать такси 🚖", "et": "Teil pole aktiivset tellimust. Vajutage nuppu takso tellimiseks 🚖", "en": "You have no active order. Press the button to order a taxi 🚖"},
}

def t(key, uid, **kwargs):
    lang = get_lang(uid)
    text = T.get(key, {}).get(lang, T.get(key, {}).get("ru", key))
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text

# ── КЛАВИАТУРЫ ──
def lang_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("🇪🇪 Eesti", callback_data="lang_et"), types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"), types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"))
    return kb

def role_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton(t("i_client", uid), callback_data="role_client"), types.InlineKeyboardButton(t("i_driver", uid), callback_data="role_driver"))
    return kb

def main_menu_client(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("order_taxi", uid))
    kb.row(t("my_trips", uid), t("support", uid))
    return kb

def main_menu_driver(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("online", uid), t("offline", uid))
    kb.row(t("earnings", uid), t("support", uid))
    return kb

def main_menu_admin():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👥 Водители онлайн", "📋 Все заказы")
    kb.row("📊 Статистика", "🚫 Заблокировать")
    return kb

def time_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton(t("now", uid), callback_data="time_now"), types.InlineKeyboardButton(t("in15", uid), callback_data="time_15"), types.InlineKeyboardButton(t("in30", uid), callback_data="time_30"))
    return kb

def price_kb(uid):
    lang = get_lang(uid)
    city = "Город" if lang=="ru" else "Linn" if lang=="et" else "City"
    far = "Далеко" if lang=="ru" else "Kaugele" if lang=="et" else "Far"
    air = "Аэропорт" if lang=="ru" else "Lennujaam" if lang=="et" else "Airport"
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("8€ — Mustamäe", callback_data="price_8"), types.InlineKeyboardButton(f"10€ — {city}", callback_data="price_10"))
    kb.row(types.InlineKeyboardButton(f"15€ — {far}", callback_data="price_15"), types.InlineKeyboardButton(f"20€ — {air}", callback_data="price_20"))
    return kb

def payment_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton(t("card", uid), callback_data="pay_card"), types.InlineKeyboardButton(t("cash", uid), callback_data="pay_cash"))
    return kb

def driver_order_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{order_id}"), types.InlineKeyboardButton("❌ Отказать", callback_data=f"decline_{order_id}"))
    return kb

def driver_active_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📍 Я прибыл!", callback_data=f"arrived_{order_id}"))
    kb.row(types.InlineKeyboardButton("✅ Поездка завершена", callback_data=f"done_{order_id}"))
    return kb

def approve_driver_kb(driver_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{driver_id}"), types.InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{driver_id}"))
    return kb

def cancel_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("cancel_order", uid), callback_data="cancel_order"))
    return kb

def get_route_static_map(from_lat, from_lon, to_lat, to_lon):
    """Генерирует статическую карту маршрута"""
    MAPBOX_TOKEN = "pk.eyJ1IjoidGx0YWtzbyIsImEiOiJjbW4zYW0yMGkxNG13MnByM2hoZng0OXh2In0.ArR_nk-dVg99VhuuatH2hA"
    markers = f"pin-s+ff0000({from_lon},{from_lat}),pin-s+0000ff({to_lon},{to_lat})"
    return f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/{markers}/auto/600x300@2x?access_token={MAPBOX_TOKEN}"

# ── /start ──
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid = msg.from_user.id
    if is_admin(uid):
        user_state[uid] = {"role": "admin", "lang": "ru"}
        bot.send_message(uid, "👨‍💼 *Панель администратора TL.TAKSO*", parse_mode="Markdown", reply_markup=main_menu_admin())
        return
    if is_approved_driver(uid):
        user_state[uid] = {"role": "driver", "lang": get_lang(uid)}
        bot.send_message(uid, "👋", reply_markup=main_menu_driver(uid))
        return
    bot.send_message(uid, "🌍 Vali keel / Выберите язык / Choose language:", reply_markup=lang_kb())

# ── ВЫБОР ЯЗЫКА ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def cb_lang(call):
    uid = call.from_user.id
    lang = call.data.split("_")[1]
    if uid not in user_state:
        user_state[uid] = {}
    user_state[uid]["lang"] = lang
    bot.edit_message_text(t("welcome", uid), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=role_kb(uid))

# ── ВЫБОР РОЛИ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("role_"))
def cb_role(call):
    uid = call.from_user.id
    role = call.data.split("_")[1]
    if role == "client":
        user_state[uid]["role"] = "client"
        bot.edit_message_text(t("welcome_client", uid), call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "👇", reply_markup=main_menu_client(uid))
    elif role == "driver":
        if uid in pending_drivers:
            bot.edit_message_text(t("pending", uid), call.message.chat.id, call.message.message_id)
            return
        if is_approved_driver(uid):
            bot.edit_message_text("✅", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, "👇", reply_markup=main_menu_driver(uid))
            return
        user_state[uid]["role"] = "driver_reg"
        user_state[uid]["step"] = "name"
        bot.edit_message_text(t("reg_driver", uid), call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# ── РЕГИСТРАЦИЯ ВОДИТЕЛЯ ──
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "name")
def reg_name(msg):
    uid = msg.from_user.id
    user_state[uid]["full_name"] = msg.text
    user_state[uid]["step"] = "car"
    bot.send_message(uid, t("ask_car", uid), parse_mode="Markdown")

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "car")
def reg_car(msg):
    uid = msg.from_user.id
    user_state[uid]["car"] = msg.text
    user_state[uid]["step"] = "phone"
    bot.send_message(uid, t("ask_phone", uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "phone")
def reg_phone(msg):
    uid = msg.from_user.id
    state = user_state[uid]
    state["phone"] = msg.text
    state["step"] = None
    pending_drivers[uid] = {"id": uid, "full_name": state.get("full_name"), "car": state.get("car"), "phone": state.get("phone"), "username": msg.from_user.username or "—", "lang": get_lang(uid), "registered": now_str()}
    bot.send_message(uid, t("pending", uid))
    try:
        bot.send_message(ADMIN_ID, f"🔔 *Новая заявка водителя!*\n\n👤 Имя: {state['full_name']}\n🚗 Машина: {state['car']}\n📱 Телефон: {state['phone']}\n💬 Telegram: @{pending_drivers[uid]['username']}\n🌍 Язык: {get_lang(uid)}\n🕐 Время: {now_str()}", parse_mode="Markdown", reply_markup=approve_driver_kb(uid))
    except Exception as e:
        print(f"Ошибка уведомления админа: {e}")

# ── ОДОБРЕНИЕ ВОДИТЕЛЯ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
def cb_approve(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    action, driver_id = call.data.split("_", 1)
    driver_id = int(driver_id)
    pending = pending_drivers.get(driver_id)
    if not pending:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return
    if action == "approve":
        drivers[driver_id] = {"approved": True, "online": False, "full_name": pending["full_name"], "car": pending["car"], "phone": pending["phone"], "lang": pending.get("lang", "ru"), "earnings": 0, "trips": 0, "commission": 0, "balance": 10.0}
        del pending_drivers[driver_id]
        bot.edit_message_text(f"✅ Водитель *{pending['full_name']}* одобрен!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        user_state[driver_id] = {"role": "driver", "lang": pending.get("lang", "ru")}
        bot.send_message(driver_id, t("approved", driver_id), parse_mode="Markdown", reply_markup=main_menu_driver(driver_id))
    elif action == "reject":
        del pending_drivers[driver_id]
        bot.edit_message_text(f"❌ Водитель *{pending['full_name']}* отклонён.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.send_message(driver_id, t("rejected", driver_id))

# ── ЗАКАЗ ТАКСИ (НОВАЯ ВЕРСИЯ С MINI APP) ──
@bot.message_handler(func=lambda m: m.text in ["🚖 Заказать такси", "🚖 Telli takso", "🚖 Order taxi"])
def order_start(msg):
    uid = msg.from_user.id
    existing = user_state.get(uid, {}).get("current_order")
    if existing and existing in orders and orders[existing]["status"] in ["pending", "accepted", "arrived"]:
        bot.send_message(uid, "⏳ У вас уже есть активный заказ!", reply_markup=main_menu_client(uid))
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="🗺️ Выбрать на карте", web_app=types.WebAppInfo(url=MINI_APP_URL)))
    
    bot.send_message(uid, "📍 Нажмите кнопку, чтобы выбрать маршрут на карте:", reply_markup=kb)
    user_state[uid]["step"] = "waiting_webapp"

# ── ОБРАБОТКА ДАННЫХ ИЗ MINI APP ──
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(msg):
    uid = msg.from_user.id
    if user_state.get(uid, {}).get("step") != "waiting_webapp":
        return
    
    try:
        data = json.loads(msg.web_app_data.data)
        
        user_state[uid]["from_lat"] = data["from_lat"]
        user_state[uid]["from_lon"] = data["from_lon"]
        user_state[uid]["from"] = data["from_address"]
        user_state[uid]["to_lat"] = data["to_lat"]
        user_state[uid]["to_lon"] = data["to_lon"]
        user_state[uid]["to"] = data["to_address"]
        user_state[uid]["time"] = data["time"]
        user_state[uid]["payment"] = data["payment"]
        user_state[uid]["price"] = data["price"]
        
        oid = new_order_id()
        
        orders[oid] = {
            "id": oid, "client_id": uid, "client_name": msg.from_user.first_name,
            "from": data["from_address"], "to": data["to_address"],
            "from_lat": data["from_lat"], "from_lon": data["from_lon"],
            "to_lat": data["to_lat"], "to_lon": data["to_lon"],
            "time": data["time"], "payment": "💳 Карта" if data["payment"] == "card" else "💵 Наличные",
            "pay_type": data["payment"], "price": data["price"],
            "driver_gets": data["driver_gets"], "status": "pending",
            "created": now_str(), "driver_id": None, "client_lang": get_lang(uid)
        }
        
        user_state[uid]["current_order"] = oid
        user_state[uid]["step"] = None
        
        bot.send_message(uid, f"✅ *Заказ #{oid} создан!*\n\n📍 {data['from_address'][:50]}\n🏁 {data['to_address'][:50]}\n💰 *{data['price']}€*\n\n⏳ Ищем водителя...", parse_mode="Markdown", reply_markup=main_menu_client(uid))
        
        notify_drivers(oid)
        
    except Exception as e:
        print(f"WebApp error: {e}")
        bot.send_message(uid, "❌ Ошибка обработки заказа")

def notify_drivers(oid):
    order = orders[oid]
    
    route_map = None
    if order.get("from_lat") and order.get("to_lat"):
        route_map = get_route_static_map(order["from_lat"], order["from_lon"], order["to_lat"], order["to_lon"])
    
    text = (f"🔔 *Новый заказ #{oid}*\n\n👤 {order['client_name']}\n📍 {order['from']}\n🏁 {order['to']}\n⏰ {order['time']}\n💳 {order['payment']}\n💰 Ваш заработок: *{order['driver_gets']}€*\n🕐 {order['created']}")
    
    sent = 0
    for driver_id, d in drivers.items():
        if not (d.get("online") and d.get("approved")):
            continue
        if d.get("balance", 0) <= 0:
            bot.send_message(driver_id, t("no_balance", driver_id))
            continue
        if has_active_order(driver_id):
            continue
        try:
            if route_map:
                bot.send_photo(driver_id, route_map, caption=text, parse_mode="Markdown", reply_markup=driver_order_kb(oid))
            else:
                bot.send_message(driver_id, text, parse_mode="Markdown", reply_markup=driver_order_kb(oid))
            sent += 1
        except Exception as e:
            print(f"Ошибка отправки водителю {driver_id}: {e}")
    if sent == 0:
        bot.send_message(order["client_id"], t("no_drivers", order["client_id"]))

# ── ПРИНЯТЬ / ОТКАЗАТЬ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_") or c.data.startswith("decline_"))
def cb_driver_response(call):
    driver_id = call.from_user.id
    if not is_approved_driver(driver_id):
        bot.answer_callback_query(call.id, "⛔")
        return
    action, oid = call.data.split("_", 1)
    order = orders.get(oid)
    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден")
        return
    if order["status"] != "pending":
        bot.answer_callback_query(call.id, "Уже принят")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return
    if action == "accept":
        if has_active_order(driver_id):
            bot.answer_callback_query(call.id, t("driver_busy", driver_id))
            return
        order["status"] = "accepted"
        order["driver_id"] = driver_id
        order["driver_name"] = drivers[driver_id]["full_name"]
        drivers[driver_id]["trips"] += 1
        drivers[driver_id]["earnings"] += order["driver_gets"]
        drivers[driver_id]["commission"] += 1
        if order.get("pay_type") == "cash":
            drivers[driver_id]["balance"] = round(drivers[driver_id].get("balance", 0) - 1, 2)
            if drivers[driver_id]["balance"] <= 3:
                bot.send_message(driver_id, t("low_balance", driver_id, bal=drivers[driver_id]["balance"]), parse_mode="Markdown")
        bot.edit_message_text(f"✅ *Заказ #{oid}*\n\n👤 {order['client_name']}\n📍 {order['from']}\n🏁 {order['to']}\n💳 {order['payment']}\n💰 {order['driver_gets']}€\n\n📍 Нажмите когда прибудете!", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=driver_active_kb(oid))
        client_id = order["client_id"]
        bot.send_message(client_id, t("driver_found", client_id, name=drivers[driver_id]["full_name"], car=drivers[driver_id]["car"]), parse_mode="Markdown")
    elif action == "decline":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Отклонён")

# ── Я ПРИБЫЛ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("arrived_"))
def cb_arrived(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if not order:
        return
    if order["status"] == "arrived":
        bot.answer_callback_query(call.id, "✅ Уже отправлено")
        return
    order["status"] = "arrived"
    bot.answer_callback_query(call.id, "✅ Клиент уведомлён!")
    client_id = order["client_id"]
    bot.send_message(client_id, t("arrived", client_id, name=order["driver_name"]), parse_mode="Markdown")

# ── ПОЕЗДКА ЗАВЕРШЕНА ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if not order:
        return
    if order["status"] == "done":
        bot.answer_callback_query(call.id, "✅ Уже завершено")
        return
    order["status"] = "done"
    bot.edit_message_text(f"✅ *Поездка #{oid} завершена!*\n\n💰 {order['driver_gets']}€\nСпасибо! 🚖", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    client_id = order["client_id"]
    bot.send_message(client_id, t("trip_done", client_id), parse_mode="Markdown", reply_markup=main_menu_client(client_id))

# ── СТАТУС ВОДИТЕЛЯ ──
@bot.message_handler(func=lambda m: m.text in ["🟢 Я онлайн", "🟢 Olen online", "🟢 I'm online"])
def driver_online(msg):
    uid = msg.from_user.id
    if not is_approved_driver(uid):
        return
    drivers[uid]["online"] = True
    bot.send_message(uid, t("online", uid), reply_markup=main_menu_driver(uid))

@bot.message_handler(func=lambda m: m.text in ["⚫ Я офлайн", "⚫ Olen offline", "⚫ I'm offline"])
def driver_offline(msg):
    uid = msg.from_user.id
    if not is_approved_driver(uid):
        return
    drivers[uid]["online"] = False
    bot.send_message(uid, t("offline", uid), reply_markup=main_menu_driver(uid))

# ── ЗАРАБОТОК ──
@bot.message_handler(func=lambda m: m.text in ["📊 Заработок сегодня", "📊 Täna teenitud", "📊 Today's earnings"])
def driver_earnings(msg):
    uid = msg.from_user.id
    if not is_approved_driver(uid):
        return
    d = drivers[uid]
    commission = d.get("commission", d["trips"])
    bot.send_message(uid, f"{t('balance', uid, bal=d.get('balance', 0))}\n\n🚖 Поездок: {d['trips']}\n💰 Заработано: {d['earnings']}€\n📦 Сбор TL.TAKSO: {commission}€", parse_mode="Markdown", reply_markup=main_menu_driver(uid))

# ── ОТМЕНА ЗАКАЗА ──
@bot.callback_query_handler(func=lambda c: c.data == "cancel_order")
def cb_cancel(call):
    uid = call.from_user.id
    oid = user_state.get(uid, {}).get("current_order")
    if oid and oid in orders:
        order = orders[oid]
        if order["status"] in ["pending", "accepted", "arrived"]:
            order["status"] = "cancelled"
            driver_id = order.get("driver_id")
            if driver_id:
                try:
                    bot.send_message(driver_id, t("driver_cancelled", driver_id))
                except:
                    pass
    bot.edit_message_text(t("order_cancelled", uid), call.message.chat.id, call.message.message_id)
    bot.send_message(uid, t("order_cancelled", uid), reply_markup=main_menu_client(uid))

# ── АДМИН ПАНЕЛЬ ──
@bot.message_handler(func=lambda m: m.text == "👥 Водители онлайн" and is_admin(m.from_user.id))
def admin_drivers(msg):
    online = [(uid, d) for uid, d in drivers.items() if d.get("online") and d.get("approved")]
    if not online:
        bot.send_message(msg.chat.id, "😔 Нет водителей онлайн", reply_markup=main_menu_admin())
        return
    text = f"🟢 *Онлайн: {len(online)}*\n\n"
    for uid, d in online:
        busy = "🚖 Занят" if has_active_order(uid) else "✅ Свободен"
        text += f"👤 {d['full_name']}\n🚗 {d['car']}\n📱 {d['phone']}\n💰 Баланс: {d.get('balance',0)}€\n{busy}\n\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "📋 Все заказы" and is_admin(m.from_user.id))
def admin_orders(msg):
    if not orders:
        bot.send_message(msg.chat.id, "📋 Заказов нет", reply_markup=main_menu_admin())
        return
    text = f"📋 *Заказов: {len(orders)}*\n\n"
    status_map = {"pending":"⏳","accepted":"🚖","arrived":"📍","done":"✅","cancelled":"❌"}
    for oid, o in list(orders.items())[-10:]:
        st = status_map.get(o['status'], '?')
        text += f"{st} #{oid} · {o['client_name']} · {o['price']}€\n{o['from']} → {o['to']}\n\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and is_admin(m.from_user.id))
def admin_stats(msg):
    total = len(orders)
    done = len([o for o in orders.values() if o['status'] == 'done'])
    revenue = sum(d.get("commission", 0) for d in drivers.values())
    all_drv = len(drivers)
    online = len([d for d in drivers.values() if d.get("online")])
    pending = len(pending_drivers)
    bot.send_message(msg.chat.id, f"📊 *Статистика TL.TAKSO*\n\n🚖 Всего заказов: {total}\n✅ Завершено: {done}\n💰 Сбор TL.TAKSO: {revenue}€\n\n👥 Водителей: {all_drv}\n🟢 Онлайн: {online}\n⏳ Ждут одобрения: {pending}", parse_mode="Markdown", reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "🚫 Заблокировать" and is_admin(m.from_user.id))
def admin_block(msg):
    approved = [(uid, d) for uid, d in drivers.items() if d.get("approved")]
    if not approved:
        bot.send_message(msg.chat.id, "Водителей нет", reply_markup=main_menu_admin())
        return
    kb = types.InlineKeyboardMarkup()
    for uid, d in approved:
        kb.add(types.InlineKeyboardButton(f"🚫 {d['full_name']} · {d['car']}", callback_data=f"block_{uid}"))
    bot.send_message(msg.chat.id, "Выберите водителя:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("block_"))
def cb_block(call):
    if not is_admin(call.from_user.id):
        return
    driver_id = int(call.data.split("_")[1])
    if driver_id in drivers:
        name = drivers[driver_id]['full_name']
        drivers[driver_id]['approved'] = False
        drivers[driver_id]['online'] = False
        bot.edit_message_text(f"🚫 *{name}* заблокирован.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        try:
            bot.send_message(driver_id, "⛔ Ваш аккаунт заблокирован. Обратитесь к администратору.")
        except:
            pass

# ── ЧАТ ──
IGNORE = ["🚖 Заказать такси","🚖 Telli takso","🚖 Order taxi", "📋 Мои поездки","📋 Minu sõidud","📋 My trips", "💬 Поддержка","💬 Tugi","💬 Support", "🟢 Я онлайн","🟢 Olen online","🟢 I'm online", "⚫ Я офлайн","⚫ Olen offline","⚫ I'm offline", "📊 Заработок сегодня","📊 Täna teenitud","📊 Today's earnings", "👥 Водители онлайн","📋 Все заказы","📊 Статистика","🚫 Заблокировать"]

@bot.message_handler(func=lambda m: (user_state.get(m.from_user.id, {}).get("role") in ["client","driver"] and user_state.get(m.from_user.id, {}).get("step") not in ["from","to","name","car","phone"] and m.text and not m.text.startswith("/") and m.text not in IGNORE))
def relay_message(msg):
    uid = msg.from_user.id
    role = user_state.get(uid, {}).get("role")
    if role == "client":
        oid = user_state[uid].get("current_order")
        if oid and oid in orders:
            order = orders[oid]
            if order["status"] in ["accepted","arrived"]:
                driver_id = order.get("driver_id")
                if driver_id:
                    bot.send_message(driver_id, f"💬 *{msg.from_user.first_name}:*\n{msg.text}", parse_mode="Markdown")
                    bot.send_message(uid, t("msg_sent_driver", uid))
                    return
            elif order["status"] == "pending":
                bot.send_message(uid, "⏳ " + t("waiting", uid))
                return
        bot.send_message(uid, t("no_active_order", uid), reply_markup=main_menu_client(uid))
    elif role == "driver":
        for oid, order in orders.items():
            if order.get("driver_id") == uid and order.get("status") in ["accepted","arrived"]:
                bot.send_message(order["client_id"], f"💬 *{msg.from_user.first_name}:*\n{msg.text}", parse_mode="Markdown")
                bot.send_message(uid, t("msg_sent_client", uid))
                return
        bot.send_message(uid, "—", reply_markup=main_menu_driver(uid))

# ── ПОДДЕРЖКА ──
@bot.message_handler(func=lambda m: m.text in ["💬 Поддержка","💬 Tugi","💬 Support"])
def support(msg):
    bot.send_message(msg.chat.id, "📞 TL.TAKSO support: @tltakso_support")
# ── ЗАПУСК ──
if __name__ == "__main__":
    print("🚖 TL.TAKSO Bot запущен!")
    from threading import Thread
    def run_bot():
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
