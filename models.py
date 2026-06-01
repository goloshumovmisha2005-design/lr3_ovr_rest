import sqlite3, json, os
from datetime import datetime
from config import DATABASE, DATA_DIR
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.first_name = row['first_name']
        self.last_name = row['last_name']
        self.phone = row['phone']
        self.email = row['email']
        self.password_hash = row['password_hash']
        self.role = row['role']
        self.bonus_points = row['bonus_points']

    @staticmethod
    def get(user_id):
        with get_db() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return User(row) if row else None

def hash_password(password):
    return generate_password_hash(password)

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                bonus_points INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                image TEXT,
                allergens TEXT,
                available INTEGER DEFAULT 1,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );
            CREATE TABLE IF NOT EXISTS tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capacity INTEGER NOT NULL,
                location TEXT,
                active INTEGER DEFAULT 1,
                pos_x INTEGER DEFAULT 0,
                pos_y INTEGER DEFAULT 0,
                width INTEGER DEFAULT 100,
                height INTEGER DEFAULT 100,
                shape TEXT DEFAULT 'rectangle'
            );
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                table_id INTEGER,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                guests INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (table_id) REFERENCES tables(id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                order_type TEXT NOT NULL,
                address TEXT,
                status TEXT DEFAULT 'created',
                total_price REAL,
                bonus_used INTEGER DEFAULT 0,
                payment_method TEXT DEFAULT 'card',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                menu_item_id INTEGER,
                quantity INTEGER,
                price REAL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                menu_item_id INTEGER,
                rating INTEGER,
                text TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
            );
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_number TEXT NOT NULL,
                card_type TEXT DEFAULT 'Visa',
                is_default INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS delivery_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS user_allergens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                allergen TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        ''')
        # Добавление отсутствующих столбцов (для обратной совместимости)
        for col, col_def in [
            ('image', 'TEXT'), ('allergens', 'TEXT'), ('available', 'INTEGER DEFAULT 1'),
            ('active', 'INTEGER DEFAULT 1'), ('bonus_used', 'INTEGER DEFAULT 0'),
            ('payment_method', 'TEXT'), ('pos_x', 'INTEGER DEFAULT 0'),
            ('pos_y', 'INTEGER DEFAULT 0'), ('width', 'INTEGER DEFAULT 100'),
            ('height', 'INTEGER DEFAULT 100'), ('shape', "TEXT DEFAULT 'rectangle'")
        ]:
            try:
                conn.execute(f"ALTER TABLE menu_items ADD COLUMN {col} {col_def}")
            except: pass
        # Администратор по умолчанию
        if not conn.execute("SELECT id FROM users WHERE role='admin'").fetchone():
            pwd = generate_password_hash('admin')
            conn.execute(
                "INSERT INTO users (first_name, last_name, phone, email, password_hash, role) VALUES (?,?,?,?,?,?)",
                ('Админ', 'Админов', '+70000000000', 'admin@myasko.ru', pwd, 'admin')
            )

def import_lab1_data(filepath):
    if not os.path.exists(filepath):
        print(f"Файл {filepath} не найден")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    with get_db() as conn:
        for item in data.get('menu_items', []):
            cat_name = item.get('category')
            if not cat_name:
                continue
            cat_row = conn.execute("SELECT id FROM categories WHERE name=?", (cat_name,)).fetchone()
            if not cat_row:
                cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
                cat_id = cur.lastrowid
            else:
                cat_id = cat_row['id']
            desc = item.get('description', '')
            volume = item.get('volume', '')
            if volume:
                desc = (desc + ' ' + volume).strip()
            weight = item.get('weight', '')
            if weight:
                desc = (desc + ' ' + weight).strip()
            conn.execute(
                "INSERT OR IGNORE INTO menu_items (category_id, name, description, price, image, allergens, available) "
                "VALUES (?,?,?,?,?,?,1)",
                (cat_id, item['name'], desc, item['price'],
                 item.get('images', ''), item.get('allergens', ''))
            )
        for user in data.get('users', []):
            pwd = generate_password_hash(user.get('password', ''))
            try:
                conn.execute(
                    "INSERT INTO users (first_name, last_name, phone, email, password_hash, role, bonus_points) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (user['first_name'], user['last_name'], user['phone'],
                     user.get('email', ''), pwd, user.get('role', 'user'),
                     user.get('bonus_points', 0))
                )
            except sqlite3.IntegrityError:
                pass
        if not conn.execute("SELECT id FROM tables").fetchone():
            for t in data.get('tables', []):
                conn.execute("INSERT INTO tables (capacity, location, active) VALUES (?,?,1)",
                             (t['capacity'], t.get('location', '')))
    print("Импорт из ЛР1 выполнен.")

def auto_import():
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) as cnt FROM menu_items").fetchone()['cnt']
    if count == 0:
        import_file = os.path.join(DATA_DIR, 'lab1_export.json')
        if os.path.exists(import_file):
            import_lab1_data(import_file)

init_db()
auto_import()