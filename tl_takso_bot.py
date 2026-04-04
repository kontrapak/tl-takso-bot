import telebot
from telebot import types
import datetime
import os
import json
import time
import threading
from flask import Flask, send_from_directory, request, abort
import re

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ КОНФИГУРАЦИЯ ══════════════════════════════
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен в переменных окружения")

MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN")
if not MAPBOX_TOKEN:
    raise ValueError("❌ MAPBOX_TOKEN не установлен")

RAILWAY_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or os.environ.get("RAILWAY_STATIC_URL")
if not RAILWAY_DOMAIN:
    raise ValueError("❌ RAILWAY_PUBLIC_DOMAIN не установлен")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", BOT_TOKEN.split(':')[1][:16])
MINI_APP_URL = f"https://{RAILWAY_DOMAIN}/static/miniapp.html"
DRIVER_MAP_URL = f"https://{RAILWAY_DOMAIN}/static/driver.html"

ADMIN_ID = int(os.environ.get("ADMIN_ID", "1873195803"))

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ СОХРАНЕНИЕ ДАННЫХ ═════════════════════════
# ═══════════════════════════════════════════════════════════════

DATA_FILE = "/mnt/data/tltakso_data.json"
data_lock = threading.Lock()

def save_data():
    with data_lock:
        data = {
            "orders": orders,
            "user_state": {str(k): v for k, v in user_state.items()},
            "drivers": {str(k): v for k, v in drivers.items()},
            "pending_drivers": {str(k): v for k, v in pending_drivers.items()},
            "order_counter": order_counter[0],
            "saved_at": datetime.datetime.now().isoformat()
        }
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            temp_file = DATA_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, DATA_FILE)
            print(f"💾 Данные сохранены: {len(orders)} заказов")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")

def load_data():
    global orders, user_state, drivers, pending_drivers, order_counter
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            orders = data.get("orders", {})
            user_state = {int(k): v for k, v in data.get("user_state", {}).items()}
            drivers = {int(k): v for k, v in data.get("drivers", {}).items()}
            pending_drivers = {int(k): v for k, v in data.get("pending_drivers", {}).items()}
            order_counter[0] = data.get("order_counter", 1)
            print(f"📂 Данные загружены: {len(orders)} заказов")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")

def auto_save():
    while True:
        time.sleep(60)
        save_data()

orders = {}
user_state = {}
drivers = {}
pending_drivers = {}
order_counter = [1]

load_data()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Инициализация админа
if ADMIN_ID not in drivers:
    drivers[ADMIN_ID] = {
        "approved": True, "online": True, "full_name": "S.L.",
        "car": "Toyota Camry", "phone": "+123456789", "lang": "ru",
        "earnings": 0, "trips": 0, "commission": 0, "balance": 50.0
    }

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ FLASK ROUTES ══════════════════════════════
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/api/orders', methods=['GET'])
def api_orders():
    result = []
    for oid, order in orders.items():
        if order.get('status') == 'pending':
            result.append({
                'id': oid,
                'price': order.get('price', 0),
                'from_address': order.get('from', '—'),
                'to_address': order.get('to', '—')
            })
    return json.dumps(result, ensure_ascii=False)

@app.route('/api/orders/<order_id>/accept', methods=['PUT'])
def api_accept_order(order_id):
    # order_id приходит как строка "TL0001"
    if order_id in orders and orders[order_id]['status'] == 'pending':
        orders[order_id]['status'] = 'accepted'
        save_data()
        return json.dumps({'ok': True})
    return json.dumps({'ok': False}), 400

@app.route(f'/webhook/{WEBHOOK_SECRET}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        except Exception as e:
            print(f"❌ Ошибка webhook: {e}")
            return '', 500
    return abort(403)

@app.route('/health')
def health_check():
    return {'status': 'ok', 'orders': len(orders), 'drivers': len(drivers)}, 200

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ═══════════════════
# ═══════════════════════════════════════════════════════════════

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
    if driver_id is None:
        return False
    for order in orders.values():
        if order.get("driver_id") == driver_id and order.get("status") in ["accepted", "arrived"]:
            return True
    return False

def get_route_static_map(from_lat, from_lon, to_lat, to_lon):
    if not all([from_lat, from_lon, to_lat, to_lon]):
        return None
    markers = f"pin-s+ff0000({from_lon},{from_lat}),pin-s+0000ff({to_lon},{to_lat})"
    return f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/{markers}/auto/600x300@2x?access_token={MAPBOX_TOKEN}"

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ ПЕРЕВОДЫ ══════════════════════════════════
# ═══════════════════════════════════════════════════════════════

T = {
    "welcome": {
        "ru": "🚖 *TL.TAKSO*\n\nТакси по Таллинну\n• 8€ — Мустамяэ\n• 10€ — По городу\n• 15€ — Далеко\n• 20€ — Аэропорт/пригород\n\nКто вы?",
        "et": "🚖 *TL.TAKSO*\n\nTakso Tallinnas\n• 8€ — Mustamäe\n• 10€ — Linnas\n• 15€ — Kaugele\n• 20€ — Lennujaam/eeslinn\n\nKes te olete?",
        "en": "🚖 *TL.TAKSO*\n\nTaxi in Tallinn\n• 8€ — Mustamäe\n• 10€ — City\n• 15€ — Far\n• 20€ — Airport/suburb\n\nWho are you?"
    },
    "i_client": {"ru": "🚖 Я клиент", "et": "🚖 Olen klient", "en": "🚖 I'm a client"},
    "i_driver": {"ru": "🧑‍✈️ Я водитель", "et": "🧑‍✈️ Olen juht", "en": "🧑‍✈️ I'm a driver"},
    "welcome_client": {"ru": "👋 Добро пожаловать!\n\nНажмите кнопку чтобы заказать такси.", "et": "👋 Tere tulemast!\n\nVajutage nuppu takso tellimiseks.", "en": "👋 Welcome!\n\nPress the button to order a taxi."},
    "order_taxi": {"ru": "🚖 Заказать такси", "et": "🚖 Telli takso", "en": "🚖 Order taxi"},
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
    "waiting": {"ru": "Ожидайте, водитель скоро примет заказ 🚖", "et": "Oodake, juht võtab tellimuse varsti vastu 🚖", "en": "Please wait, driver will accept soon 🚖"},
    "driver_found": {"ru": "🚖 *Водитель найден!*\n\n👤 Водитель: {name}\n🚗 Машина: {car}\n⏱ Едет к вам...", "et": "🚖 *Juht leitud!*\n\n👤 Juht: {name}\n🚗 Auto: {car}\n⏱ Sõidab teie juurde...", "en": "🚖 *Driver found!*\n\n👤 Driver: {name}\n🚗 Car: {car}\n⏱ On the way..."},
    "arrived": {"ru": "📍 *Водитель прибыл!*\n\n🚖 {name} ждёт вас. Выходите! 😊", "et": "📍 *Juht on kohal!*\n\n🚖 {name} ootab teid. Tulge välja! 😊", "en": "📍 *Driver arrived!*\n\n🚖 {name} is waiting. Please come out! 😊"},
    "trip_done": {"ru": "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!", "et": "🏁 *Sõit lõpetatud!*\n\nTäname, et valisite TL.TAKSO!", "en": "🏁 *Trip completed!*\n\nThank you for choosing TL.TAKSO!"},
    "cancel_order": {"ru": "❌ Отменить заказ", "et": "❌ Tühista tellimus", "en": "❌ Cancel order"},
    "order_cancelled": {"ru": "❌ Заказ отменён.", "et": "❌ Tellimus tühistatud.", "en": "❌ Order cancelled."},
    "driver_cancelled": {"ru": "⚠️ Клиент отменил заказ.", "et": "⚠️ Klient tühistas tellimuse.", "en": "⚠️ Client cancelled the order."},
    "reg_driver": {"ru": "🧑‍✈️ *Регистрация водителя*\n\nВведите ваше полное имя:", "et": "🧑‍✈️ *Juhi registreerimine*\n\nSisestage oma täisnimi:", "en": "🧑‍✈️ *Driver registration*\n\nEnter your full name:"},
    "ask_car": {"ru": "🚗 Введите марку и номер машины:", "et": "🚗 Sisestage auto mark ja number:", "en": "🚗 Enter car model and plate:"},
    "ask_phone": {"ru": "📱 Введите ваш номер телефона:", "et": "📱 Sisestage oma telefoninumber:", "en": "📱 Enter your phone number:"},
    "pending": {"ru": "⏳ Ваша заявка на рассмотрении.", "et": "⏳ Teie taotlus on läbivaatamisel.", "en": "⏳ Your application is under review."},
    "approved": {"ru": "🎉 *Заявка одобрена!*", "et": "🎉 *Taotlus on kinnitatud!*", "en": "🎉 *Application approved!*"},
    "rejected": {"ru": "😔 Заявка отклонена.", "et": "😔 Taotlus lükati tagasi.", "en": "😔 Application rejected."},
    "balance": {"ru": "💰 Ваш баланс: {bal}€", "et": "💰 Teie saldo: {bal}€", "en": "💰 Your balance: {bal}€"},
    "low_balance": {"ru": "⚠️ Баланс низкий: {bal}€", "et": "⚠️ Saldo on madal: {bal}€", "en": "⚠️ Balance is low: {bal}€"},
    "driver_busy": {"ru": "⚠️ У вас уже есть активный заказ", "et": "⚠️ Teil on juba aktiivne tellimus", "en": "⚠️ You already have an active order"},
    "msg_sent_driver": {"ru": "✉️ Отправлено водителю", "et": "✉️ Saadetud juhile", "en": "✉️ Sent to driver"},
    "msg_sent_client": {"ru": "✉️ Отправлено клиенту", "et": "✉️ Saadetud kliendile", "en": "✉️ Sent to client"},
    "no_active_order": {"ru": "Нет активного заказа", "et": "Aktiivset tellimust pole", "en": "No active order"},
}

def t(key, uid, **kwargs):
    lang = get_lang(uid)
    text = T.get(key, {}).get(lang, T.get(key, {}).get("ru", key))
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ КЛАВИАТУРЫ ════════════════════════════════
# ═══════════════════════════════════════════════════════════════

def lang_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("🇪🇪 Eesti", callback_data="lang_et"),
           types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
           types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"))
    return kb

def role_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton(t("i_client", uid), callback_data="role_client"),
           types.InlineKeyboardButton(t("i_driver", uid), callback_data="role_driver"))
    return kb

def main_menu_client(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("order_taxi", uid))
    kb.row("💬 Поддержка")
    return kb

def main_menu_driver(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🟢 Я онлайн", "⚫ Я офлайн")
    kb.row("📊 Заработок", "💬 Поддержка")
    kb.row("🗺️ Карта")
    return kb

def main_menu_admin():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👥 Водители", "📋 Заказы")
    kb.row("📊 Статистика", "🚫 Блокировка")
    return kb

def location_or_text_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(types.KeyboardButton(text="📍 Отправить геолокацию", request_location=True))
    kb.row(types.KeyboardButton(text="✏️ Ввести адрес вручную"))
    return kb

def time_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton(t("now", uid), callback_data="time_now"),
           types.InlineKeyboardButton(t("in15", uid), callback_data="time_15"),
           types.InlineKeyboardButton(t("in30", uid), callback_data="time_30"))
    return kb

def price_kb(uid):
    lang = get_lang(uid)
    city = "Город" if lang=="ru" else "Linn" if lang=="et" else "City"
    far = "Далеко" if lang=="ru" else "Kaugele" if lang=="et" else "Far"
    air = "Аэропорт" if lang=="ru" else "Lennujaam" if lang=="et" else "Airport"
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("8€ — Mustamäe", callback_data="price_8"),
           types.InlineKeyboardButton(f"10€ — {city}", callback_data="price_10"))
    kb.row(types.InlineKeyboardButton(f"15€ — {far}", callback_data="price_15"),
           types.InlineKeyboardButton(f"20€ — {air}", callback_data="price_20"))
    return kb

def payment_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton(t("card", uid), callback_data="pay_card"),
           types.InlineKeyboardButton(t("cash", uid), callback_data="pay_cash"))
    return kb

def driver_order_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{order_id}"),
           types.InlineKeyboardButton("❌ Отказать", callback_data=f"decline_{order_id}"))
    return kb

def driver_active_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📍 Я прибыл!", callback_data=f"arrived_{order_id}"))
    kb.row(types.InlineKeyboardButton("✅ Поездка завершена", callback_data=f"done_{order_id}"))
    kb.row(types.InlineKeyboardButton("❌ Отменить заказ", callback_data=f"driver_cancel_{order_id}"))
    return kb

def approve_driver_kb(driver_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{driver_id}"),
           types.InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{driver_id}"))
    return kb

def cancel_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("cancel_order", uid), callback_data="cancel_order"))
    return kb

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ КОМАНДЫ И РЕГИСТРАЦИЯ ═════════════════════
# ═══════════════════════════════════════════════════════════════

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid = msg.from_user.id
    if is_admin(uid):
        user_state[uid] = {"role": "admin", "lang": "ru"}
        save_data()
        bot.send_message(uid, "👨‍💼 Панель администратора", reply_markup=main_menu_admin())
        return
    if is_approved_driver(uid):
        user_state[uid] = {"role": "driver", "lang": get_lang(uid)}
        save_data()
        bot.send_message(uid, "👋", reply_markup=main_menu_driver(uid))
        return
    if uid in pending_drivers:
        bot.send_message(uid, t("pending", uid))
        return
    if uid not in user_state:
        user_state[uid] = {"role": None, "lang": "ru"}
    bot.send_message(uid, "🌍 Vali keel / Выберите язык:", reply_markup=lang_kb())

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ КОМАНДЫ ДЛЯ СМЕНЫ РОЛИ ════════════════════
# ═══════════════════════════════════════════════════════════════

@bot.message_handler(commands=["client"])
def force_client(msg):
    uid = msg.from_user.id
    user_state[uid] = {"role": "client", "lang": get_lang(uid)}
    if uid in drivers:
        drivers[uid]["online"] = False
    save_data()
    bot.send_message(uid, "👋 *Теперь вы клиент*\n\nМожете заказывать такси", 
                     parse_mode="Markdown", reply_markup=main_menu_client(uid))

@bot.message_handler(commands=["driver"])
def force_driver(msg):
    uid = msg.from_user.id
    if uid not in drivers:
        drivers[uid] = {
            "approved": True, "online": True, "full_name": msg.from_user.first_name,
            "car": "Tesla Model 3", "phone": "+123456789", "lang": get_lang(uid),
            "earnings": 0, "trips": 0, "commission": 0, "balance": 50.0
        }
        save_data()
    user_state[uid] = {"role": "driver", "lang": get_lang(uid)}
    drivers[uid]["online"] = True
    drivers[uid]["approved"] = True
    save_data()
    bot.send_message(uid, "🧑‍✈️ *Теперь вы водитель*\n\nНажмите 🟢 Я онлайн чтобы получать заказы", 
                     parse_mode="Markdown", reply_markup=main_menu_driver(uid))

@bot.message_handler(commands=["admin"])
def force_admin(msg):
    uid = msg.from_user.id
    user_state[uid] = {"role": "admin", "lang": "ru"}
    save_data()
    bot.send_message(uid, "👨‍💼 *Панель администратора*", 
                     parse_mode="Markdown", reply_markup=main_menu_admin())

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ ОБРАБОТЧИКИ CALLBACK ══════════════════════
# ═══════════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def cb_lang(call):
    uid = call.from_user.id
    lang = call.data.split("_")[1]
    user_state[uid] = {"role": None, "lang": lang}
    bot.edit_message_text(t("welcome", uid), call.message.chat.id, call.message.message_id,
                         parse_mode="Markdown", reply_markup=role_kb(uid))

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
    state["step"] = None
    pending_drivers[uid] = {
        "id": uid, "full_name": state.get("full_name"), "car": state.get("car"),
        "phone": msg.text, "username": msg.from_user.username or "—",
        "lang": get_lang(uid), "registered": now_str()
    }
    save_data()
    bot.send_message(uid, t("pending", uid))
    try:
        bot.send_message(ADMIN_ID, f"🔔 *Новая заявка!*\n\n👤 {state['full_name']}\n🚗 {state['car']}\n📱 {msg.text}",
                        parse_mode="Markdown", reply_markup=approve_driver_kb(uid))
    except:
        pass

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
        drivers[driver_id] = {
            "approved": True, "online": False, "full_name": pending["full_name"],
            "car": pending["car"], "phone": pending["phone"], "lang": pending.get("lang", "ru"),
            "earnings": 0, "trips": 0, "commission": 0, "balance": 10.0
        }
        del pending_drivers[driver_id]
        save_data()
        bot.edit_message_text(f"✅ Водитель *{pending['full_name']}* одобрен!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        user_state[driver_id] = {"role": "driver", "lang": pending.get("lang", "ru")}
        bot.send_message(driver_id, t("approved", driver_id), parse_mode="Markdown", reply_markup=main_menu_driver(driver_id))
    elif action == "reject":
        del pending_drivers[driver_id]
        save_data()
        bot.edit_message_text(f"❌ Водитель *{pending['full_name']}* отклонён.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.send_message(driver_id, t("rejected", driver_id))

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ ЗАКАЗ ТАКСИ ═══════════════════════════════
# ═══════════════════════════════════════════════════════════════


@bot.message_handler(func=lambda m: m.text in ["🚖 Заказать такси", "🚖 Telli takso", "🚖 Order taxi"])
def order_start(msg):
    uid = msg.from_user.id
    existing = user_state.get(uid, {}).get("current_order")
    if existing and existing in orders and orders[existing]["status"] in ["pending", "accepted", "arrived"]:
        bot.send_message(uid, "⏳ У ваc есть активный заказ!", reply_markup=main_menu_client(uid))
        return
    if uid not in user_state:
        user_state[uid] = {}
    user_state[uid]["step"] = "waiting_webapp"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="🗺️ Выбрать на карте", web_app=types.WebAppInfo(url=MINI_APP_URL)))
    bot.send_message(uid, "📍 Нажмите кнопку чтобы выбрать маршрут на карте:", reply_markup=kb)

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "choose_address_method")
def handle_address_method(msg):
    uid = msg.from_user.id
    text = msg.text
    
    if "геолокацию" in text or "location" in text.lower():
        user_state[uid]["step"] = "waiting_from_location"
        bot.send_message(uid, "📍 *Отправьте ваше текущее местоположение*", 
                         parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())
    elif "вручную" in text or "address" in text.lower() or "вручную" in text:
        user_state[uid]["step"] = "manual_from_address"
        bot.send_message(uid, t("ask_from", uid), parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.send_message(uid, "Пожалуйста, выберите вариант из меню", reply_markup=location_or_text_kb(uid))

@bot.message_handler(content_types=['location'], func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "waiting_from_location")
def handle_from_location(msg):
    uid = msg.from_user.id
    user_state[uid]["order_data"]["from_lat"] = msg.location.latitude
    user_state[uid]["order_data"]["from_lon"] = msg.location.longitude
    user_state[uid]["order_data"]["from_address"] = f"📍 {msg.location.latitude:.5f}, {msg.location.longitude:.5f}"
    user_state[uid]["step"] = "waiting_to_method"
    bot.send_message(uid, "🏁 *Теперь укажите адрес назначения*", 
                     parse_mode="Markdown", reply_markup=location_or_text_kb(uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "manual_from_address")
def handle_manual_from(msg):
    uid = msg.from_user.id
    user_state[uid]["order_data"]["from_address"] = msg.text
    user_state[uid]["order_data"]["from_lat"] = None
    user_state[uid]["order_data"]["from_lon"] = None
    user_state[uid]["step"] = "waiting_to_method"
    bot.send_message(uid, "🏁 *Теперь укажите адрес назначения*", 
                     parse_mode="Markdown", reply_markup=location_or_text_kb(uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "waiting_to_method")
def handle_to_method(msg):
    uid = msg.from_user.id
    text = msg.text
    
    if "геолокацию" in text or "location" in text.lower():
        user_state[uid]["step"] = "waiting_to_location"
        bot.send_message(uid, "📍 *Отправьте местоположение назначения*", 
                         parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())
    elif "вручную" in text or "address" in text.lower() or "вручную" in text:
        user_state[uid]["step"] = "manual_to_address"
        bot.send_message(uid, t("ask_to", uid), parse_mode="Markdown")
    else:
        bot.send_message(uid, "Пожалуйста, выберите вариант", reply_markup=location_or_text_kb(uid))

@bot.message_handler(content_types=['location'], func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "waiting_to_location")
def handle_to_location(msg):
    uid = msg.from_user.id
    user_state[uid]["order_data"]["to_lat"] = msg.location.latitude
    user_state[uid]["order_data"]["to_lon"] = msg.location.longitude
    user_state[uid]["order_data"]["to_address"] = f"📍 {msg.location.latitude:.5f}, {msg.location.longitude:.5f}"
    user_state[uid]["step"] = "waiting_time"
    bot.send_message(uid, t("ask_time", uid), parse_mode="Markdown", reply_markup=time_kb(uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "manual_to_address")
def handle_manual_to(msg):
    uid = msg.from_user.id
    user_state[uid]["order_data"]["to_address"] = msg.text
    user_state[uid]["order_data"]["to_lat"] = None
    user_state[uid]["order_data"]["to_lon"] = None
    user_state[uid]["step"] = "waiting_time"
    bot.send_message(uid, t("ask_time", uid), parse_mode="Markdown", reply_markup=time_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("time_"))
def cb_time(call):
    uid = call.from_user.id
    choice = call.data.split("_")[1]
    time_map = {"now": "Сейчас", "15": "Через 15 мин", "30": "Через 30 мин"}
    user_state[uid]["order_data"]["time"] = time_map.get(choice, "Сейчас")
    bot.edit_message_text(t("ask_price", uid), call.message.chat.id, call.message.message_id,
                          reply_markup=price_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("price_"))
def cb_price(call):
    uid = call.from_user.id
    price = int(call.data.split("_")[1])
    user_state[uid]["order_data"]["price"] = price
    user_state[uid]["order_data"]["driver_gets"] = price - 1
    bot.edit_message_text(t("ask_payment", uid), call.message.chat.id, call.message.message_id,
                          reply_markup=payment_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def cb_payment(call):
    uid = call.from_user.id
    pay_type = call.data.split("_")[1]
    data = user_state[uid].get("order_data", {})
    
    oid = new_order_id()
    orders[oid] = {
        "id": oid, "client_id": uid, "client_name": call.from_user.first_name,
        "from": data.get("from_address", "—"), "to": data.get("to_address", "—"),
        "from_lat": data.get("from_lat"), "from_lon": data.get("from_lon"),
        "to_lat": data.get("to_lat"), "to_lon": data.get("to_lon"),
        "time": data.get("time", "Сейчас"), "payment": "💳 Карта" if pay_type == "card" else "💵 Наличные",
        "pay_type": pay_type, "price": data.get("price", 0),
        "driver_gets": data.get("driver_gets", data.get("price", 0)),
        "status": "pending", "created": now_str(), "driver_id": None,
        "client_lang": get_lang(uid)
    }
    
    user_state[uid]["current_order"] = oid
    user_state[uid]["step"] = None
    save_data()
    
    # Показываем карту маршрута
    map_url = get_route_static_map(data.get("from_lat"), data.get("from_lon"), 
                                    data.get("to_lat"), data.get("to_lon"))
    if map_url:
        try:
            bot.send_photo(uid, map_url, caption=f"🗺️ *Ваш маршрут*", parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Ошибка отправки карты: {e}")
    
    bot.send_message(uid, f"✅ *Заказ #{oid} создан!*\n\n📍 {orders[oid]['from'][:50]}\n🏁 {orders[oid]['to'][:50]}\n💰 *{orders[oid]['price']}€*\n\n⏳ Ищем водителя...",
                     parse_mode="Markdown", reply_markup=main_menu_client(uid))
    
    # Уведомляем водителей
    # 
notified = 0
for driver_id, d in drivers.items():
    if d.get("approved") and d.get("online") and d.get("balance", 0) > 0 and not has_active_order(driver_id):
        try:
            bot.send_message(driver_id, f"🔔 *Новый заказ #{oid}*\n\n👤 {order['client_name']}\n📍 {order['from'][:40]}\n🏁 {order['to'][:40]}\n💰 *{order['driver_gets']}€*",
                             parse_mode="Markdown", reply_markup=driver_order_kb(oid))
            notified += 1
        except Exception as e:
            print(f"❌ Не удалось уведомить водителя {driver_id}: {e}")

if notified == 0:
    bot.send_message(order['client_id'], "⚠️ Сейчас нет свободных водителей. Пожалуйста, подождите или попробуйте позже.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_") or c.data.startswith("decline_"))
def cb_driver_response(call):
    driver_id = call.from_user.id
    action, oid = call.data.split("_", 1)
    order = orders.get(oid)
    if not order or order["status"] != "pending":
        bot.answer_callback_query(call.id, "Заказ уже неактивен")
        return
    
    if action == "accept":
        if has_active_order(driver_id):
            bot.answer_callback_query(call.id, t("driver_busy", driver_id))
            return
        order["status"] = "accepted"
        order["driver_id"] = driver_id
        order["driver_name"] = drivers[driver_id]["full_name"]
        drivers[driver_id]["trips"] = drivers[driver_id].get("trips", 0) + 1
        drivers[driver_id]["earnings"] = drivers[driver_id].get("earnings", 0) + order["driver_gets"]
        drivers[driver_id]["commission"] = drivers[driver_id].get("commission", 0) + 1
        if order.get("pay_type") == "cash":
            drivers[driver_id]["balance"] = drivers[driver_id].get("balance", 0) - 1
        save_data()
        bot.edit_message_text(f"✅ *Заказ #{oid} принят!*\n\n📍 {order['from'][:40]}\n🏁 {order['to'][:40]}\n👤 {order['client_name']}", 
                              call.message.chat.id, call.message.message_id,
                              parse_mode="Markdown", reply_markup=driver_active_kb(oid))
        bot.send_message(order["client_id"], t("driver_found", order["client_id"], 
                         name=drivers[driver_id]["full_name"], car=drivers[driver_id]["car"]), parse_mode="Markdown")
    elif action == "decline":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Отклонён")

@bot.callback_query_handler(func=lambda c: c.data.startswith("arrived_"))
def cb_arrived(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if order and order["status"] == "accepted":
        order["status"] = "arrived"
        save_data()
        bot.answer_callback_query(call.id, "✅ Клиент уведомлён!")
        bot.send_message(order["client_id"], t("arrived", order["client_id"], name=order["driver_name"]), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if order and order["status"] in ["accepted", "arrived"]:
        order["status"] = "done"
        save_data()
        bot.edit_message_text(f"✅ *Поездка #{oid} завершена!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.send_message(order["client_id"], t("trip_done", order["client_id"]), parse_mode="Markdown", reply_markup=main_menu_client(order["client_id"]))
        # Очищаем текущий заказ у клиента
        if order["client_id"] in user_state:
            user_state[order["client_id"]].pop("current_order", None)

@bot.callback_query_handler(func=lambda c: c.data.startswith("driver_cancel_"))
def cb_driver_cancel(call):
    oid = call.data.split("_", 2)[2] if len(call.data.split("_")) > 2 else call.data.split("_", 1)[1]
    order = orders.get(oid)
    if order and order["status"] in ["accepted", "arrived"]:
        driver_id = call.from_user.id
        order["status"] = "pending"
        order["driver_id"] = None
        order.pop("driver_name", None)
        drivers[driver_id]["trips"] = max(0, drivers[driver_id].get("trips", 0) - 1)
        drivers[driver_id]["earnings"] = max(0, drivers[driver_id].get("earnings", 0) - order.get("driver_gets", 0))
        drivers[driver_id]["commission"] = max(0, drivers[driver_id].get("commission", 0) - 1)
        if order.get("pay_type") == "cash":
            drivers[driver_id]["balance"] = drivers[driver_id].get("balance", 0) + 1
        save_data()
        bot.edit_message_text(f"❌ Заказ #{oid} отменён. Возвращён в поиск.", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "Заказ отменён")
        # Уведомляем клиента
        bot.send_message(order["client_id"], "⚠️ Водитель отменил заказ. Ищем нового водителя...", reply_markup=cancel_kb(order["client_id"]))
        # Рассылаем водителям снова
        for did, d in drivers.items():
            if d.get("approved") and d.get("online") and d.get("balance", 0) > 0 and not has_active_order(did) and did != driver_id:
                try:
                    bot.send_message(did, f"🔔 *Заказ #{oid} (повторно)*\n\n👤 {order['client_name']}\n📍 {order['from'][:40]}\n🏁 {order['to'][:40]}\n💰 *{order['driver_gets']}€*",
                                     parse_mode="Markdown", reply_markup=driver_order_kb(oid))
                except:
                    pass

@bot.callback_query_handler(func=lambda c: c.data == "cancel_order")
def cb_cancel(call):
    uid = call.from_user.id
    oid = user_state.get(uid, {}).get("current_order")
    if oid and oid in orders:
        order = orders[oid]
        if order["status"] in ["pending", "accepted", "arrived"]:
            order["status"] = "cancelled"
            if order.get("driver_id"):
                try:
                    bot.send_message(order["driver_id"], t("driver_cancelled", order["driver_id"]))
                    # Возвращаем комиссию водителю
                    if order.get("pay_type") == "cash":
                        drivers[order["driver_id"]]["balance"] = drivers[order["driver_id"]].get("balance", 0) + 1
                    drivers[order["driver_id"]]["trips"] = max(0, drivers[order["driver_id"]].get("trips", 0) - 1)
                    drivers[order["driver_id"]]["earnings"] = max(0, drivers[order["driver_id"]].get("earnings", 0) - order.get("driver_gets", 0))
                    drivers[order["driver_id"]]["commission"] = max(0, drivers[order["driver_id"]].get("commission", 0) - 1)
                except:
                    pass
            save_data()
    bot.edit_message_text(t("order_cancelled", uid), call.message.chat.id, call.message.message_id)
    bot.send_message(uid, t("order_cancelled", uid), reply_markup=main_menu_client(uid))
    if uid in user_state:
        user_state[uid].pop("current_order", None)

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ ВОДИТЕЛИ И АДМИНКА ════════════════════════
# ═══════════════════════════════════════════════════════════════

@bot.message_handler(func=lambda m: m.text in ["🟢 Я онлайн", "🟢 Olen online", "🟢 I'm online"] and is_approved_driver(m.from_user.id))
def driver_online(msg):
    drivers[msg.from_user.id]["online"] = True
    save_data()
    bot.send_message(msg.chat.id, "🟢 Вы онлайн", reply_markup=main_menu_driver(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["⚫ Я офлайн", "⚫ Olen offline", "⚫ I'm offline"] and is_approved_driver(m.from_user.id))
def driver_offline(msg):
    drivers[msg.from_user.id]["online"] = False
    save_data()
    bot.send_message(msg.chat.id, "⚫ Вы офлайн", reply_markup=main_menu_driver(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["📊 Заработок", "📊 Tulu", "📊 Earnings"] and is_approved_driver(m.from_user.id))
def driver_earnings(msg):
    d = drivers[msg.from_user.id]
    lang = get_lang(msg.from_user.id)
    if lang == "ru":
        text = f"{t('balance', msg.from_user.id, bal=d.get('balance', 0))}\n🚖 Поездок: {d.get('trips', 0)}\n💶 Заработано: {d.get('earnings', 0)}€\n📊 Комиссия: {d.get('commission', 0)}€"
    elif lang == "et":
        text = f"{t('balance', msg.from_user.id, bal=d.get('balance', 0))}\n🚖 Sõite: {d.get('trips', 0)}\n💶 Teenitud: {d.get('earnings', 0)}€\n📊 Komisjon: {d.get('commission', 0)}€"
    else:
        text = f"{t('balance', msg.from_user.id, bal=d.get('balance', 0))}\n🚖 Trips: {d.get('trips', 0)}\n💶 Earned: {d.get('earnings', 0)}€\n📊 Commission: {d.get('commission', 0)}€"
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_driver(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["🗺️ Карта", "🗺️ Kaart", "🗺️ Map"] and is_approved_driver(m.from_user.id))
def driver_map(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="🗺️ Открыть карту" if get_lang(msg.from_user.id) == "ru" else "🗺️ Ava kaart" if get_lang(msg.from_user.id) == "et" else "🗺️ Open map", 
                                      web_app=types.WebAppInfo(url=DRIVER_MAP_URL)))
    bot.send_message(msg.chat.id, "🗺️ Карта заказов:" if get_lang(msg.from_user.id) == "ru" else "🗺️ Tellimuste kaart:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["💬 Поддержка", "💬 Tugi", "💬 Support"])
def support(msg):
    bot.send_message(msg.chat.id, "📞 Поддержка: @tltakso_support")

# Админ-панель
@bot.message_handler(func=lambda m: m.text == "👥 Водители" and is_admin(m.from_user.id))
def admin_drivers(msg):
    online = [(uid, d) for uid, d in drivers.items() if d.get("online") and d.get("approved")]
    text = f"🟢 Онлайн: {len(online)}\n\n"
    for uid, d in online:
        busy = "🚖 Занят" if has_active_order(uid) else "✅ Свободен"
        text += f"👤 {d['full_name']}\n🚗 {d['car']}\n💰 {d.get('balance',0)}€\n{busy}\n\n"
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "📋 Заказы" and is_admin(m.from_user.id))
def admin_orders(msg):
    if not orders:
        bot.send_message(msg.chat.id, "📋 Заказов нет", reply_markup=main_menu_admin())
        return
    text = f"📋 Заказов: {len(orders)}\n\n"
    status_map = {"pending":"⏳","accepted":"🚖","arrived":"📍","done":"✅","cancelled":"❌"}
    for oid, o in list(orders.items())[-10:]:
        text += f"{status_map.get(o['status'], '?')} #{oid} · {o['client_name']} · {o['price']}€\n"
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and is_admin(m.from_user.id))
def admin_stats(msg):
    total = len(orders)
    done = len([o for o in orders.values() if o['status'] == 'done'])
    revenue = sum(d.get("commission", 0) for d in drivers.values())
    bot.send_message(msg.chat.id, f"📊 Статистика\n\n🚖 Заказов: {total}\n✅ Завершено: {done}\n💰 Сбор: {revenue}€\n👥 Водителей: {len(drivers)}",
                     reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "🚫 Блокировка" and is_admin(m.from_user.id))
def admin_block(msg):
    approved = [(uid, d) for uid, d in drivers.items() if d.get("approved") and uid != ADMIN_ID]
    if not approved:
        bot.send_message(msg.chat.id, "Нет водителей")
        return
    kb = types.InlineKeyboardMarkup()
    for uid, d in approved:
        kb.add(types.InlineKeyboardButton(f"🚫 {d['full_name']}", callback_data=f"block_{uid}"))
    bot.send_message(msg.chat.id, "Выберите водителя:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("block_"))
def cb_block(call):
    if not is_admin(call.from_user.id):
        return
    driver_id = int(call.data.split("_")[1])
    if driver_id in drivers:
        drivers[driver_id]['approved'] = False
        drivers[driver_id]['online'] = False
        save_data()
        bot.edit_message_text(f"🚫 Водитель заблокирован", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(driver_id, "⛔ Ваш аккаунт заблокирован")
        except:
            pass

# Чат между клиентом и водителем
IGNORE_PATTERNS = [
    r"🚖.*(Заказать такси|Telli takso|Order taxi)",
    r"💬.*(Поддержка|Tugi|Support)",
    r"🟢.*(онлайн|online)",
    r"⚫.*(офлайн|offline)",
    r"📊.*(Заработок|Tulu|Earnings)",
    r"🗺️.*(Карта|Kaart|Map)",
    r"👥.*Водители",
    r"📋.*Заказы",
    r"📊.*Статистика",
    r"🚫.*Блокировка"
]

def should_ignore(text):
    if not text:
        return False
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("role") in ["client","driver"] and m.text and not m.text.startswith("/"))
def relay_message(msg):
    if should_ignore(msg.text):
        return
    
    uid = msg.from_user.id
    role = user_state.get(uid, {}).get("role")
    if role == "client":
        oid = user_state.get(uid, {}).get("current_order")
        if oid and oid in orders:
            order = orders[oid]
            if order["status"] in ["accepted","arrived"]:
                driver_id = order.get("driver_id")
                if driver_id:
                    bot.send_message(driver_id, f"💬 *{msg.from_user.first_name}:*\n{msg.text}", parse_mode="Markdown")
                    bot.send_message(uid, t("msg_sent_driver", uid))
                    return
        bot.send_message(uid, t("no_active_order", uid), reply_markup=main_menu_client(uid))
    elif role == "driver":
        for oid, order in orders.items():
            if order.get("driver_id") == uid and order.get("status") in ["accepted","arrived"]:
                bot.send_message(order["client_id"], f"💬 *{msg.from_user.first_name}:*\n{msg.text}", parse_mode="Markdown")
                bot.send_message(uid, t("msg_sent_client", uid))
                return

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ ЗАПУСК БОТА ═══════════════════════════════
# ═══════════════════════════════════════════════════════════════

def setup_webhook():
    webhook_url = f"https://{RAILWAY_DOMAIN}/webhook/{WEBHOOK_SECRET}"
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook установлен: {webhook_url}")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки webhook: {e}")
        return False

if __name__ == "__main__":
    print("🚖 TL.TAKSO Bot запускается...")
    save_thread = threading.Thread(target=auto_save, daemon=True)
    save_thread.start()
    setup_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
