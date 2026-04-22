# main.py - TL.TAKSO Bot (улучшенная версия)
import os
import sys
import json
import time
import threading
import re
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

# Директория данных (важно для Railway!)
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(exist_ok=True)

# Файл с данными
DATA_FILE = DATA_DIR / "tltakso_data.json"

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# === ЗАГРУЗКА ДАННЫХ ===
data_lock = threading.Lock()

def load_data():
    """Загрузка данных из JSON"""
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"orders": {}, "drivers": {}, "user_state": {}, "pending_drivers": {}, "order_counter": 1}

def save_data():
    """Сохранение данных в JSON"""
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

# Загружаем данные
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
        "car": "Toyota", "phone": "+372", "lang": "ru",
        "earnings": 0, "trips": 0, "balance": 100.0
    }

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def new_order_id():
    oid = f"TL{order_counter[0]:04d}"
    order_counter[0] += 1
    return oid

def is_admin(uid):
    return uid == ADMIN_ID

def get_lang(uid):
    return user_state.get(uid, {}).get("lang", "ru")

# === FLASK ROUTES ===
@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'orders': len(orders)})

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
            })
    return jsonify(result)

@app.route('/api/create_order', methods=['POST'])
def api_create_order():
    try:
        data = request.get_json()
        client_id = int(data.get('client_id', 0))
        oid = new_order_id()
        
        orders[oid] = {
            "id": oid,
            "client_id": client_id,
            "client_name": data.get('client_name', 'Клиент'),
            "from": data.get('from_address', '—'),
            "to": data.get('to_address', '—'),
            "from_lat": data.get('from_lat', 0),
            "from_lon": data.get('from_lon', 0),
            "to_lat": data.get('to_lat', 0),
            "to_lon": data.get('to_lon', 0),
            "price": data.get('price', 0),
            "driver_gets": data.get('driver_gets', 0),
            "pay_type": data.get('payment', 'cash'),
            "status": "pending",
            "driver_id": None,
            "created": datetime.now().strftime("%H:%M")
        }
        
        if client_id not in user_state:
            user_state[client_id] = {}
        user_state[client_id]["current_order"] = oid
        
        save_data()
        
        # Уведомляем водителей
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
    return jsonify({
        'ok': True,
        'status': order.get('status'),
        'driver_name': order.get('driver_name', ''),
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
    
    save_data()
    return jsonify({'ok': True})

@app.route('/api/complete_order/<order_id>', methods=['POST'])
def api_complete_order(order_id):
    order = orders.get(order_id)
    if order:
        order['status'] = 'done'
        driver_locations.pop(order_id, None)
        save_data()
    return jsonify({'ok': True})

@app.route('/api/cancel_order_client/<order_id>', methods=['POST'])
def api_cancel_order_client(order_id):
    order = orders.get(order_id)
    if order:
        order['status'] = 'cancelled'
        driver_locations.pop(order_id, None)
        save_data()
    return jsonify({'ok': True})

def notify_drivers(oid):
    order = orders.get(oid)
    if not order:
        return
    
    text = f"🔔 *Новый заказ #{oid}*\n📍 {order['from'][:30]}\n🏁 {order['to'][:30]}\n💰 {order['driver_gets']}€"
    
    for driver_id, d in drivers.items():
        if d.get("approved") and d.get("online"):
            try:
                kb = types.InlineKeyboardMarkup()
                kb.row(
                    types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{oid}"),
                    types.InlineKeyboardButton("❌ Отказать", callback_data=f"decline_{oid}")
                )
                bot.send_message(driver_id, text, parse_mode="Markdown", reply_markup=kb)
            except:
                pass

# === ТЕЛЕГРАМ БОТ ===
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid = msg.from_user.id
    
    if uid not in user_state:
        user_state[uid] = {"role": None, "lang": "ru"}
    
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇪🇪 Eesti", callback_data="lang_et")
    )
    bot.send_message(uid, "🌍 Выберите язык / Vali keel:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def cb_lang(call):
    uid = call.from_user.id
    lang = call.data.split("_")[1]
    user_state[uid]["lang"] = lang
    
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🚖 Я клиент", callback_data="role_client"),
        types.InlineKeyboardButton("🧑‍✈️ Я водитель", callback_data="role_driver")
    )
    bot.edit_message_text("Кто вы?", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("role_"))
def cb_role(call):
    uid = call.from_user.id
    role = call.data.split("_")[1]
    
    user_state[uid]["role"] = role
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    
    if role == "client":
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("🚖 Заказать такси")
        bot.send_message(uid, "👋 Добро пожаловать! Нажмите кнопку чтобы заказать такси.", reply_markup=kb)
    else:
        bot.send_message(uid, "🧑‍✈️ Регистрация водителя. Введите ваше полное имя:")

@bot.message_handler(func=lambda m: m.text == "🚖 Заказать такси")
def order_start(msg):
    uid = msg.from_user.id
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗺️ Открыть карту", web_app=types.WebAppInfo(url=f"https://{RAILWAY_DOMAIN}")))
    bot.send_message(uid, "📍 Нажмите кнопку чтобы выбрать маршрут:", reply_markup=kb)

@bot.message_handler(content_types=['web_app_data'])
def handle_webapp(msg):
    uid = msg.from_user.id
    data = json.loads(msg.web_app_data.data)
    
    oid = new_order_id()
    orders[oid] = {
        "id": oid,
        "client_id": uid,
        "client_name": msg.from_user.first_name,
        "from": data.get('from_address', '—'),
        "to": data.get('to_address', '—'),
        "from_lat": data.get('from_lat', 0),
        "from_lon": data.get('from_lon', 0),
        "to_lat": data.get('to_lat', 0),
        "to_lon": data.get('to_lon', 0),
        "price": data.get('price', 0),
        "driver_gets": data.get('driver_gets', 0),
        "pay_type": data.get('payment', 'cash'),
        "status": "pending",
        "driver_id": None,
        "created": datetime.now().strftime("%H:%M")
    }
    
    user_state[uid] = user_state.get(uid, {})
    user_state[uid]["current_order"] = oid
    save_data()
    
    bot.send_message(uid, f"✅ Заказ #{oid} создан! Ищем водителя...")
    notify_drivers(oid)

@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_"))
def cb_accept(call):
    driver_id = call.from_user.id
    oid = call.data.split("_")[1]
    
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
    
    save_data()
    
    bot.edit_message_text(
        f"✅ Заказ #{oid} принят!\n📍 {order['from'][:30]}\n🏁 {order['to'][:30]}",
        call.message.chat.id, call.message.message_id
    )
    
    # Уведомляем клиента
    try:
        tracking_url = f"https://{RAILWAY_DOMAIN}/static/tracking.html?order={oid}"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🗺️ Следить за водителем", web_app=types.WebAppInfo(url=tracking_url)))
        bot.send_message(order['client_id'], 
            f"🚖 Водитель найден!\n👤 {drivers[driver_id]['full_name']}\n🚗 {drivers[driver_id]['car']}", 
            reply_markup=kb)
    except:
        pass

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
    
    # Фоновое сохранение каждую минуту
    threading.Thread(target=auto_save_worker, daemon=True).start()
    
    # Настройка webhook
    setup_webhook()
    
    # Запуск Flask
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    
