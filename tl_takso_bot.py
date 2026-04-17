import telebot
from telebot import types
import datetime
import os
import json
import time
import threading
from flask import Flask, send_from_directory, request, abort, jsonify
import re

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен")

MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "pk.eyJ1IjoidGx0YWtzbyIsImEiOiJjbW4zYW0yMGkxNG13MnByM2hoZng0OXh2In0.ArR_nk-dVg99VhuuatH2hA")
RAILWAY_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or os.environ.get("RAILWAY_STATIC_URL", "web-production-f5a52.up.railway.app")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", BOT_TOKEN.split(':')[1][:16])
MINI_APP_URL = f"https://{RAILWAY_DOMAIN}/static/miniapp.html"
DRIVER_MAP_URL = f"https://{RAILWAY_DOMAIN}/static/driver.html"
TRACKING_URL = f"https://{RAILWAY_DOMAIN}/static/tracking.html"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1873195803"))

DATA_FILE = "/mnt/data/tltakso_data.json"
data_lock = threading.Lock()

# Хранилище геопозиций водителей: {order_id: {lat, lon, updated}}
driver_locations = {}

# Резервы заказов: {order_id: {driver_id, driver_name, expires}}
order_reserves = {}

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

def cleanup_reserves():
    """Очищает истёкшие резервы и переводит заказы обратно в пул"""
    while True:
        time.sleep(3)
        now = time.time()
        expired = [oid for oid, r in list(order_reserves.items()) if r['expires'] < now]
        for oid in expired:
            order_reserves.pop(oid, None)
            order = orders.get(oid)
            if order and order.get('status') == 'pending':
                print(f"⏰ Резерв истёк для заказа #{oid}, возвращаем в пул")

orders = {}
user_state = {}
drivers = {}
pending_drivers = {}
order_counter = [1]

load_data()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

if ADMIN_ID not in drivers:
    drivers[ADMIN_ID] = {
        "approved": True, "online": True, "full_name": "S.L.",
        "car": "Toyota Camry", "phone": "+123456789", "lang": "ru",
        "earnings": 0, "trips": 0, "commission": 0, "balance": 50.0
    }

# ── FLASK ROUTES ──

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
        if order.get('status') != 'pending':
            continue
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
        if not data:
            return jsonify({'ok': False, 'error': 'No data'}), 400
        client_id = data.get('client_id')
        client_name = data.get('client_name', 'Клиент')
        if not client_id:
            return jsonify({'ok': False, 'error': 'No client_id'}), 400
        client_id = int(client_id)
        oid = new_order_id()
        orders[oid] = {
            "id": oid, "client_id": client_id, "client_name": client_name,
            "from": data.get("from_address", "—"), "to": data.get("to_address", "—"),
            "from_lat": data.get("from_lat", 0), "from_lon": data.get("from_lon", 0),
            "to_lat": data.get("to_lat", 0), "to_lon": data.get("to_lon", 0),
            "time": data.get("time", "Сейчас"),
            "payment": "💳 Карта" if data.get("payment") == "card" else "💵 Наличные",
            "pay_type": data.get("payment", "cash"),
            "price": data.get("price", 0),
            "driver_gets": data.get("driver_gets", data.get("price", 0)),
            "status": "pending", "created": now_str(),
            "driver_id": None, "client_lang": "ru"
        }
        if client_id not in user_state:
            user_state[client_id] = {}
        user_state[client_id]["current_order"] = oid
        save_data()
        try:
            bot.send_message(client_id,
                f"✅ *Заказ #{oid} создан!*\n\n📍 {orders[oid]['from'][:50]}\n🏁 {orders[oid]['to'][:50]}\n💰 *{orders[oid]['price']}€*\n\n⏳ Ищем водителя...",
                parse_mode="Markdown", reply_markup=main_menu_client(client_id))
        except Exception as e:
            print(f"Ошибка отправки клиенту: {e}")
        notify_drivers(oid)
        return jsonify({'ok': True, 'order_id': oid})
    except Exception as e:
        print(f"Ошибка create_order: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/reserve_order/<order_id>', methods=['POST'])
def api_reserve_order(order_id):
    """Водитель резервирует заказ на 10 секунд"""
    try:
        data = request.get_json()
        driver_id = data.get('driver_id')
        driver_name = data.get('driver_name', 'Водитель')
        if not driver_id:
            return jsonify({'ok': False, 'error': 'No driver_id'}), 400
        driver_id = int(driver_id)
        with data_lock:
            order = orders.get(order_id)
            if not order:
                return jsonify({'ok': False, 'error': 'Not found'}), 404
            if order.get('status') != 'pending':
                return jsonify({'ok': False, 'error': 'Already taken'}), 409
            # Проверяем существующий резерв
            existing = order_reserves.get(order_id)
            if existing and existing['expires'] > time.time():
                if existing['driver_id'] != driver_id:
                    return jsonify({'ok': False, 'error': 'Reserved'}), 409
            # Ставим резерв на 10 секунд
            order_reserves[order_id] = {
                'driver_id': driver_id,
                'driver_name': driver_name,
                'expires': time.time() + 10
            }
        return jsonify({'ok': True, 'expires_in': 10})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/confirm_order/<order_id>', methods=['POST'])
def api_confirm_order(order_id):
    """Водитель подтверждает резерв → заказ принят"""
    try:
        data = request.get_json()
        driver_id = data.get('driver_id')
        driver_name = data.get('driver_name', 'Водитель')
        if not driver_id:
            return jsonify({'ok': False, 'error': 'No driver_id'}), 400
        driver_id = int(driver_id)
        with data_lock:
            order = orders.get(order_id)
            if not order:
                return jsonify({'ok': False, 'error': 'Not found'}), 404
            if order.get('status') != 'pending':
                return jsonify({'ok': False, 'error': 'Already taken'}), 409
            reserve = order_reserves.get(order_id)
            if not reserve:
                return jsonify({'ok': False, 'error': 'No reserve'}), 409
            if reserve['driver_id'] != driver_id:
                return jsonify({'ok': False, 'error': 'Reserved by other'}), 409
            if reserve['expires'] < time.time():
                order_reserves.pop(order_id, None)
                return jsonify({'ok': False, 'error': 'Reserve expired'}), 409
            # Всё ок — принимаем
            order['status'] = 'accepted'
            order['driver_id'] = driver_id
            order['driver_name'] = driver_name
            order_reserves.pop(order_id, None)
        if driver_id in drivers:
            drivers[driver_id]['trips'] = drivers[driver_id].get('trips', 0) + 1
            drivers[driver_id]['earnings'] = drivers[driver_id].get('earnings', 0) + order.get('driver_gets', 0)
            drivers[driver_id]['commission'] = drivers[driver_id].get('commission', 0) + 1
            if order.get('pay_type') == 'cash':
                drivers[driver_id]['balance'] = drivers[driver_id].get('balance', 0) - 1
        save_data()
        try:
            tracking_url = f"{TRACKING_URL}?order={order_id}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="🗺️ Следить за водителем", web_app=types.WebAppInfo(url=tracking_url)))
            d = drivers.get(driver_id, {})
            bot.send_message(order['client_id'],
                f"🚖 *Водитель найден!*\n\n👤 {d.get('full_name', driver_name)}\n🚗 {d.get('car', '')}\n⏱ Едет к вам...",
                parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")
        return jsonify({'ok': True, 'order_id': order_id})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/accept_order/<order_id>', methods=['POST'])
def api_accept_order(order_id):
    try:
        data = request.get_json()
        driver_id = data.get('driver_id')
        driver_name = data.get('driver_name', 'Водитель')
        if not driver_id:
            return jsonify({'ok': False, 'error': 'No driver_id'}), 400
        driver_id = int(driver_id)
        order = orders.get(order_id)
        if not order:
            return jsonify({'ok': False, 'error': 'Not found'}), 404
        if order.get('status') != 'pending':
            return jsonify({'ok': False, 'error': 'Already taken'}), 409
        order['status'] = 'accepted'
        order['driver_id'] = driver_id
        order['driver_name'] = driver_name
        if driver_id in drivers:
            drivers[driver_id]["trips"] = drivers[driver_id].get("trips", 0) + 1
            drivers[driver_id]["earnings"] = drivers[driver_id].get("earnings", 0) + order.get("driver_gets", 0)
            drivers[driver_id]["commission"] = drivers[driver_id].get("commission", 0) + 1
            if order.get("pay_type") == "cash":
                drivers[driver_id]["balance"] = drivers[driver_id].get("balance", 0) - 1
        save_data()
        # Уведомить клиента с кнопкой слежения
        try:
            tracking_url = f"{TRACKING_URL}?order={order_id}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="🗺️ Следить за водителем", web_app=types.WebAppInfo(url=tracking_url)))
            d = drivers.get(driver_id, {})
            bot.send_message(order["client_id"],
                f"🚖 *Водитель найден!*\n\n👤 {d.get('full_name', driver_name)}\n🚗 {d.get('car', '')}\n⏱ Едет к вам...",
                parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")
        return jsonify({'ok': True, 'order_id': order_id})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/reject_order/<order_id>', methods=['POST'])
def api_reject_order_driver(order_id):
    return jsonify({'ok': True})

@app.route('/api/driver_location/<order_id>', methods=['POST'])
def api_driver_location(order_id):
    """Водитель отправляет свою геопозицию"""
    try:
        data = request.get_json()
        lat = data.get('lat')
        lon = data.get('lon')
        if lat is None or lon is None:
            return jsonify({'ok': False}), 400
        driver_locations[order_id] = {
            'lat': lat, 'lon': lon,
            'updated': time.time()
        }
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/order_status/<order_id>', methods=['GET'])
def api_order_status(order_id):
    """Клиент запрашивает статус заказа и позицию водителя"""
    order = orders.get(order_id)
    if not order:
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    loc = driver_locations.get(order_id)
    result = {
        'ok': True,
        'status': order.get('status'),
        'driver_name': order.get('driver_name', ''),
        'driver_lat': loc['lat'] if loc else None,
        'driver_lon': loc['lon'] if loc else None,
        'to_lat': order.get('to_lat'),
        'to_lon': order.get('to_lon'),
        'from_lat': order.get('from_lat'),
        'from_lon': order.get('from_lon'),
    }
    return jsonify(result)

@app.route('/api/arrived/<order_id>', methods=['POST'])
def api_arrived(order_id):
    """Водитель нажал 'Я прибыл'"""
    try:
        order = orders.get(order_id)
        if not order or order['status'] != 'accepted':
            return jsonify({'ok': False}), 400
        order['status'] = 'arrived'
        save_data()
        try:
            bot.send_message(order['client_id'],
                f"📍 *Водитель прибыл!*\n\n🚖 {order.get('driver_name', 'Водитель')} ждёт вас. Выходите! 😊",
                parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка уведомления: {e}")
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/complete_order/<order_id>', methods=['POST'])
def api_complete_order(order_id):
    """Водитель завершил поездку"""
    try:
        order = orders.get(order_id)
        if not order or order['status'] not in ['accepted', 'arrived']:
            return jsonify({'ok': False}), 400
        order['status'] = 'done'
        save_data()
        driver_locations.pop(order_id, None)
        try:
            bot.send_message(order['client_id'],
                "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!",
                parse_mode="Markdown", reply_markup=main_menu_client(order['client_id']))
        except Exception as e:
            print(f"Ошибка уведомления: {e}")
        if order['client_id'] in user_state:
            user_state[order['client_id']].pop("current_order", None)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/cancel_order_driver/<order_id>', methods=['POST'])
def api_cancel_order_driver(order_id):
    """Водитель отменил заказ"""
    try:
        data = request.get_json() or {}
        driver_id = data.get('driver_id')
        order = orders.get(order_id)
        if not order or order['status'] not in ['accepted', 'arrived']:
            return jsonify({'ok': False}), 400
        order['status'] = 'pending'
        order['driver_id'] = None
        order.pop('driver_name', None)
        if driver_id:
            driver_id = int(driver_id)
            if driver_id in drivers:
                drivers[driver_id]['trips'] = max(0, drivers[driver_id].get('trips', 0) - 1)
                drivers[driver_id]['earnings'] = max(0, drivers[driver_id].get('earnings', 0) - order.get('driver_gets', 0))
                drivers[driver_id]['commission'] = max(0, drivers[driver_id].get('commission', 0) - 1)
                if order.get('pay_type') == 'cash':
                    drivers[driver_id]['balance'] = drivers[driver_id].get('balance', 0) + 1
        driver_locations.pop(order_id, None)
        save_data()
        try:
            bot.send_message(order['client_id'], "⚠️ Водитель отменил заказ. Ищем нового...")
        except:
            pass
        notify_drivers(order_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/cancel_order_client/<order_id>', methods=['POST'])
def api_cancel_order_client(order_id):
    """Клиент отменил заказ через Mini App"""
    try:
        order = orders.get(order_id)
        if not order or order['status'] not in ['pending', 'accepted', 'arrived']:
            return jsonify({'ok': False}), 400
        order['status'] = 'cancelled'
        driver_id = order.get('driver_id')
        if driver_id and driver_id in drivers:
            try:
                bot.send_message(driver_id, "⚠️ Клиент отменил заказ.")
            except:
                pass
            drivers[driver_id]['trips'] = max(0, drivers[driver_id].get('trips', 0) - 1)
            drivers[driver_id]['earnings'] = max(0, drivers[driver_id].get('earnings', 0) - order.get('driver_gets', 0))
            drivers[driver_id]['commission'] = max(0, drivers[driver_id].get('commission', 0) - 1)
            if order.get('pay_type') == 'cash':
                drivers[driver_id]['balance'] = drivers[driver_id].get('balance', 0) + 1
        driver_locations.pop(order_id, None)
        client_id = order['client_id']
        if client_id in user_state:
            user_state[client_id].pop("current_order", None)
        save_data()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/active_order', methods=['GET'])
def api_active_order():
    """Проверяет есть ли у клиента активный заказ"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'ok': False}), 400
        user_id = int(user_id)
        oid = user_state.get(user_id, {}).get('current_order')
        if oid and oid in orders:
            order = orders[oid]
            if order.get('status') in ['pending', 'accepted', 'arrived']:
                return jsonify({'ok': True, 'order_id': oid, 'status': order['status']})
        return jsonify({'ok': False})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
    return jsonify({'status': 'ok', 'orders': len(orders), 'drivers': len(drivers)}), 200

# ═══════════════════════════════════════════════════════════════
# ══════════════ API ДЛЯ MINI APP (клиент) ═══════════════════════
# ═══════════════════════════════════════════════════════════════

@app.route('/api/create_order', methods=['POST'])
def api_create_order():
    data = request.get_json()
    oid = new_order_id()
    
    orders[oid] = {
        "id": oid,
        "client_id": data.get('client_id'),
        "client_name": data.get('client_name'),
        "from": data.get('from_address'),
        "to": data.get('to_address'),
        "from_lat": data.get('from_lat'),
        "from_lon": data.get('from_lon'),
        "to_lat": data.get('to_lat'),
        "to_lon": data.get('to_lon'),
        "price": data.get('price'),
        "driver_gets": data.get('driver_gets'),
        "payment": data.get('payment'),
        "time": data.get('time'),
        "status": "pending",
        "created": now_str(),
        "driver_id": None
    }
    save_data()
    
    # Уведомляем водителей
    notify_drivers(oid)
    
    return jsonify({'ok': True, 'order_id': oid})

@app.route('/api/order_status/<order_id>', methods=['GET'])
def api_order_status(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({'ok': False, 'error': 'Заказ не найден'})
    
    driver = drivers.get(order.get('driver_id')) if order.get('driver_id') else None
    
    return jsonify({
        'ok': True,
        'status': order.get('status'),
        'driver_lat': driver.get('last_lat') if driver else None,
        'driver_lon': driver.get('last_lon') if driver else None
    })

@app.route('/api/active_order', methods=['GET'])
def api_active_order():
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({'ok': False, 'error': 'user_id required'})
    
    for oid, order in orders.items():
        if order.get('client_id') == user_id and order.get('status') in ['pending', 'accepted', 'arrived']:
            return jsonify({'ok': True, 'order_id': oid, 'status': order.get('status')})
    
    return jsonify({'ok': False})

@app.route('/api/cancel_order', methods=['POST'])
def api_cancel_order():
    data = request.get_json()
    order_id = data.get('order_id')
    user_id = data.get('user_id')
    
    order = orders.get(order_id)
    if not order:
        return jsonify({'ok': False, 'error': 'Заказ не найден'})
    
    if order.get('client_id') != user_id:
        return jsonify({'ok': False, 'error': 'Не ваш заказ'})
    
    if order.get('status') in ['done', 'cancelled']:
        return jsonify({'ok': False, 'error': 'Заказ уже завершён'})
    
    order['status'] = 'cancelled'
    save_data()
    
    # Уведомить водителя
    if order.get('driver_id'):
        try:
            bot.send_message(order['driver_id'], f"❌ Клиент отменил заказ #{order_id}")
        except:
            pass
    
    return jsonify({'ok': True})

@app.route('/api/driver_location/<order_id>', methods=['POST'])
def api_driver_location(order_id):
    data = request.get_json()
    driver_id = data.get('driver_id')
    lat = data.get('lat')
    lon = data.get('lon')
    
    order = orders.get(order_id)
    if order and order.get('driver_id') == driver_id:
        if driver_id in drivers:
            drivers[driver_id]['last_lat'] = lat
            drivers[driver_id]['last_lon'] = lon
            save_data()
    
    return jsonify({'ok': True})

# ── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ──

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

def notify_drivers(oid):
    order = orders.get(oid)
    if not order:
        return

    print(f"🔔 Новый заказ #{oid}, всего водителей: {len(drivers)}")

    text = (f"🔔 *Новый заказ #{oid}*\n\n"
            f"👤 {order['client_name']}\n"
            f"📍 {order['from'][:40]}\n"
            f"🏁 {order['to'][:40]}\n"
            f"💰 *{order['driver_gets']}€*")

    notified = 0

    for driver_id, d in drivers.items():
        print(f"👉 {driver_id}: approved={d.get('approved')} online={d.get('online')} balance={d.get('balance')}")

        if not d.get("approved"):
            continue
        if not d.get("online"):
            continue
        if has_active_order(driver_id):
            continue

        try:
            bot.send_message(
                driver_id,
                text,
                parse_mode="Markdown",
                reply_markup=driver_order_kb(oid)
            )
            print(f"✅ Отправлено водителю {driver_id}")
            notified += 1
        except Exception as e:
            print(f"❌ Ошибка водителю {driver_id}: {e}")

    if notified == 0:
        print("⚠️ Нет доступных водителей")
        try:
            bot.send_message(
                order["client_id"],
                "⚠️ Сейчас нет свободных водителей. Попробуйте позже."
            )
        except:
            pass

# ── ПЕРЕВОДЫ ──

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
    "driver_found": {"ru": "🚖 *Водитель найден!*\n\n👤 {name}\n🚗 {car}\n⏱ Едет к вам...", "et": "🚖 *Juht leitud!*\n\n👤 {name}\n🚗 {car}\n⏱ Sõidab teie juurde...", "en": "🚖 *Driver found!*\n\n👤 {name}\n🚗 {car}\n⏱ On the way..."},
    "arrived": {"ru": "📍 *Водитель прибыл!*\n\n🚖 {name} ждёт вас. Выходите! 😊", "et": "📍 *Juht on kohal!*\n\n🚖 {name} ootab teid. Tulge välja! 😊", "en": "📍 *Driver arrived!*\n\n🚖 {name} is waiting. Please come out! 😊"},
    "trip_done": {"ru": "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!", "et": "🏁 *Sõit lõpetatud!*\n\nTäname, et valisite TL.TAKSO!", "en": "🏁 *Trip completed!*\n\nThank you for choosing TL.TAKSO!"},
    "cancel_order": {"ru": "❌ Отменить заказ", "et": "❌ Tühista tellimus", "en": "❌ Cancel order"},
    "order_cancelled": {"ru": "❌ Заказ отменён.", "et": "❌ Tellimus tühistatud.", "en": "❌ Order cancelled."},
    "driver_cancelled": {"ru": "⚠️ Клиент отменил заказ.", "et": "⚠️ Klient tühistas tellimuse.", "en": "⚠️ Client cancelled the order."},
    "reg_driver": {"ru": "🧑‍✈️ *Регистрация водителя*\n\nВведите ваше полное имя:", "et": "🧑‍✈️ *Juhi registreerimine*\n\nSisestage oma täisnimi:", "en": "🧑‍✈️ *Driver registration*\n\nEnter your full name:"},
    "ask_car": {"ru": "🚗 Введите марку и номер машины:", "et": "🚗 Sisestage auto mark ja number:", "en": "🚗 Enter car model and plate:"},
    "ask_phone": {"ru": "📱 Введите ваш номер телефона:", "et": "📱 Sisestage oma telefoninumber:", "en": "📱 Enter your phone number:"},
    "pending": {"ru": "⏳ Ваша заявка на рассмотрении.", "et": "⏳ Teie taotlus on läbivaatamisel.", "en": "⏳ Your application is under review."},
    "approved": {"ru": "🎉 *Заявка одобрена!*\n\nНажмите 🟢 Я онлайн чтобы начать!", "et": "🎉 *Taotlus on kinnitatud!*", "en": "🎉 *Application approved!*"},
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

# ── КЛАВИАТУРЫ ──

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

# ── /start ──

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
    user_state[uid] = {"role": "driver", "lang": get_lang(uid)}
    drivers[uid]["online"] = True
    drivers[uid]["approved"] = True
    save_data()
    bot.send_message(uid, "🧑‍✈️ *Теперь вы водитель*",
                     parse_mode="Markdown", reply_markup=main_menu_driver(uid))

@bot.message_handler(commands=["admin"])
def force_admin(msg):
    uid = msg.from_user.id
    user_state[uid] = {"role": "admin", "lang": "ru"}
    save_data()
    bot.send_message(uid, "👨‍💼 *Панель администратора*",
                     parse_mode="Markdown", reply_markup=main_menu_admin())

# ═══════════════════════════════════════════════════════════════
# ═══════════════════ WEBAPP DATA HANDLER ═══════════════════════
# ═══════════════════════════════════════════════════════════════

@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(msg):
    uid = msg.from_user.id
    print(f"📩 WebApp данные от {uid}: {msg.web_app_data.data}")

    try:
        data = json.loads(msg.web_app_data.data)
        oid = new_order_id()

        price = data.get("price", 10)
        orders[oid] = {
            "id": oid,
            "client_id": uid,
            "client_name": msg.from_user.first_name,
            "from": data.get("from_address", data.get("from", "—")),
            "to": data.get("to_address", data.get("to", "—")),
            "from_lat": data.get("from_lat", 0),
            "from_lon": data.get("from_lon", 0),
            "to_lat": data.get("to_lat", 0),
            "to_lon": data.get("to_lon", 0),
            "price": price,
            "driver_gets": data.get("driver_gets", price - 1),
            "pay_type": data.get("payment", "cash"),
            "payment": "💳 Карта" if data.get("payment") == "card" else "💵 Наличные",
            "status": "pending",
            "created": now_str(),
            "driver_id": None,
            "client_lang": get_lang(uid)
        }

        if uid not in user_state:
            user_state[uid] = {}
        user_state[uid]["current_order"] = oid
        save_data()

        bot.send_message(uid,
            f"✅ *Заказ #{oid} создан!*\n\n📍 {orders[oid]['from']}\n🏁 {orders[oid]['to']}\n💰 *{orders[oid]['price']}€*\n\n⏳ Ищем водителя...",
            parse_mode="Markdown")

        notify_drivers(oid)

    except Exception as e:
        print(f"❌ Ошибка обработки webapp: {e}")
        bot.send_message(uid, "❌ Ошибка создания заказа. Попробуйте снова.")

# ── ВЫБОР ЯЗЫКА И РОЛИ ──

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

# ── ЗАКАЗ ТАКСИ ──

@bot.message_handler(func=lambda m: m.text in ["🚖 Заказать такси", "🚖 Telli takso", "🚖 Order taxi"])
def order_start(msg):
    uid = msg.from_user.id
    existing = user_state.get(uid, {}).get("current_order")
    if existing and existing in orders and orders[existing]["status"] in ["pending", "accepted", "arrived"]:
        bot.send_message(uid, "⏳ У вас есть активный заказ!", reply_markup=main_menu_client(uid))
        return
    if uid not in user_state:
        user_state[uid] = {}
    user_state[uid]["step"] = "waiting_webapp"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="🗺️ Выбрать на карте", web_app=types.WebAppInfo(url=MINI_APP_URL)))
    bot.send_message(uid, "📍 Нажмите кнопку чтобы выбрать маршрут на карте:", reply_markup=kb)

# ── ПРИНЯТЬ / ОТКАЗАТЬ (через бот кнопки) ──

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
        # Отправляем водителю кнопки управления заказом
        bot.edit_message_text(
            f"✅ *Заказ #{oid} принят!*\n\n📍 {order['from'][:40]}\n🏁 {order['to'][:40]}\n💰 {order['driver_gets']}€",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=driver_active_kb(oid))
        # Уведомляем клиента с кнопкой слежения
        try:
            tracking_url = f"{TRACKING_URL}?order={oid}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="🗺️ Следить за водителем", web_app=types.WebAppInfo(url=tracking_url)))
            bot.send_message(order["client_id"],
                f"🚖 *Водитель найден!*\n\n👤 {drivers[driver_id]['full_name']}\n🚗 {drivers[driver_id]['car']}\n⏱ Едет к вам...",
                parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"Ошибка уведомления клиента: {e}")
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
        # Обновляем кнопки — убираем "Прибыл", оставляем остальные
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
            reply_markup=driver_arrived_kb(oid))
        try:
            bot.send_message(order["client_id"],
                f"📍 *Водитель прибыл!*\n\n🚖 {order.get('driver_name', 'Водитель')} ждёт вас. Выходите! 😊",
                parse_mode="Markdown")
        except:
            pass
    else:
        bot.answer_callback_query(call.id, "Уже отмечено")

@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if order and order["status"] in ["accepted", "arrived"]:
        order["status"] = "done"
        save_data()
        driver_locations.pop(oid, None)
        bot.edit_message_text(f"✅ *Поездка #{oid} завершена!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        try:
            bot.send_message(order["client_id"], t("trip_done", order["client_id"]),
                parse_mode="Markdown", reply_markup=main_menu_client(order["client_id"]))
        except:
            pass
        if order["client_id"] in user_state:
            user_state[order["client_id"]].pop("current_order", None)
    else:
        bot.answer_callback_query(call.id, "Заказ уже завершён")

@bot.callback_query_handler(func=lambda c: c.data.startswith("driver_cancel_"))
def cb_driver_cancel(call):
    parts = call.data.split("_")
    oid = parts[-1]
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
        driver_locations.pop(oid, None)
        save_data()
        bot.edit_message_text(f"❌ Заказ #{oid} отменён.", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "Заказ отменён")
        try:
            bot.send_message(order["client_id"], "⚠️ Водитель отменил заказ. Ищем нового...", reply_markup=cancel_kb(order["client_id"]))
        except:
            pass
        notify_drivers(oid)
    else:
        bot.answer_callback_query(call.id, "Заказ уже неактивен")

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
                    if order.get("pay_type") == "cash":
                        drivers[order["driver_id"]]["balance"] = drivers[order["driver_id"]].get("balance", 0) + 1
                    drivers[order["driver_id"]]["trips"] = max(0, drivers[order["driver_id"]].get("trips", 0) - 1)
                    drivers[order["driver_id"]]["earnings"] = max(0, drivers[order["driver_id"]].get("earnings", 0) - order.get("driver_gets", 0))
                    drivers[order["driver_id"]]["commission"] = max(0, drivers[order["driver_id"]].get("commission", 0) - 1)
                except:
                    pass
            driver_locations.pop(oid, None)
            save_data()
    try:
        bot.edit_message_text(t("order_cancelled", uid), call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(uid, t("order_cancelled", uid), reply_markup=main_menu_client(uid))
    if uid in user_state:
        user_state[uid].pop("current_order", None)

# ── ВОДИТЕЛИ ──

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
    text = f"{t('balance', msg.from_user.id, bal=d.get('balance', 0))}\n🚖 Поездок: {d.get('trips', 0)}\n💶 Заработано: {d.get('earnings', 0)}€\n📊 Комиссия: {d.get('commission', 0)}€"
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_driver(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["🗺️ Карта", "🗺️ Kaart", "🗺️ Map"] and is_approved_driver(m.from_user.id))
def driver_map(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="🗺️ Открыть карту", web_app=types.WebAppInfo(url=DRIVER_MAP_URL)))
    bot.send_message(msg.chat.id, "🗺️ Карта заказов:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["💬 Поддержка", "💬 Tugi", "💬 Support"])
def support(msg):
    bot.send_message(msg.chat.id, "📞 Поддержка: @tltakso_support")

# ── АДМИН ──

@bot.message_handler(func=lambda m: m.text == "👥 Водители" and is_admin(m.from_user.id))
def admin_drivers(msg):
    online = [(uid, d) for uid, d in drivers.items() if d.get("online") and d.get("approved")]
    text = f"🟢 Онлайн: {len(online)}\n\n"
    for uid, d in online:
        busy = "🚖 Занят" if has_active_order(uid) else "✅ Свободен"
        text += f"👤 {d['full_name']}\n🚗 {d['car']}\n💰 {d.get('balance',0)}€\n{busy}\n\n"
    bot.send_message(msg.chat.id, text or "Нет водителей онлайн", reply_markup=main_menu_admin())

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
    bot.send_message(msg.chat.id,
        f"📊 Статистика\n\n🚖 Заказов: {total}\n✅ Завершено: {done}\n💰 Сбор: {revenue}€\n👥 Водителей: {len(drivers)}",
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
        bot.edit_message_text("🚫 Водитель заблокирован", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(driver_id, "⛔ Ваш аккаунт заблокирован")
        except:
            pass

# ── ЧАТ ──

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

# ── ДОПОЛНИТЕЛЬНЫЕ КЛАВИАТУРЫ ──

def driver_arrived_kb(order_id):
    """Кнопки после прибытия — без кнопки 'Прибыл'"""
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✅ Поездка завершена", callback_data=f"done_{order_id}"))
    kb.row(types.InlineKeyboardButton("❌ Отменить заказ", callback_data=f"driver_cancel_{order_id}"))
    return kb

# ── ЗАПУСК ──

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
    threading.Thread(target=auto_save, daemon=True).start()
    threading.Thread(target=cleanup_reserves, daemon=True).start()
    setup_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
    
