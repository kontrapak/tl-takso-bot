from flask import Flask, send_from_directory
import os

app = Flask(__name__)

# Главная страница (клиент)
@app.route('/')
def home():
    return send_from_directory(os.path.dirname(__file__), 'index.html')

# Страница водителя
@app.route('/driver.html')
def driver():
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), 'driver.html')

# Статические файлы
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), filename)

# API: получить заказы
@app.route('/api/orders', methods=['GET'])
def get_orders():
    return []

# API: создать заказ
@app.route('/api/orders', methods=['POST'])
def create_order():
    return {'success': True, 'orderId': 1}

# API: принять заказ
@app.route('/api/orders/<int:order_id>/accept', methods=['PUT'])
def accept_order(order_id):
    return {'success': True}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
