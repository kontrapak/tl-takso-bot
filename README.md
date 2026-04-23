<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>TL.TAKSO</title>

<script src="https://telegram.org/js/telegram-web-app.js"></script>

<script src="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"></script>
<link href="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css" rel="stylesheet" />

<style>
body { margin:0; }
#map { width:100%; height:100vh; }
button {
    position:absolute;
    bottom:20px;
    left:50%;
    transform:translateX(-50%);
    padding:15px 25px;
    font-size:18px;
    border:none;
    border-radius:10px;
    background:#000;
    color:#fff;
}
</style>
</head>

<body>
<div id="map"></div>
<button onclick="sendOrder()">🚖 Заказать</button>

<script>
const tg = window.Telegram.WebApp;
tg.expand();

mapboxgl.accessToken = 'ТВОЙ_TOKEN';

const map = new mapboxgl.Map({
    container: 'map',
    style: 'mapbox://styles/mapbox/streets-v12',
    center: [24.7536, 59.4370], // Таллин
    zoom: 12
});

let from = null;
let to = null;
let step = "from";

let markerFrom, markerTo;

map.on('click', function(e) {

    if (step === "from") {
        from = e.lngLat;

        if (markerFrom) markerFrom.remove();
        markerFrom = new mapboxgl.Marker({color: "green"})
            .setLngLat(from)
            .addTo(map);

        step = "to";

    } else {
        to = e.lngLat;

        if (markerTo) markerTo.remove();
        markerTo = new mapboxgl.Marker({color: "red"})
            .setLngLat(to)
            .addTo(map);
    }
});

function sendOrder() {
    if (!from || !to) {
        alert("Выберите точки");
        return;
    }

    const data = {
        from: [from.lng, from.lat],
        to: [to.lng, to.lat]
    };

    tg.sendData(JSON.stringify(data));
}
</script>

</body>
</html>
