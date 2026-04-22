# tl_takso_bot.py - TL.TAKSO Полная версия (ИСПРАВЛЕННАЯ)
import os
import sys
import json
import time
import threading
import re
import hashlib
import hmac
import urllib.parse
from datetime import datetime
from pathlib import Path
from flask import Flask, send_from_directory, request, abort, jsonify
import telebot
from telebot import types

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен")

MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "pk.eyJ1IjoidGx0YWtzbyIsImEiOiJjbW4zYW0yMGkxNG13MnByM2hoZng0OXh2In0.ArR_nk-dVg99VhuuatH2hA")
RAILWAY_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1873195803"))

# Директория данных
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "tltakso_data.json"

# URL для Mini Apps - ИСПРАВЛЕНО
PROTOCOL = "https"
CLIENT_URL = f"{PROTOCOL}://{RAILWAY_DOMAIN}/static/index.html"
DRIVER_URL = f"{PROTOCOL}://{RAILWAY_DOMAIN}/static/driver.html"
TRACKING_URL = f"{PROTOCOL}://{RAILWAY_DOMAIN}/static/tracking.html"

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# === ЗАГРУЗКА И СОХРАНЕНИЕ ДАННЫХ ===
data_lock = threading.Lock()

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"orders": {}, "drivers": {}, "user_state": {}, "pending_drivers": {}, "order_counter": 1}

def save_data():
    with data_lock:
        data = {
            "orders": orders,
            "user_state": user_state,
            "drivers": drivers,
            "pending_drivers": pending_drivers,
            "order_counter": order_counter[0],
            "saved_at": datetime.now().isoformat()
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()
orders = data.get("orders", {})
user_state = data.get("user_state", {})
drivers = data.get("drivers", {})
pending_drivers = data.get("pending_drivers", {})
order_counter = [data.get("order_counter", 1)]

# Хранилища в памяти
driver_locations = {}
order_reserves = {}

# Админ как водитель
if ADMIN_ID not in drivers:
    drivers[ADMIN_ID] = {
        "approved": True, "online": True, "full_name": "Админ",
        "car": "Toyota Camry", "phone": "+372", "lang": "ru",
        "earnings": 0, "trips": 0, "commission": 0, "balance": 100.0
    }

# === ПЕРЕВОДЫ ===
T = {
    "welcome": {"ru": "🚖 *TL.TAKSO*\n\nТакси по Таллинну\n\nКто вы?", "et": "🚖 *TL.TAKSO*\n\nTakso Tallinnas\n\nKes te olete?", "en": "🚖 *TL.TAKSO*\n\nTaxi in Tallinn\n\nWho are you?"},
    "i_client": {"ru": "🚖 Я клиент", "et": "🚖 Olen klient", "en": "🚖 I'm a client"},
    "i_driver": {"ru": "🧑‍✈️ Я водитель", "et": "🧑‍✈️ Olen juht", "en": "🧑‍✈️ I'm a driver"},
    "order_taxi": {"ru": "🚖 Заказать такси", "et": "🚖 Telli takso", "en": "🚖 Order taxi"},
    "support": {"ru": "💬 Поддержка", "et": "💬 Tugi", "en": "💬 Support"},
    "online": {"ru": "🟢 Я онлайн", "et": "🟢 Olen online", "en": "🟢 I'm online"},
    "offline": {"ru": "⚫ Я офлайн", "et": "⚫ Olen offline", "en": "⚫ I'm offline"},
    "earnings": {"ru": "📊 Заработок", "et": "📊 Tulu", "en": "📊 Earnings"},
    "map": {"ru": "🗺️ Карта", "et": "🗺️ Kaart", "en": "🗺️ Map"},
    "reg_driver": {"ru": "🧑‍✈️ *Регистрация водителя*\n\nВведите ваше полное имя:", "et": "🧑‍✈️ *Juhi registreerimine*\n\nSisestage oma täisnimi:", "en": "🧑‍✈️ *Driver registration*\n\nEnter your full name:"},
    "ask_car": {"ru": "🚗 Введите марку и номер машины:", "et": "🚗 Sisestage auto mark ja number:", "en": "🚗 Enter car model and plate:"},
    "ask_phone": {"ru": "📱 Введите ваш номер телефона:", "et": "📱 Sisestage oma telefoninumber:", "en": "📱 Enter your phone number:"},
    "pending": {"ru": "⏳ Ваша заявка на рассмотрении.", "et": "⏳ Teie taotlus on läbivaatamisel.", "en": "⏳ Your application is under review."},
    "approved": {"ru": "✅ Ваша заявка одобрена!", "et": "✅ Teie taotlus on kinnitatud!", "en": "✅ Your application is approved!"},
    "rejected": {"ru": "❌ Заявка отклонена.", "et": "❌ Taotlus lükati tagasi.", "en": "❌ Application rejected."},
}

def t(key, uid, **kwargs):
    lang = user_state.get(uid, {}).get("lang", "ru")
    text = T.get(key, {}).get(lang, T.get(key, {}).get("ru", key))
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def new_order_id():
    oid = f"TL{order_counter[0]:04d}"
    order_counter[0] += 1
    return oid

def now_str():
    return datetime.now().strftime("%H:%M")

def is_admin(uid):
    return uid == ADMIN_ID

def is_approved_driver(uid):
    return uid in drivers and drivers[uid].get("approved")

def get_lang(uid):
    return user_state.get(uid, {}).get("lang", "ru")

def has_active_order(driver_id):
    if not driver_id:
        return False
    for order in orders.values():
        if order.get("driver_id") == driver_id and order.get("status") in ["accepted", "arrived"]:
            return True
    return False

def notify_drivers(oid):
    order = orders.get(oid)
    if not order:
        return
    
    text = f"🔔 *Новый заказ #{oid}*\n\n👤 {order.get('client_name', 'Клиент')}\n📍 {order.get('from', '—')[:40]}\n🏁 {order.get('to', '—')[:40]}\n💰 *{order.get('driver_gets', 0)}€*"
    
    for driver_id, d in drivers.items():
        if d.get("approved") and d.get("online") and not has_active_order(driver_id):
            try:
                kb = types.InlineKeyboardMarkup()
                kb.row(
                    types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{oid}"),
                    types.InlineKeyboardButton("❌ Отказать", callback_data=f"decline_{oid}")
                )
                bot.send_message(driver_id, text, parse_mode="Markdown", reply_markup=kb)
            except:
                pass

# === КЛАВИАТУРЫ ===
def lang_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🇪🇪 Eesti", callback_data="lang_et"),
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    return kb

def role_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton(t("i_client", uid), callback_data="role_client"),
        types.InlineKeyboardButton(t("i_driver", uid), callback_data="role_driver")
    )
    return kb

def main_menu_client(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("order_taxi", uid))
    kb.row(t("support", uid))
    return kb

def main_menu_driver(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("online", uid), t("offline", uid))
    kb.row(t("earnings", uid), t("support", uid))
    kb.row(t("map", uid))
    return kb

def main_menu_admin():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👥 Водители", "📋 Заказы")
    kb.row("📊 Статистика", "🚫 Блокировка")
    return kb

def approve_driver_kb(driver_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{driver_id}"),
        types.InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{driver_id}")
    )
    return kb

def driver_active_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📍 Я прибыл!", callback_data=f"arrived_{order_id}"))
    kb.row(types.InlineKeyboardButton("✅ Поездка завершена", callback_data=f"done_{order_id}"))
    kb.row(types.InlineKeyboardButton("❌ Отменить заказ", callback_data=f"driver_cancel_{order_id}"))
    return kb

# === FLASK ROUTES ===
@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'orders': len(orders), 'drivers': len(drivers)})

@app.route('/api/orders', methods=['GET'])
def api_orders():
    result = []
    for oid, order in orders.items():
        if order.get('status') == 'pending':
            result.append({
                'id': oid,
                'price': order.get('driver_gets', order.get('price', 0)),
                'from_address': order.get('from', '—'),
                'to_address': order.get('to', '—'),
                'from_lat': order.get('from_lat'),
                'from_lon': order.get('from_lon'),
                'to_lat': order.get('to_lat'),
                'to_lon': order.get('to_lon'),
                'client_name': order.get('client_name', 'Клиент')
            })
    return jsonify(result)

@app.route('/api/create_order', methods=['POST'])
def api_create_order():
    try:
        data = request.get_json()
        client_id = int(data.get('client_id', 0))
        oid = new_order_id()
        
        price = data.get('price', 0)
        orders[oid] = {
            "id": oid, "client_id": client_id,
            "client_name": data.get('client_name', 'Клиент'),
            "from": data.get('from_address', '—'),
            "to": data.get('to_address', '—'),
            "from_lat": data.get('from_lat', 0),
            "from_lon": data.get('from_lon', 0),
            "to_lat": data.get('to_lat', 0),
            "to_lon": data.get('to_lon', 0),
            "price": price,
            "driver_gets": data.get('driver_gets', price - 1),
            "pay_type": data.get('payment', 'cash'),
            "payment": "💳 Карта" if data.get('payment') == 'card' else "💵 Наличные",
            "status": "pending",
            "driver_id": None,
            "created": now_str()
        }
        
        if client_id not in user_state:
            user_state[client_id] = {"role": "client", "lang": "ru"}
        user_state[client_id]["current_order"] = oid
        
        save_data()
        
        try:
            bot.send_message(client_id, f"✅ *Заказ #{oid} создан!*\n\n📍 {orders[oid]['from'][:50]}\n🏁 {orders[oid]['to'][:50]}\n💰 *{price}€*\n\n⏳ Ищем водителя...", parse_mode="Markdown")
        except:
            pass
        
        notify_drivers(oid)
        return jsonify({'ok': True, 'order_id': oid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/order_status/<order_id>')
def api_order_status(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({'ok': False}), 404
    
    loc = driver_locations.get(order_id)
    driver_id = order.get('driver_id')
    driver_car = drivers.get(driver_id, {}).get('car', '') if driver_id else ''
    
    return jsonify({
        'ok': True,
        'status': order.get('status'),
        'driver_name': order.get('driver_name', ''),
        'driver_car': driver_car,
        'driver_lat': loc['lat'] if loc else None,
        'driver_lon': loc['lon'] if loc else None,
        'from_address': order.get('from'),
        'to_address': order.get('to'),
        'from_lat': order.get('from_lat'),
        'from_lon': order.get('from_lon'),
        'to_lat': order.get('to_lat'),
        'to_lon': order.get('to_lon'),
        'price': order.get('price'),
        'payment': order.get('pay_type')
    })

@app.route('/api/driver_location/<order_id>', methods=['POST'])
def api_driver_location(order_id):
    data = request.get_json()
    driver_locations[order_id] = {
        'lat': data.get('lat'),
        'lon': data.get('lon'),
        'updated': time.time()
    }
    return jsonify({'ok': True})

@app.route('/api/accept_order/<order_id>', methods=['POST'])
def api_accept_order(order_id):
    data = request.get_json()
    driver_id = int(data.get('driver_id', 0))
    
    with data_lock:
        order = orders.get(order_id)
        if not order or order.get('status') != 'pending':
            return jsonify({'ok': False, 'error': 'Заказ недоступен'}), 409
        
        order['status'] = 'accepted'
        order['driver_id'] = driver_id
        order['driver_name'] = data.get('driver_name', 'Водитель')
    
    if driver_id in drivers:
        drivers[driver_id]['trips'] = drivers[driver_id].get('trips', 0) + 1
        drivers[driver_id]['earnings'] = drivers[driver_id].get('earnings', 0) + order.get('driver_gets', 0)
        if order.get('pay_type') == 'cash':
            drivers[driver_id]['balance'] = drivers[driver_id].get('balance', 0) - 1
    
    save_data()
    
    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗺️ Следить за водителем", web_app=types.WebAppInfo(url=f"{TRACKING_URL}?order={order_id}")))
        d = drivers.get(driver_id, {})
        bot.send_message(order['client_id'], f"🚖 *Водитель найден!*\n\n👤 {d.get('full_name', '')}\n🚗 {d.get('car', '')}", parse_mode="Markdown", reply_markup=kb)
    except:
        pass
    
    return jsonify({'ok': True})

@app.route('/api/complete_order/<order_id>', methods=['POST'])
def api_complete_order(order_id):
    order = orders.get(order_id)
    if order and order.get('status') in ['accepted', 'arrived']:
        order['status'] = 'done'
        driver_locations.pop(order_id, None)
        save_data()
        try:
            bot.send_message(order['client_id'], "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!", parse_mode="Markdown")
        except:
            pass
        if order['client_id'] in user_state:
            user_state[order['client_id']].pop("current_order", None)
    return jsonify({'ok': True})

@app.route('/api/cancel_order_client/<order_id>', methods=['POST'])
def api_cancel_order_client(order_id):
    order = orders.get(order_id)
    if order:
        order['status'] = 'cancelled'
        driver_id = order.get('driver_id')
        if driver_id:
            try:
                bot.send_message(driver_id, "⚠️ Клиент отменил заказ.")
            except:
                pass
        driver_locations.pop(order_id, None)
        if order['client_id'] in user_state:
            user_state[order['client_id']].pop("current_order", None)
        save_data()
    return jsonify({'ok': True})

# === ТЕЛЕГРАМ БОТ ===
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
        bot.send_message(uid, "👋 Водитель", reply_markup=main_menu_driver(uid))
        return
    
    if uid in pending_drivers:
        bot.send_message(uid, t("pending", uid))
        return
    
    if uid not in user_state:
        user_state[uid] = {"role": None, "lang": "ru"}
    
    bot.send_message(uid, "🌍 Vali keel / Выберите язык:", reply_markup=lang_kb())

# === КОМАНДЫ ДЛЯ ПЕРЕКЛЮЧЕНИЯ РОЛЕЙ ===
@bot.message_handler(commands=["client"])
def force_client(msg):
    uid = msg.from_user.id
    user_state[uid] = {"role": "client", "lang": get_lang(uid)}
    save_data()
    bot.send_message(uid, "👋 *Вы перешли в режим клиента*", parse_mode="Markdown", reply_markup=main_menu_client(uid))

@bot.message_handler(commands=["driver"])
def force_driver(msg):
    uid = msg.from_user.id
    if uid not in drivers:
        drivers[uid] = {
            "approved": True, "online": False,
            "full_name": msg.from_user.first_name or "Водитель",
            "car": "Не указано", "phone": "Не указано",
            "lang": get_lang(uid),
            "earnings": 0, "trips": 0, "balance": 0
        }
    user_state[uid] = {"role": "driver", "lang": get_lang(uid)}
    save_data()
    bot.send_message(uid, "🧑‍✈️ *Вы перешли в режим водителя*", parse_mode="Markdown", reply_markup=main_menu_driver(uid))

@bot.message_handler(commands=["admin"])
def force_admin(msg):
    uid = msg.from_user.id
    if is_admin(uid):
        user_state[uid] = {"role": "admin", "lang": "ru"}
        save_data()
        bot.send_message(uid, "👨‍💼 *Панель администратора*", parse_mode="Markdown", reply_markup=main_menu_admin())
    else:
        bot.send_message(uid, "⛔ Нет доступа")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def cb_lang(call):
    uid = call.from_user.id
    lang = call.data.split("_")[1]
    user_state[uid]["lang"] = lang
    bot.edit_message_text(t("welcome", uid), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=role_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("role_"))
def cb_role(call):
    uid = call.from_user.id
    role = call.data.split("_")[1]
    
    if role == "client":
        user_state[uid]["role"] = "client"
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(uid, "👋 Добро пожаловать! Нажмите кнопку чтобы заказать такси.", reply_markup=main_menu_client(uid))
    else:
        if uid in pending_drivers:
            bot.edit_message_text(t("pending", uid), call.message.chat.id, call.message.message_id)
            return
        if is_approved_driver(uid):
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(uid, "👋", reply_markup=main_menu_driver(uid))
            return
        user_state[uid]["role"] = "driver_reg"
        user_state[uid]["reg_step"] = "name"
        bot.edit_message_text(t("reg_driver", uid), call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("reg_step") == "name")
def reg_name(msg):
    uid = msg.from_user.id
    user_state[uid]["reg_name"] = msg.text
    user_state[uid]["reg_step"] = "car"
    bot.send_message(uid, t("ask_car", uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("reg_step") == "car")
def reg_car(msg):
    uid = msg.from_user.id
    user_state[uid]["reg_car"] = msg.text
    user_state[uid]["reg_step"] = "phone"
    bot.send_message(uid, t("ask_phone", uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("reg_step") == "phone")
def reg_phone(msg):
    uid = msg.from_user.id
    state = user_state[uid]
    
    pending_drivers[uid] = {
        "id": uid, "full_name": state.get("reg_name"),
        "car": state.get("reg_car"), "phone": msg.text,
        "username": msg.from_user.username or "—",
        "lang": get_lang(uid), "registered": now_str()
    }
    state["reg_step"] = None
    save_data()
    
    bot.send_message(uid, t("pending", uid))
    try:
        bot.send_message(ADMIN_ID, f"🔔 *Новая заявка!*\n\n👤 {state['reg_name']}\n🚗 {state['reg_car']}\n📱 {msg.text}", parse_mode="Markdown", reply_markup=approve_driver_kb(uid))
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
def cb_approve(call):
    if not is_admin(call.from_user.id):
        return
    
    action, driver_id = call.data.split("_", 1)
    driver_id = int(driver_id)
    pending = pending_drivers.get(driver_id)
    
    if not pending:
        bot.answer_callback_query(call.id, "Заявка не найдена")
        return
    
    if action == "approve":
        drivers[driver_id] = {
            "approved": True, "online": False,
            "full_name": pending["full_name"],
            "car": pending["car"], "phone": pending["phone"],
            "lang": pending.get("lang", "ru"),
            "earnings": 0, "trips": 0, "commission": 0, "balance": 10.0
        }
        del pending_drivers[driver_id]
        save_data()
        bot.edit_message_text(f"✅ Водитель *{pending['full_name']}* одобрен!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        user_state[driver_id] = {"role": "driver", "lang": pending.get("lang", "ru")}
        bot.send_message(driver_id, t("approved", driver_id), reply_markup=main_menu_driver(driver_id))
    else:
        del pending_drivers[driver_id]
        save_data()
        bot.edit_message_text(f"❌ Водитель *{pending['full_name']}* отклонён.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.send_message(driver_id, t("rejected", driver_id))

@bot.message_handler(func=lambda m: m.text in ["🚖 Заказать такси", "🚖 Telli takso", "🚖 Order taxi"])
def order_start(msg):
    uid = msg.from_user.id
    
    existing = user_state.get(uid, {}).get("current_order")
    if existing and existing in orders and orders[existing]["status"] in ["pending", "accepted", "arrived"]:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗺️ Отслеживать", web_app=types.WebAppInfo(url=f"{TRACKING_URL}?order={existing}")))
        bot.send_message(uid, "⏳ У вас уже есть активный заказ!", reply_markup=kb)
        return
    
    # ИСПРАВЛЕНО: правильная ссылка на карту
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗺️ Открыть карту", web_app=types.WebAppInfo(url=CLIENT_URL)))
    bot.send_message(uid, "📍 Нажмите кнопку чтобы выбрать маршрут:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["🗺️ Карта", "🗺️ Kaart", "🗺️ Map"])
def driver_map(msg):
    uid = msg.from_user.id
    if is_approved_driver(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗺️ Открыть карту", web_app=types.WebAppInfo(url=DRIVER_URL)))
        bot.send_message(uid, "🗺️ Карта заказов:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["🟢 Я онлайн", "🟢 Olen online", "🟢 I'm online"])
def driver_online(msg):
    uid = msg.from_user.id
    if is_approved_driver(uid):
        drivers[uid]["online"] = True
        save_data()
        bot.send_message(uid, "🟢 Вы онлайн", reply_markup=main_menu_driver(uid))

@bot.message_handler(func=lambda m: m.text in ["⚫ Я офлайн", "⚫ Olen offline", "⚫ I'm offline"])
def driver_offline(msg):
    uid = msg.from_user.id
    if is_approved_driver(uid):
        drivers[uid]["online"] = False
        save_data()
        bot.send_message(uid, "⚫ Вы офлайн", reply_markup=main_menu_driver(uid))

@bot.message_handler(func=lambda m: m.text in ["📊 Заработок", "📊 Tulu", "📊 Earnings"])
def driver_earnings(msg):
    uid = msg.from_user.id
    if is_approved_driver(uid):
        d = drivers[uid]
        text = f"💰 Баланс: {d.get('balance', 0)}€\n🚖 Поездок: {d.get('trips', 0)}\n💶 Заработано: {d.get('earnings', 0)}€"
        bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text in ["💬 Поддержка", "💬 Tugi", "💬 Support"])
def support(msg):
    bot.send_message(msg.chat.id, "📞 Поддержка: @tltakso_support")

@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_"))
def cb_accept(call):
    driver_id = call.from_user.id
    oid = call.data.split("_")[1]
    
    if has_active_order(driver_id):
        bot.answer_callback_query(call.id, "⚠️ У вас уже есть активный заказ")
        return
    
    with data_lock:
        order = orders.get(oid)
        if not order or order.get('status') != 'pending':
            bot.answer_callback_query(call.id, "Заказ уже недоступен")
            return
        
        order['status'] = 'accepted'
        order['driver_id'] = driver_id
        order['driver_name'] = drivers[driver_id]['full_name']
        
        drivers[driver_id]['trips'] = drivers[driver_id].get('trips', 0) + 1
        drivers[driver_id]['earnings'] = drivers[driver_id].get('earnings', 0) + order.get('driver_gets', 0)
        if order.get('pay_type') == 'cash':
            drivers[driver_id]['balance'] = drivers[driver_id].get('balance', 0) - 1
    
    save_data()
    
    bot.edit_message_text(
        f"✅ *Заказ #{oid} принят!*\n\n📍 {order['from'][:40]}\n🏁 {order['to'][:40]}\n💰 {order['driver_gets']}€",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=driver_active_kb(oid)
    )
    
    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗺️ Следить за водителем", web_app=types.WebAppInfo(url=f"{TRACKING_URL}?order={oid}")))
        bot.send_message(order['client_id'], f"🚖 *Водитель найден!*\n\n👤 {drivers[driver_id]['full_name']}\n🚗 {drivers[driver_id]['car']}", parse_mode="Markdown", reply_markup=kb)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("decline_"))
def cb_decline(call):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "Отклонён")

@bot.callback_query_handler(func=lambda c: c.data.startswith("arrived_"))
def cb_arrived(call):
    oid = call.data.split("_")[1]
    order = orders.get(oid)
    
    if order and order.get('status') == 'accepted':
        order['status'] = 'arrived'
        save_data()
        bot.answer_callback_query(call.id, "✅ Клиент уведомлён!")
        try:
            bot.send_message(order['client_id'], f"📍 *Водитель прибыл!*\n\n🚖 {order.get('driver_name', 'Водитель')} ждёт вас.", parse_mode="Markdown")
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(call):
    oid = call.data.split("_")[1]
    order = orders.get(oid)
    
    if order and order.get('status') in ['accepted', 'arrived']:
        order['status'] = 'done'
        driver_locations.pop(oid, None)
        save_data()
        
        bot.edit_message_text(f"✅ *Поездка #{oid} завершена!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        try:
            bot.send_message(order['client_id'], "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!", parse_mode="Markdown")
        except:
            pass
        
        if order['client_id'] in user_state:
            user_state[order['client_id']].pop("current_order", None)

@bot.callback_query_handler(func=lambda c: c.data.startswith("driver_cancel_"))
def cb_driver_cancel(call):
    oid = call.data.split("_")[-1]
    order = orders.get(oid)
    driver_id = call.from_user.id
    
    if order and order.get('status') in ['accepted', 'arrived']:
        order['status'] = 'pending'
        order['driver_id'] = None
        order.pop('driver_name', None)
        
        drivers[driver_id]['trips'] = max(0, drivers[driver_id].get('trips', 0) - 1)
        drivers[driver_id]['earnings'] = max(0, drivers[driver_id].get('earnings', 0) - order.get('driver_gets', 0))
        if order.get('pay_type') == 'cash':
            drivers[driver_id]['balance'] = drivers[driver_id].get('balance', 0) + 1
        
        driver_locations.pop(oid, None)
        save_data()
        
        bot.edit_message_text(f"❌ Заказ #{oid} отменён.", call.message.chat.id, call.message.message_id)
        
        try:
            bot.send_message(order['client_id'], "⚠️ Водитель отменил заказ. Ищем нового...")
        except:
            pass
        
        notify_drivers(oid)

# === АДМИН ===
@bot.message_handler(func=lambda m: m.text == "👥 Водители" and is_admin(m.from_user.id))
def admin_drivers(msg):
    online = [(uid, d) for uid, d in drivers.items() if d.get("online") and d.get("approved")]
    text = f"🟢 Онлайн: {len(online)}\n\n"
    for uid, d in online[:10]:
        busy = "🚖 Занят" if has_active_order(uid) else "✅ Свободен"
        text += f"👤 {d['full_name']}\n🚗 {d['car']}\n💰 {d.get('balance',0)}€ {busy}\n\n"
    bot.send_message(msg.chat.id, text or "Нет водителей онлайн", reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "📋 Заказы" and is_admin(m.from_user.id))
def admin_orders(msg):
    if not orders:
        bot.send_message(msg.chat.id, "Заказов нет")
        return
    text = f"📋 Заказов: {len(orders)}\n\n"
    for oid, o in list(orders.items())[-10:]:
        text += f"#{oid} · {o.get('client_name', '—')} · {o.get('price', 0)}€ · {o.get('status', '—')}\n"
    bot.send_message(msg.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and is_admin(m.from_user.id))
def admin_stats(msg):
    total = len(orders)
    done = len([o for o in orders.values() if o.get('status') == 'done'])
    revenue = sum(d.get("commission", 0) for d in drivers.values())
    bot.send_message(msg.chat.id, f"📊 Статистика\n\n🚖 Заказов: {total}\n✅ Завершено: {done}\n💰 Сбор: {revenue}€\n👥 Водителей: {len(drivers)}")

# === ЗАПУСК ===
def setup_webhook():
    webhook_url = f"https://{RAILWAY_DOMAIN}/webhook"
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook: {webhook_url}")
    except Exception as e:
        print(f"❌ Webhook error: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return '', 200
    return abort(403)

def auto_save_worker():
    while True:
        time.sleep(60)
        save_data()
        print(f"💾 Автосохранение: {len(orders)} заказов")

if __name__ == "__main__":
    print("🚖 TL.TAKSO Bot запускается...")
    
    threading.Thread(target=auto_save_worker, daemon=True).start()
    
    setup_webhook()
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    
