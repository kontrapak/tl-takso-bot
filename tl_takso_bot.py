import telebot
from telebot import types
import datetime
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# ── ХРАНИЛИЩЕ ──
orders = {}
user_state = {}
drivers = {}
order_counter = [1]

def new_order_id():
    oid = f"TL{order_counter[0]:04d}"
    order_counter[0] += 1
    return oid

def now_str():
    return datetime.datetime.now().strftime("%H:%M")

# ── КЛАВИАТУРЫ ──
def main_menu_client():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🚖 Заказать такси")
    kb.row("📋 Мои поездки", "💬 Поддержка")
    return kb

def main_menu_driver():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🟢 Я онлайн", "⚫ Я офлайн")
    kb.row("📊 Заработок сегодня", "💬 Поддержка")
    return kb

def payment_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("💳 Карта", callback_data="pay_card"),
        types.InlineKeyboardButton("💵 Наличные", callback_data="pay_cash")
    )
    return kb

def time_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⚡ Сейчас", callback_data="time_now"),
        types.InlineKeyboardButton("⏱ +15 мин", callback_data="time_15"),
        types.InlineKeyboardButton("⏱ +30 мин", callback_data="time_30")
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
    """Кнопки для водителя после принятия заказа"""
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📍 Я прибыл!", callback_data=f"arrived_{order_id}"))
    kb.row(types.InlineKeyboardButton("✅ Поездка завершена", callback_data=f"done_{order_id}"))
    return kb

def cancel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отменить заказ", callback_data="cancel_order"))
    return kb

# ── /start ──
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🚖 Я клиент", callback_data="role_client"),
        types.InlineKeyboardButton("🧑‍✈️ Я водитель", callback_data="role_driver")
    )
    bot.send_message(
        msg.chat.id,
        "🚖 *TL.TAKSO*\n\n"
        "Такси по Таллинну\n"
        "• Фиксированная цена *10€* по городу\n"
        "• Сбор сервиса всего *1€* (Bolt берёт 25%!)\n\n"
        "Кто вы?",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ── ВЫБОР РОЛИ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("role_"))
def cb_role(call):
    uid = call.from_user.id
    role = call.data.split("_")[1]
    if role == "client":
        user_state[uid] = {"role": "client"}
        bot.edit_message_text("👋 Добро пожаловать!\n\nНажмите кнопку ниже чтобы заказать такси.",
                              call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "Выберите действие:", reply_markup=main_menu_client())
    elif role == "driver":
        drivers[uid] = {"online": False, "name": call.from_user.first_name, "earnings": 0, "trips": 0}
        user_state[uid] = {"role": "driver"}
        bot.edit_message_text(f"👋 Привет, {call.from_user.first_name}!\n\nВы зарегистрированы как водитель TL.TAKSO.",
                              call.message.chat.id, call.message.message_id)
        bot.send_message(uid, "Панель водителя:", reply_markup=main_menu_driver())

# ── КЛИЕНТ: ЗАКАЗ ──
@bot.message_handler(func=lambda m: m.text == "🚖 Заказать такси")
def order_start(msg):
    uid = msg.from_user.id
    user_state[uid] = {"role": "client", "step": "from"}
    bot.send_message(uid, "📍 Откуда едем?\n\nВведите адрес:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "from")
def order_from(msg):
    uid = msg.from_user.id
    user_state[uid]["from"] = msg.text
    user_state[uid]["step"] = "to"
    bot.send_message(uid, "🏁 Куда едем?\n\nВведите адрес назначения:")

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "to")
def order_to(msg):
    uid = msg.from_user.id
    user_state[uid]["to"] = msg.text
    user_state[uid]["step"] = "time"
    bot.send_message(uid, "⏰ Когда нужна машина?", reply_markup=time_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("time_"))
def cb_time(call):
    uid = call.from_user.id
    t = call.data.split("_")[1]
    times = {"now": "⚡ Сейчас", "15": "⏱ Через 15 минут", "30": "⏱ Через 30 минут"}
    user_state[uid]["time"] = times.get(t, "Сейчас")
    user_state[uid]["step"] = "payment"
    bot.edit_message_text("💳 Способ оплаты?", call.message.chat.id, call.message.message_id,
                          reply_markup=payment_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def cb_payment(call):
    uid = call.from_user.id
    pay = "💳 Карта" if call.data == "pay_card" else "💵 Наличные"
    state = user_state.get(uid, {})
    oid = new_order_id()
    orders[oid] = {
        "id": oid,
        "client_id": uid,
        "client_name": call.from_user.first_name,
        "from": state.get("from", "—"),
        "to": state.get("to", "—"),
        "time": state.get("time", "Сейчас"),
        "payment": pay,
        "status": "pending",
        "created": now_str(),
        "driver_id": None
    }
    user_state[uid] = {"role": "client", "current_order": oid}
    bot.edit_message_text(
        f"✅ *Заказ #{oid} принят!*\n\n"
        f"📍 Откуда: {orders[oid]['from']}\n"
        f"🏁 Куда: {orders[oid]['to']}\n"
        f"⏰ Время: {orders[oid]['time']}\n"
        f"💳 Оплата: {pay}\n"
        f"💰 Стоимость: *11€* (10€ + 1€ сбор)\n\n"
        f"⏳ Ищем водителя...",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=cancel_kb()
    )
    bot.send_message(uid, "Ожидайте, водитель скоро примет заказ 🚖", reply_markup=main_menu_client())
    notify_drivers(oid)

def notify_drivers(oid):
    order = orders[oid]
    text = (
        f"🔔 *Новый заказ #{oid}*\n\n"
        f"👤 Клиент: {order['client_name']}\n"
        f"📍 Откуда: {order['from']}\n"
        f"🏁 Куда: {order['to']}\n"
        f"⏰ Время: {order['time']}\n"
        f"💳 Оплата: {order['payment']}\n"
        f"💰 Ваш заработок: *10€*\n"
        f"🕐 {order['created']}"
    )
    sent = 0
    for driver_id, d in drivers.items():
        if d.get("online"):
            try:
                bot.send_message(driver_id, text, parse_mode="Markdown", reply_markup=driver_order_kb(oid))
                sent += 1
            except Exception as e:
                print(f"Ошибка отправки водителю {driver_id}: {e}")
    if sent == 0:
        bot.send_message(order["client_id"],
                         "😔 Сейчас нет свободных водителей. Попробуйте через несколько минут.")

# ── ВОДИТЕЛЬ: ПРИНЯТЬ / ОТКАЗАТЬ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("accept_") or c.data.startswith("decline_"))
def cb_driver_response(call):
    driver_id = call.from_user.id
    action, oid = call.data.split("_", 1)
    order = orders.get(oid)
    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден")
        return
    if order["status"] != "pending":
        bot.answer_callback_query(call.id, "Заказ уже принят другим водителем")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return
    if action == "accept":
        order["status"] = "accepted"
        order["driver_id"] = driver_id
        order["driver_name"] = call.from_user.first_name
        if driver_id not in drivers:
            drivers[driver_id] = {"online": True, "name": call.from_user.first_name, "earnings": 0, "trips": 0}
        drivers[driver_id]["trips"] += 1
        drivers[driver_id]["earnings"] += 10
        # Сообщение водителю с кнопками
        bot.edit_message_text(
            f"✅ *Вы приняли заказ #{oid}*\n\n"
            f"👤 Клиент: {order['client_name']}\n"
            f"📍 Забрать: {order['from']}\n"
            f"🏁 Везти: {order['to']}\n"
            f"💳 Оплата: {order['payment']}\n"
            f"💰 Ваш заработок: 10€\n\n"
            f"Нажмите кнопку когда прибудете! 👇",
            call.message.chat.id, call.message.message_id,
            parse_mode="Markdown",
            reply_markup=driver_active_kb(oid)
        )
        # Уведомление клиенту
        bot.send_message(
            order["client_id"],
            f"🚖 *Водитель найден!*\n\n"
            f"👤 Водитель: {order['driver_name']}\n"
            f"⏱ Едет к вам...\n\n"
            f"Заказ #{oid}",
            parse_mode="Markdown"
        )
    elif action == "decline":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Заказ отклонён")

# ── ВОДИТЕЛЬ: Я ПРИБЫЛ ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("arrived_"))
def cb_arrived(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if not order:
        return
    order["status"] = "arrived"
    bot.answer_callback_query(call.id, "✅ Клиент уведомлён!")
    # Уведомить клиента
    bot.send_message(
        order["client_id"],
        f"📍 *Водитель прибыл!*\n\n"
        f"🚖 {order['driver_name']} ждёт вас.\n"
        f"Выходите! 😊",
        parse_mode="Markdown"
    )

# ── ВОДИТЕЛЬ: ПОЕЗДКА ЗАВЕРШЕНА ──
@bot.callback_query_handler(func=lambda c: c.data.startswith("done_"))
def cb_done(call):
    oid = call.data.split("_", 1)[1]
    order = orders.get(oid)
    if not order:
        return
    order["status"] = "done"
    bot.edit_message_text(
        f"✅ *Поездка #{oid} завершена!*\n\n"
        f"💰 Заработок: 10€\n"
        f"Спасибо за работу! 🚖",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown"
    )
    bot.send_message(
        order["client_id"],
        f"🏁 *Поездка завершена!*\n\n"
        f"Спасибо что выбрали TL.TAKSO!\n"
        f"Стоимость: 11€",
        parse_mode="Markdown",
        reply_markup=main_menu_client()
    )

# ── ЧАТ МЕЖДУ КЛИЕНТОМ И ВОДИТЕЛЕМ ──
@bot.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("role") in ["client", "driver"]
                     and user_state.get(m.from_user.id, {}).get("step") not in ["from", "to"]
                     and m.text and not m.text.startswith("/")
                     and m.text not in ["🚖 Заказать такси", "📋 Мои поездки", "💬 Поддержка",
                                        "🟢 Я онлайн", "⚫ Я офлайн", "📊 Заработок сегодня"])
def relay_message(msg):
    uid = msg.from_user.id
    state = user_state.get(uid, {})
    role = state.get("role")

    if role == "client":
        # Найти заказ клиента и отправить водителю
        oid = state.get("current_order")
        if oid and oid in orders:
            order = orders[oid]
            driver_id = order.get("driver_id")
            if driver_id:
                bot.send_message(driver_id,
                                 f"💬 *Клиент {msg.from_user.first_name}:*\n{msg.text}",
                                 parse_mode="Markdown")
                bot.send_message(uid, "✉️ Сообщение отправлено водителю")
            else:
                bot.send_message(uid, "⏳ Водитель ещё не принял заказ")
        else:
            bot.send_message(uid, "У вас нет активного заказа. Сначала закажите такси 🚖",
                             reply_markup=main_menu_client())

    elif role == "driver":
        # Найти активный заказ водителя и отправить клиенту
        active_order = None
        for oid, order in orders.items():
            if order.get("driver_id") == uid and order.get("status") in ["accepted", "arrived"]:
                active_order = order
                break
        if active_order:
            bot.send_message(active_order["client_id"],
                             f"💬 *Водитель {msg.from_user.first_name}:*\n{msg.text}",
                             parse_mode="Markdown")
            bot.send_message(uid, "✉️ Сообщение отправлено клиенту")
        else:
            bot.send_message(uid, "У вас нет активного заказа", reply_markup=main_menu_driver())

# ── СТАТУС ВОДИТЕЛЯ ──
@bot.message_handler(func=lambda m: m.text in ["🟢 Я онлайн", "⚫ Я офлайн"])
def driver_status(msg):
    uid = msg.from_user.id
    if uid not in drivers:
        drivers[uid] = {"online": False, "name": msg.from_user.first_name, "earnings": 0, "trips": 0}
    online = msg.text == "🟢 Я онлайн"
    drivers[uid]["online"] = online
    status = "🟢 Вы онлайн — заказы будут приходить вам" if online else "⚫ Вы офлайн — заказы не поступают"
    bot.send_message(uid, status, reply_markup=main_menu_driver())

# ── ЗАРАБОТОК ──
@bot.message_handler(func=lambda m: m.text == "📊 Заработок сегодня")
def driver_earnings(msg):
    uid = msg.from_user.id
    d = drivers.get(uid, {"earnings": 0, "trips": 0})
    commission = d["trips"] * 1
    bot.send_message(
        uid,
        f"📊 *Ваш заработок сегодня*\n\n"
        f"🚖 Поездок: {d['trips']}\n"
        f"💰 Заработано: {d['earnings']}€\n"
        f"📦 Сбор TL.TAKSO: {commission}€\n\n"
        f"_(Bolt взял бы {round(d['earnings'] * 0.25)}€ комиссии)_",
        parse_mode="Markdown",
        reply_markup=main_menu_driver()
    )

# ── ОТМЕНА ──
@bot.callback_query_handler(func=lambda c: c.data == "cancel_order")
def cb_cancel(call):
    uid = call.from_user.id
    state = user_state.get(uid, {})
    oid = state.get("current_order")
    if oid and oid in orders:
        orders[oid]["status"] = "cancelled"
        bot.edit_message_text("❌ Заказ отменён.", call.message.chat.id, call.message.message_id)
    bot.send_message(uid, "Заказ отменён.", reply_markup=main_menu_client())

# ── ПОДДЕРЖКА ──
@bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
def support(msg):
    bot.send_message(msg.chat.id, "📞 Поддержка TL.TAKSO\n\nПишите: @tltakso_support")

# ── ЗАПУСК ──
if __name__ == "__main__":
    print("🚖 TL.TAKSO Bot запущен!")
    bot.infinity_polling()
