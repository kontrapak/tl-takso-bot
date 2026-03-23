<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>TL.TAKSO - Заказ такси</title>
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.5.0/mapbox-gl.js"></script>
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.5.0/mapbox-gl.css" rel="stylesheet" />
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #f5f5f5;
            height: 100vh;
            overflow: hidden;
        }
        
        /* Карта */
        #map {
            width: 100%;
            height: 45vh;
            background: #e0e0e0;
        }
        
        /* Основной контейнер */
        .container {
            position: relative;
            background: white;
            border-radius: 24px 24px 0 0;
            margin-top: -24px;
            padding: 20px;
            height: calc(55vh - 20px);
            overflow-y: auto;
            box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
        }
        
        /* Адреса */
        .address-section {
            background: #f8f8f8;
            border-radius: 16px;
            padding: 12px;
            margin-bottom: 16px;
        }
        
        .address-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: white;
            border-radius: 12px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .address-item:active {
            background: #f0f0f0;
        }
        
        .address-icon {
            font-size: 24px;
        }
        
        .address-content {
            flex: 1;
        }
        
        .address-label {
            font-size: 12px;
            color: #666;
            margin-bottom: 4px;
        }
        
        .address-text {
            font-size: 14px;
            font-weight: 500;
            color: #333;
        }
        
        /* Время */
        .time-section {
            margin-bottom: 16px;
        }
        
        .section-title {
            font-size: 14px;
            font-weight: 600;
            color: #666;
            margin-bottom: 12px;
        }
        
        .time-buttons {
            display: flex;
            gap: 12px;
        }
        
        .time-btn {
            flex: 1;
            padding: 12px;
            border: 1px solid #e0e0e0;
            background: white;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }
        
        .time-btn.active {
            background: #2196f3;
            color: white;
            border-color: #2196f3;
        }
        
        /* Оплата */
        .payment-section {
            margin-bottom: 20px;
        }
        
        .payment-buttons {
            display: flex;
            gap: 12px;
        }
        
        .payment-btn {
            flex: 1;
            padding: 12px;
            border: 1px solid #e0e0e0;
            background: white;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }
        
        .payment-btn.active {
            background: #4caf50;
            color: white;
            border-color: #4caf50;
        }
        
        /* Стоимость */
        .price-section {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 16px;
            color: white;
        }
        
        .price-main {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 12px;
        }
        
        .price-breakdown {
            font-size: 12px;
            opacity: 0.9;
            margin-bottom: 8px;
        }
        
        .price-compare {
            font-size: 12px;
            opacity: 0.8;
            padding-top: 8px;
            border-top: 1px solid rgba(255,255,255,0.3);
        }
        
        /* Кнопка заказа */
        .order-btn {
            width: 100%;
            padding: 16px;
            background: #2196f3;
            color: white;
            border: none;
            border-radius: 16px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 12px;
        }
        
        .order-btn:active {
            background: #1976d2;
            transform: scale(0.98);
        }
        
        /* Загрузка */
        .loading {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 12px 24px;
            border-radius: 24px;
            z-index: 2000;
            display: none;
        }
        
        /* Адаптация под Telegram */
        .telegram-header {
            background: var(--tg-theme-bg-color, white);
            padding: 12px;
            text-align: center;
            font-weight: bold;
            color: var(--tg-theme-text-color, black);
        }
        
        @media (max-width: 480px) {
            .container {
                padding: 16px;
            }
        }
    </style>
</head>
<body>
    <div id="map"></div>
    
    <div class="container">
        <!-- Адреса -->
        <div class="address-section">
            <div class="address-item" id="fromAddressBtn">
                <div class="address-icon">📍</div>
                <div class="address-content">
                    <div class="address-label">Откуда</div>
                    <div class="address-text" id="fromAddress">Выберите на карте</div>
                </div>
            </div>
            <div class="address-item" id="toAddressBtn">
                <div class="address-icon">🏁</div>
                <div class="address-content">
                    <div class="address-label">Куда</div>
                    <div class="address-text" id="toAddress">Выберите на карте</div>
                </div>
            </div>
        </div>
        
        <!-- Время поездки -->
        <div class="time-section">
            <div class="section-title">⏰ ВРЕМЯ ПОЕЗДКИ</div>
            <div class="time-buttons">
                <button class="time-btn" data-time="now">⚡ Сейчас</button>
                <button class="time-btn" data-time="15">⏱ +15 мин</button>
                <button class="time-btn" data-time="30">⏱ +30 мин</button>
            </div>
        </div>
        
        <!-- Оплата -->
        <div class="payment-section">
            <div class="section-title">💳 ОПЛАТА</div>
            <div class="payment-buttons">
                <button class="payment-btn" data-payment="card">💳 Карта</button>
                <button class="payment-btn" data-payment="cash">💵 Наличные</button>
            </div>
        </div>
        
        <!-- Стоимость -->
        <div class="price-section">
            <div class="price-main" id="totalPrice">11 €</div>
            <div class="price-breakdown" id="priceBreakdown">
                Тариф 10€<br>
                Сервис 1€
            </div>
            <div class="price-compare" id="priceCompare">
                ✔ Bolt взял бы 12.5€
            </div>
        </div>
        
        <!-- Кнопка заказа -->
        <button class="order-btn" id="orderBtn">🚖 ЗАКАЗАТЬ ТАКСИ</button>
    </div>
    
    <div class="loading" id="loading">Загрузка...</div>

    <script>
        // Инициализация Telegram Web App
        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.enableClosingConfirmation();
        
        // Mapbox токен
        mapboxgl.accessToken = 'pk.eyJ1IjoidGx0YWtzbyIsImEiOiJjbW4zYW0yMGkxNG13MnByM2hoZng0OXh2In0.ArR_nk-dVg99VhuuatH2hA';
        
        // Состояние
        let map;
        let fromMarker;
        let toMarker;
        let currentSelecting = 'from'; // 'from' или 'to'
        let fromPoint = null;
        let toPoint = null;
        let fromAddressText = null;
        let toAddressText = null;
        let selectedTime = 'now';
        let selectedPayment = 'card';
        
        // Тарифы
        const tariffs = {
            'mustamae': { name: 'Mustamäe', price: 8 },
            'city': { name: 'Город', price: 10 },
            'far': { name: 'Далеко', price: 15 },
            'airport': { name: 'Аэропорт', price: 20 }
        };
        
        // Функция расчета стоимости (упрощенная)
        function calculatePrice(fromLat, fromLng, toLat, toLng) {
            // Расчет расстояния по прямой (в км)
            const R = 6371;
            const dLat = (toLat - fromLat) * Math.PI / 180;
            const dLon = (toLng - fromLng) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(fromLat * Math.PI / 180) * Math.cos(toLat * Math.PI / 180) *
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            const distance = R * c;
            
            // Тариф: 2€ за км, минимум 8€
            let price = Math.max(8, Math.round(distance * 2));
            let tariffName = "Город";
            
            if (distance <= 3) {
                price = 8;
                tariffName = "Mustamäe";
            } else if (distance <= 8) {
                price = 10;
                tariffName = "Город";
            } else if (distance <= 15) {
                price = 15;
                tariffName = "Далеко";
            } else {
                price = 20;
                tariffName = "Аэропорт/пригород";
            }
            
            return { price, tariffName, distance: distance.toFixed(1) };
        }
        
        function updatePriceDisplay() {
            if (!fromPoint || !toPoint) {
                document.getElementById('totalPrice').textContent = '— €';
                document.getElementById('priceBreakdown').innerHTML = 'Выберите маршрут';
                document.getElementById('priceCompare').innerHTML = '';
                return;
            }
            
            const { price, tariffName, distance } = calculatePrice(
                fromPoint.lat, fromPoint.lng,
                toPoint.lat, toPoint.lng
            );
            
            const serviceFee = 1;
            const total = price + serviceFee;
            const boltPrice = (price + serviceFee) * 1.15; // Bolt на 15% дороже
            
            document.getElementById('totalPrice').textContent = `${total} €`;
            document.getElementById('priceBreakdown').innerHTML = 
                `Тариф ${price}€<br>Сервис ${serviceFee}€<br>📏 ${distance} км`;
            document.getElementById('priceCompare').innerHTML = 
                `✔ Bolt взял бы ${Math.round(boltPrice)}€`;
        }
        
        // Инициализация карты
        function initMap(lat = 59.4370, lng = 24.7536) {
            map = new mapboxgl.Map({
                container: 'map',
                style: 'mapbox://styles/mapbox/streets-v12',
                center: [lng, lat],
                zoom: 12
            });
            
            map.addControl(new mapboxgl.NavigationControl(), 'top-right');
            
            // Маркер отправления (зеленый)
            fromMarker = new mapboxgl.Marker({ color: '#4caf50', draggable: true })
                .setLngLat([lng, lat])
                .addTo(map);
            
            // Маркер назначения (красный)
            toMarker = new mapboxgl.Marker({ color: '#f44336', draggable: true })
                .setLngLat([lng + 0.01, lat + 0.01])
                .addTo(map);
            
            // Обработка перетаскивания
            fromMarker.on('dragend', () => {
                const lngLat = fromMarker.getLngLat();
                fromPoint = { lat: lngLat.lat, lng: lngLat.lng };
                reverseGeocode(lngLat.lat, lngLat.lng, 'from');
            });
            
            toMarker.on('dragend', () => {
                const lngLat = toMarker.getLngLat();
                toPoint = { lat: lngLat.lat, lng: lngLat.lng };
                reverseGeocode(lngLat.lat, lngLat.lng, 'to');
            });
            
            // Клик на карте
            map.on('click', (e) => {
                const { lat, lng } = e.lngLat;
                if (currentSelecting === 'from') {
                    fromMarker.setLngLat([lng, lat]);
                    fromPoint = { lat, lng };
                    reverseGeocode(lat, lng, 'from');
                } else {
                    toMarker.setLngLat([lng, lat]);
                    toPoint = { lat, lng };
                    reverseGeocode(lat, lng, 'to');
                }
            });
            
            // Получаем текущее местоположение
            getCurrentLocation();
        }
        
        async function reverseGeocode(lat, lng, type) {
            showLoading(true);
            try {
                const response = await fetch(
                    `https://api.mapbox.com/geocoding/v5/mapbox.places/${lng},${lat}.json` +
                    `?access_token=${mapboxgl.accessToken}&language=ru&limit=1`
                );
                const data = await response.json();
                if (data.features && data.features[0]) {
                    const address = data.features[0].place_name;
                    if (type === 'from') {
                        fromAddressText = address;
                        document.getElementById('fromAddress').textContent = address.length > 40 ? address.substring(0, 40) + '...' : address;
                    } else {
                        toAddressText = address;
                        document.getElementById('toAddress').textContent = address.length > 40 ? address.substring(0, 40) + '...' : address;
                    }
                    
                    if (fromPoint && toPoint) {
                        updatePriceDisplay();
                    }
                }
            } catch (error) {
                console.error('Reverse geocoding error:', error);
            } finally {
                showLoading(false);
            }
        }
        
        function getCurrentLocation() {
            if ('geolocation' in navigator) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const { latitude, longitude } = position.coords;
                        map.flyTo({ center: [longitude, latitude], zoom: 14, duration: 1000 });
                        fromMarker.setLngLat([longitude, latitude]);
                        fromPoint = { lat: latitude, lng: longitude };
                        reverseGeocode(latitude, longitude, 'from');
                    },
                    (error) => console.log('Geolocation error:', error)
                );
            }
        }
        
        // UI обработчики
        document.getElementById('fromAddressBtn').onclick = () => {
            currentSelecting = 'from';
            tg.showAlert('📍 Нажмите на карте, чтобы выбрать место отправления');
        };
        
        document.getElementById('toAddressBtn').onclick = () => {
            currentSelecting = 'to';
            tg.showAlert('🏁 Нажмите на карте, чтобы выбрать место назначения');
        };
        
        // Время
        document.querySelectorAll('.time-btn').forEach(btn => {
            btn.onclick = () => {
                document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedTime = btn.dataset.time;
            };
        });
        document.querySelector('.time-btn').classList.add('active');
        
        // Оплата
        document.querySelectorAll('.payment-btn').forEach(btn => {
            btn.onclick = () => {
                document.querySelectorAll('.payment-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedPayment = btn.dataset.payment;
            };
        });
        document.querySelector('.payment-btn').classList.add('active');
        
        // Заказ
        document.getElementById('orderBtn').onclick = () => {
            if (!fromPoint || !toPoint) {
                tg.showAlert('❌ Пожалуйста, выберите маршрут на карте');
                return;
            }
            
            const { price } = calculatePrice(fromPoint.lat, fromPoint.lng, toPoint.lat, toPoint.lng);
            
            const orderData = {
                from_lat: fromPoint.lat,
                from_lon: fromPoint.lng,
                from_address: fromAddressText,
                to_lat: toPoint.lat,
                to_lon: toPoint.lng,
                to_address: toAddressText,
                time: selectedTime,
                payment: selectedPayment,
                price: price + 1,
                driver_gets: price
            };
            
            tg.sendData(JSON.stringify(orderData));
            tg.close();
        };
        
        function showLoading(show) {
            document.getElementById('loading').style.display = show ? 'flex' : 'none';
        }
        
        // Запуск
        initMap();
        
        // Адаптация под тему Telegram
        if (tg.colorScheme === 'dark') {
            document.body.style.backgroundColor = '#1c1c1e';
            document.querySelector('.container').style.backgroundColor = '#1c1c1e';
        }
    </script>
</body>
</html>
