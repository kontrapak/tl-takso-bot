import telebot
from telebot import types
import datetime
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# ── ADMIN ──
ADMIN_ID = 1873195803

# ── ХРАНИЛИЩЕ ──
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
    "ask_from": {
        "ru": "📍 Откуда едем?\n\nВведите адрес:",
        "et": "📍 Kust sõidate?\n\nSisestage aadress:",
        "en": "📍 Where from?\n\nEnter address:"
    },
    "ask_to": {
        "ru": "🏁 Куда едем?\n\nВведите адрес назначения:",
        "et": "🏁 Kuhu sõidate?\n\nSisestage sihtkoha aadress:",
        "en": "🏁 Where to?\n\nEnter destination address:"
    },
    "ask_time": {
        "ru": "⏰ Когда нужна машина?",
        "et": "⏰ Millal vajate autot?",
        "en": "⏰ When do you need the car?"
    },
    "now": {"ru": "⚡ Сейчас", "et": "⚡ Kohe", "en": "⚡ Now"},
    "in15": {"ru": "⏱ +15 мин", "et": "⏱ +15 min", "en": "⏱ +15 min"},
    "in30": {"ru": "⏱ +30 мин", "et": "⏱ +30 min", "en": "⏱ +30 min"},
    "ask_price": {
        "ru": "💰 Выберите тариф:",
        "et": "💰 Valige tariif:",
        "en": "💰 Choose tariff:"
    },
    "ask_payment": {
        "ru": "💳 Способ оплаты?",
        "et": "💳 Makseviis?",
        "en": "💳 Payment method?"
    },
    "card": {"ru": "💳 Карта", "et": "💳 Kaart", "en": "💳 Card"},
    "cash": {"ru": "💵 Наличные", "et": "💵 Sularaha", "en": "💵 Cash"},
    "cancel_order": {"ru": "❌ Отменить заказ", "et": "❌ Tühista tellimus", "en": "❌ Cancel order"},
    "waiting": {
        "ru": "Ожидайте, водитель скоро примет заказ 🚖",
        "et": "Oodake, juht võtab tellimuse varsti vastu 🚖",
        "en": "Please wait, driver will accept soon 🚖"
    },
    "no_drivers": {
        "ru": "😔 Сейчас нет свободных водителей. Попробуйте через несколько минут.",
        "et": "😔 Praegu pole vabu juhte. Proovige mõne minuti pärast.",
        "en": "😔 No drivers available. Please try again in a few minutes."
    },
    "driver_found": {
        "ru": "🚖 *Водитель найден!*\n\n👤 Водитель: {name}\n🚗 Машина: {car}\n⏱ Едет к вам...",
        "et": "🚖 *Juht leitud!*\n\n👤 Juht: {name}\n🚗 Auto: {car}\n⏱ Sõidab teie juurde...",
        "en": "🚖 *Driver found!*\n\n👤 Driver: {name}\n🚗 Car: {car}\n⏱ On the way..."
    },
    "arrived": {
        "ru": "📍 *Водитель прибыл!*\n\n🚖 {name} ждёт вас. Выходите! 😊",
        "et": "📍 *Juht on kohal!*\n\n🚖 {name} ootab teid. Tulge välja! 😊",
        "en": "📍 *Driver arrived!*\n\n🚖 {name} is waiting. Please come out! 😊"
    },
    "trip_done": {
        "ru": "🏁 *Поездка завершена!*\n\nСпасибо что выбрали TL.TAKSO!",
        "et": "🏁 *Sõit lõpetatud!*\n\nTäname, et valisite TL.TAKSO!",
        "en": "🏁 *Trip completed!*\n\nThank you for choosing TL.TAKSO!"
    },
    "reg_driver": {
        "ru": "🧑‍✈️ *Регистрация водителя*\n\nВведите ваше полное имя:",
        "et": "🧑‍✈️ *Juhi registreerimine*\n\nSisestage oma täisnimi:",
        "en": "🧑‍✈️ *Driver registration*\n\nEnter your full name:"
    },
    "ask_car": {
        "ru": "🚗 Введите марку и номер машины:\n\n_Пример: Toyota Camry · 123 ABC_",
        "et": "🚗 Sisestage auto mark ja number:\n\n_Näide: Toyota Camry · 123 ABC_",
        "en": "🚗 Enter car model and plate:\n\n_Example: Toyota Camry · 123 ABC_"
    },
    "ask_phone": {
        "ru": "📱 Введите ваш номер телефона:",
        "et": "📱 Sisestage oma telefoninumber:",
        "en": "📱 Enter your phone number:"
    },
    "pending": {
        "ru": "⏳ Ваша заявка на рассмотрении. Ожидайте одобрения.",
        "et": "⏳ Teie taotlus on läbivaatamisel. Oodake kinnitust.",
        "en": "⏳ Your application is under review. Please wait."
    },
    "approved": {
        "ru": "🎉 *Поздравляем! Ваша заявка одобрена!*\n\nНажмите '🟢 Я онлайн' чтобы начать!",
        "et": "🎉 *Palju õnne! Teie taotlus on kinnitatud!*\n\nVajutage '🟢 Olen online' alustamiseks!",
        "en": "🎉 *Congratulations! Your application is approved!*\n\nPress '🟢 I'm online' to start!"
    },
    "rejected": {
        "ru": "😔 Ваша заявка была отклонена. Обратитесь к поддержке.",
        "et": "😔 Teie taotlus lükati tagasi. Võtke ühendust toega.",
        "en": "😔 Your application was rejected. Please contact support."
    },
    "balance": {
        "ru": "💰 Ваш баланс: *{bal}€*\n\nПри наличной оплате списывается 1€ за поездку.\nПополните баланс чтобы продолжить работу.",
        "et": "💰 Teie saldo: *{bal}€*\n\nSularaha maksmisel arvestatakse 1€ sõidu kohta.\nTäiendage saldot töö jätkamiseks.",
        "en": "💰 Your balance: *{bal}€*\n\n1€ is deducted per cash trip.\nTop up your balance to continue working."
    },
    "low_balance": {
        "ru": "⚠️ Ваш баланс низкий: *{bal}€*. Пополните счёт!",
        "et": "⚠️ Teie saldo on madal: *{bal}€*. Täiendage kontot!",
        "en": "⚠️ Your balance is low: *{bal}€*. Please top up!"
    },
    "no_balance": {
        "ru": "❌ Недостаточно средств на балансе. Пополните счёт чтобы получать заказы.",
        "et": "❌ Kontol pole piisavalt vahendeid. Täiendage kontot tellimuste saamiseks.",
        "en": "❌ Insufficient balance. Top up to receive orders."
    },
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
    kb.row(
        types.InlineKeyboardButton(t("now", uid), callback_data="time_now"),
        types.InlineKeyboardButton(t("in15", uid), callback_data="time_15"),
        types.InlineKeyboardButton(t("in30", uid), callback_data="time_30")
    )
    return kb

def price_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("8€ — Mustamäe", callback_data="price_8"),
        types.InlineKeyboardButton("10€ — " + ("Город" if get_lang(uid)=="ru" else "Linn" if get_lang(uid)=="et" else "City"), callback_data="price_10")
    )
    kb.row(
        types.InlineKeyboardButton("15€ — " + ("Далеко" if get_lang(uid)=="ru" else "Kaugele" if get_lang(uid)=="et" else "Far"), callback_data="price_15"),
        types.InlineKeyboardButton("20€ — " + ("Аэропорт" if get_lang(uid)=="ru" else "Lennujaam" if get_lang(uid)=="et" else "Airport"), callback_data="price_20")
    )
    return kb

def payment_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton(t("card", uid), callback_data="pay_card"),
        types.InlineKeyboardButton(t("cash", uid), callback_data="pay_cash")
    )
    return kb

def driver_order_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_{order_id}"),
        types.InlineKeyboardButton("❌ Отказать", callback_data=f"decline_{order_id}")
    )
    return kb

def driver_active_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📍 Я прибыл!", callback_data=f"arrived_{order_id}"))
    kb.row(types.InlineKeyboardButton("✅ Поездка завершена", callback_data=f"done_{order_id}"))
    return kb

def approve_driver_kb(driver_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{driver_id}"),
        types.InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{driver_id}")
    )
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
    bot.edit_message_text(t("welcome", uid), call.message.chat.id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=role_kb(uid))

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
    pending_drivers[uid] = {
        "id": uid, "full_name": state.get("full_name"),
        "car": state.get("car"), "phone": state.get("phone"),
        "username": msg.from_user.username or "—",
        "lang": get_lang(uid), "registered": now_str()
    }
    bot.send_message(uid, t("pending", uid))
    try:
        bot.send_message(ADMIN_ID,
            f"🔔 *Новая заявка водителя!*\n\n"
            f"👤 Имя: {state['full_name']}\n"
            f"🚗 Машина: {state['car']}\n"
            f"📱 Телефон: {state['phone']}\n"
            f"💬 Telegram: @{pending_drivers[uid]['username']}\n"
            f"🌍 Язык: {get_lang(uid)}\n"
            f"🕐 Время: {now_str()}",
            parse_mode="Markdown", reply_markup=approve_driver_kb(uid))
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
        drivers[driver_id] = {
            "approved": True, "online": False,
            "full_name": pending["full_name"], "car": pending["car"],
            "phone": pending["phone"], "lang": pending.get("lang", "ru"),
            "earnings": 0, "trips": 0, "balance": 10.0
        }
        del pending_drivers[driver_id]
        bot.edit_message_text(f"✅ Водитель *{pending['full_name']}* одобрен!",
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        user_state[driver_id] = {"role": "driver", "lang": pending.get("lang", "ru")}
        bot.send_message(driver_id, t("approved", driver_id), parse_mode="Markdown",
                         reply_markup=main_menu_driver(driver_id))
    elif action == "reject":
        lang = pending.get("lang", "ru")
        del pending_drivers[driver_id]
        bot.edit_message_text(f"❌ Водитель *{pending['full_name']}* отклонён.",
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.send_message(driver_id, t("rejected", driver_id))

# ── ЗАКАЗ ТАКСИ ──
@bot.message_handler(func=lambda m: m.text in [t("order_taxi", m.from_user.id), "🚖 Заказать такси", "🚖 Telli takso", "🚖 Order taxi"])
def order_start(msg):
    uid = msg.from_user.id
    user_state[uid]["step"] = "from"
    bot.send_message(uid, t("ask_from", uid), reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "from")
def order_from(msg):
    uid = msg.from_user.id
    user_state[uid]["from"] = msg.text
    user_state[uid]["step"] = "to"
    bot.send_message(uid, t("ask_to", uid))

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "to")
def order_to(msg):
    uid = msg.from_user.id
    user_state[uid]["to"] = msg.text
    user_state[uid]["step"] = "time"
    bot.send_message(uid, t("ask_time", uid), reply_markup=time_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("time_"))
def cb_time(call):
    uid = call.from_user.id
    t_val = call.data.split("_")[1]
    times = {"now": t("now", uid), "15": t("in15", uid), "30": t("in30", uid)}
    user_state[uid]["time"] = times.get(t_val, t("now", uid))
    user_state[uid]["step"] = "price"
    bot.edit_message_text(t("ask_price", uid), call.message.chat.id, call.message.message_id,
                          reply_markup=price_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("price_"))
def cb_price(call):
    uid = call.from_user.id
    price = int(call.data.split("_")[1])
    user_state[uid]["price"] = price
    user_state[uid]["step"] = "payment"
    bot.edit_message_text(t("ask_payment", uid), call.message.chat.id, call.message.message_id,
                          reply_markup=payment_kb(uid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def cb_payment(call):
    uid = call.from_user.id
    pay = t("card", uid) if call.data == "pay_card" else t("cash", uid)
    pay_type = "card" if call.data == "pay_card" else "cash"
    state = user_state.get(uid, {})
    price = state.get("price", 8)
    driver_gets = price - 1
    oid = new_order_id()
    orders[oid] = {
        "id": oid, "client_id": uid, "client_name": call.from_user.first_name,
        "from": state.get("from", "—"), "to": state.get("to", "—"),
        "time": state.get("time", "—"), "payment": pay, "pay_type": pay_type,
        "price": price, "driver_gets": driver_gets,
        "status": "pending", "created": now_str(), "driver_id": None,
        "client_lang": get_lang(uid)
    }
    user_state[uid]["current_order"] = oid
    user_state[uid]["step"] = None
    bot.edit_message_text(
        f"✅ *{oid}*\n\n"
        f"📍 {orders[oid]['from']}\n"
        f"🏁 {orders[oid]['to']}\n"
        f"⏰ {orders[oid]['time']}\n"
        f"💳 {pay}\n"
        f"💰 *{price}€*\n\n⏳",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=cancel_kb(uid))
    bot.send_message(uid, t("waiting", uid), reply_markup=main_menu_client(uid))
    notify_drivers(oid)

def notify_drivers(oid):
    order = orders[oid]
    text = (f"🔔 *Новый заказ #{oid}*\n\n"
            f"👤 {order['client_name']}\n"
            f"📍 {order['from']}\n🏁 {order['to']}\n"
            f"⏰ {order['time']}\n💳 {order['payment']}\n"
            f"💰 Ваш заработок: *{order['driver_gets']}€*\n"
            f"🕐 {order['created']}")
    sent = 0
    for driver_id, d in drivers.items():
        if d.get("online") and d.get("approved"):
            if d.get("balance", 0) <= 0:
                bot.send_message(driver_id, t("no_balance", driver_id))
                continue
            try:
                bot.send_message(driver_id, text, parse_mode="Markdown", reply_markup=driver_order_kb(oid))
                sent += 1
            except Exception as e:
                print(f"Ошибка: {e}")
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
        order["status"] = "accepted"
        order["driver_id"] = driver_id
        order["driver_name"] = drivers[driver_id]["full_name"]
        drivers[driver_id]["trips"] += 1
        drivers[driver_id]["earnings"] += order["driver_gets"]
        if order.get("pay_type") == "cash":
            drivers[driver_id]["balance"] = round(drivers[driver_id].get("balance", 0) - 1, 2)
            if drivers[driver_id]["balance"] <= 3:
                bot.send_message(driver_id, t("low_balance", driver_id, bal=drivers[driver_id]["balance"]), parse_mode="Markdown")
        bot.edit_message_text(
            f"✅ *Заказ #{oid}*\n\n"
            f"👤 {order['client_name']}\n"
            f"📍 {order['from']}\n🏁 {order['to']}\n"
            f"💳 {order['payment']}\n"
            f"💰 {order['driver_gets']}€\n\n📍 Нажмите когда прибудете!",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=driver_active_kb(oid))
        client_id = order["client_id"]
        bot.send_message(client_id,
            t("driver_found", client_id,
              name=drivers[driver_id]["full_name"],
              car=drivers[driver_id]["car"]),
            parse_mode="Markdown")
    elif action == "decline":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Отклонён")

# ── Я ПРИБЫЛ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("arrived_"))
def cb_arrived(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if not order: return
    order["status"] = "arrived"
    bot.answer_callback_query(call.id, "✅")
    client_id = order["client_id"]
    bot.send_message(client_id,
        t("arrived", client_id, name=order["driver_name"]),
        parse_mode="Markdown")

# ── ЗАВЕРШЕНО ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if not order: return
    order["status"] = "done"
    bot.edit_message_text(
        f"✅ *#{oid} завершён!*\n\n💰 {order['driver_gets']}€\nСпасибо! 🚖",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    client_id = order["client_id"]
    bot.send_message(client_id, t("trip_done", client_id),
                     parse_mode="Markdown", reply_markup=main_menu_client(client_id))

# ── СТАТУС ВОДИТЕЛЯ ──
@bot.message_handler(func=lambda m: m.text in ["🟢 Я онлайн", "🟢 Olen online", "🟢 I'm online"])
def driver_online(msg):
    uid = msg.from_user.id
    if not is_approved_driver(uid): return
    drivers[uid]["online"] = True
    bot.send_message(uid, t("online", uid), reply_markup=main_menu_driver(uid))

@bot.message_handler(func=lambda m: m.text in ["⚫ Я офлайн", "⚫ Olen offline", "⚫ I'm offline"])
def driver_offline(msg):
    uid = msg.from_user.id
    if not is_approved_driver(uid): return
    drivers[uid]["online"] = False
    bot.send_message(uid, t("offline", uid), reply_markup=main_menu_driver(uid))

# ── ЗАРАБОТОК ──
@bot.message_handler(func=lambda m: m.text in ["📊 Заработок сегодня", "📊 Täna teenitud", "📊 Today's earnings"])
def driver_earnings(msg):
    uid = msg.from_user.id
    if not is_approved_driver(uid): return
    d = drivers[uid]
    bot.send_message(uid,
        t("balance", uid, bal=d.get("balance", 0)) + f"\n\n"
        f"🚖 Поездок: {d['trips']}\n"
        f"💰 Заработано: {d['earnings']}€\n"
        f"📦 Сбор TL: {d['trips']}€",
        parse_mode="Markdown", reply_markup=main_menu_driver(uid))

# ── АДМИН ПАНЕЛЬ ──
@bot.message_handler(func=lambda m: m.text == "👥 Водители онлайн" and is_admin(m.from_user.id))
def admin_drivers(msg):
    online = [(uid, d) for uid, d in drivers.items() if d.get("online") and d.get("approved")]
    if not online:
        bot.send_message(msg.chat.id, "😔 Нет водителей онлайн", reply_markup=main_menu_admin())
        return
    text = f"🟢 *Онлайн: {len(online)}*\n\n"
    for uid, d in online:
        text += f"👤 {d['full_name']}\n🚗 {d['car']}\n📱 {d['phone']}\n💰 Баланс: {d.get('balance',0)}€\n\n"
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
    revenue = sum(1 for o in orders.values() if o['status'] == 'done')
    all_drv = len(drivers)
    online = len([d for d in drivers.values() if d.get("online")])
    pending = len(pending_drivers)
    bot.send_message(msg.chat.id,
        f"📊 *Статистика TL.TAKSO*\n\n"
        f"🚖 Всего заказов: {total}\n✅ Завершено: {done}\n"
        f"💰 Сбор TL: {revenue}€\n\n"
        f"👥 Водителей: {all_drv}\n🟢 Онлайн: {online}\n⏳ Ждут: {pending}",
        parse_mode="Markdown", reply_markup=main_menu_admin())

@bot.message_handler(func=lambda m: m.text == "🚫 Заблокировать" and is_admin(m.from_user.id))
def admin_block(msg):
    if not drivers:
        bot.send_message(msg.chat.id, "Водителей нет", reply_markup=main_menu_admin())
        return
    kb = types.InlineKeyboardMarkup()
    for uid, d in drivers.items():
        if d.get("approved"):
            kb.add(types.InlineKeyboardButton(f"🚫 {d['full_name']} · {d['car']}", callback_data=f"block_{uid}"))
    bot.send_message(msg.chat.id, "Выберите водителя:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("block_"))
def cb_block(call):
    if not is_admin(call.from_user.id): return
    driver_id = int(call.data.split("_")[1])
    if driver_id in drivers:
        name = drivers[driver_id]['full_name']
        drivers[driver_id]['approved'] = False
        drivers[driver_id]['online'] = False
        bot.edit_message_text(f"🚫 *{name}* заблокирован.",
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        try:
            bot.send_message(driver_id, "⛔ Ваш аккаунт заблокирован.")
        except: pass

# ── ЧАТ ──
IGNORE = ["🚖 Заказать такси","🚖 Telli takso","🚖 Order taxi",
          "📋 Мои поездки","📋 Minu sõidud","📋 My trips",
          "💬 Поддержка","💬 Tugi","💬 Support",
          "🟢 Я онлайн","🟢 Olen online","🟢 I'm online",
          "⚫ Я офлайн","⚫ Olen offline","⚫ I'm offline",
          "📊 Заработок сегодня","📊 Täna teenitud","📊 Today's earnings",
          "👥 Водители онлайн","📋 Все заказы","📊 Статистика","🚫 Заблокировать"]

@bot.message_handler(func=lambda m: (
    user_state.get(m.from_user.id, {}).get("role") in ["client","driver"]
    and user_state.get(m.from_user.id, {}).get("step") not in ["from","to","name","car","phone"]
    and m.text and not m.text.startswith("/")
    and m.text not in IGNORE
))
def relay_message(msg):
    uid = msg.from_user.id
    role = user_state.get(uid, {}).get("role")
    if role == "client":
        oid = user_state[uid].get("current_order")
        if oid and oid in orders:
            driver_id = orders[oid].get("driver_id")
            if driver_id:
                bot.send_message(driver_id, f"💬 *{msg.from_user.first_name}:*\n{msg.text}", parse_mode="Markdown")
                bot.send_message(uid, "✉️")
            else:
                bot.send_message(uid, "⏳")
        else:
            bot.send_message(uid, "🚖", reply_markup=main_menu_client(uid))
    elif role == "driver":
        for oid, order in orders.items():
            if order.get("driver_id") == uid and order.get("status") in ["accepted","arrived"]:
                bot.send_message(order["client_id"], f"💬 *{msg.from_user.first_name}:*\n{msg.text}", parse_mode="Markdown")
                bot.send_message(uid, "✉️")
                return
        bot.send_message(uid, "—", reply_markup=main_menu_driver(uid))

# ── ОТМЕНА ──
@bot.callback_query_handler(func=lambda c: c.data == "cancel_order")
def cb_cancel(call):
    uid = call.from_user.id
    oid = user_state.get(uid, {}).get("current_order")
    if oid and oid in orders:
        orders[oid]["status"] = "cancelled"
        bot.edit_message_text("❌", call.message.chat.id, call.message.message_id)
    bot.send_message(uid, "❌", reply_markup=main_menu_client(uid))

# ── ПОДДЕРЖКА ──
@bot.message_handler(func=lambda m: m.text in ["💬 Поддержка","💬 Tugi","💬 Support"])
def support(msg):
    bot.send_message(msg.chat.id, "📞 TL.TAKSO support: @tltakso_support")

# ── ЗАПУСК ──
if __name__ == "__main__":
    print("🚖 TL.TAKSO Bot запущен!")
    bot.infinity_polling()
