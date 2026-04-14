const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// ============ СТАТИКА ============
// Старые файлы в корне (работают как раньше)
app.use(express.static('.'));

// Новые красивые URLы /app/... ← ИСПРАВЛЕНО: 'static' вместо 'статический'
app.use('/app', express.static('static'));

// Редиректы со старых URL на новые
app.get('/client.html', (req, res) => {
  res.redirect('/app/index.html');
});

app.get('/driver.html', (req, res) => {
  res.redirect('/app/driver.html');
});
// =================================

// Подключение к PostgreSQL
const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.DATABASE_URL ? { rejectUnauthorized: false } : false
});

// Инициализация базы данных
const initDB = async () => {
    try {
        await pool.query(`
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                from_address TEXT NOT NULL,
                to_address TEXT NOT NULL,
                price INTEGER NOT NULL,
                from_lat FLOAT,
                from_lng FLOAT,
                to_lat FLOAT,
                to_lng FLOAT,
                status VARCHAR(20) DEFAULT 'waiting',
                driver_id VARCHAR(100),
                driver_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP
            )
        `);
        console.log('✅ База данных готова');
    } catch (error) {
        console.error('❌ Ошибка БД:', error.message);
    }
};

// API: Создать заказ
app.post('/api/orders', async (req, res) => {
    const { from, to, price, fromCoords, toCoords } = req.body;
    
    if (!from || !to || !price) {
        return res.status(400).json({ error: 'Не все поля заполнены' });
    }
    
    try {
        const result = await pool.query(
            `INSERT INTO orders (from_address, to_address, price, from_lat, from_lng, to_lat, to_lng) 
             VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id`,
            [from, to, price, fromCoords?.[1] || null, fromCoords?.[0] || null, toCoords?.[1] || null, toCoords?.[0] || null]
        );
        
        res.json({ success: true, orderId: result.rows[0].id });
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// API: Получить все заказы
app.get('/api/orders', async (req, res) => {
    try {
        const result = await pool.query(
            'SELECT * FROM orders WHERE status = $1 ORDER BY created_at DESC',
            ['waiting']
        );
        res.json(result.rows);
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// API: Получить один заказ
app.get('/api/orders/:id', async (req, res) => {
    try {
        const result = await pool.query('SELECT * FROM orders WHERE id = $1', [req.params.id]);
        res.json(result.rows[0] || null);
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// API: Принять заказ
app.put('/api/orders/:id/accept', async (req, res) => {
    const { id } = req.params;
    const { driver_id, driver_name } = req.body;
    
    try {
        const check = await pool.query('SELECT status FROM orders WHERE id = $1', [id]);
        if (check.rows[0]?.status !== 'waiting') {
            return res.status(400).json({ error: 'Заказ уже принят' });
        }
        
        await pool.query(
            `UPDATE orders SET status = 'accepted', driver_id = $1, driver_name = $2, accepted_at = NOW() WHERE id = $3`,
            [driver_id, driver_name || 'Водитель', id]
        );
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// API: Отменить заказ
app.put('/api/orders/:id/cancel', async (req, res) => {
    try {
        await pool.query('UPDATE orders SET status = $1 WHERE id = $2', ['cancelled', req.params.id]);
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// API: Статистика
app.get('/api/stats', async (req, res) => {
    try {
        const stats = await pool.query(`
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN status = 'waiting' THEN 1 ELSE 0 END) as waiting,
                SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) as accepted,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
            FROM orders
        `);
        res.json(stats.rows[0]);
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// Запуск сервера
app.listen(PORT, async () => {
    await initDB();
    console.log(`🚀 Сервер на порту ${PORT}`);
});
