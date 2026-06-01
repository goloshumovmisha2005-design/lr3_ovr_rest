# routers.py
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from models import *
from forms import *
from config import DATA_DIR, UPLOAD_FOLDER
import os, json, io, time, shutil
from datetime import datetime, date
from functools import wraps

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.config.from_object('config')
@app.context_processor
def inject_csrf():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf, csrf_token_value=generate_csrf())
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Обеспечиваем существование папки для загрузок
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите.'
login_manager.login_message_category = 'error'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('Недостаточно прав', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.before_request
def make_user_available():
    g.user = current_user if current_user.is_authenticated else None

# Главная
@app.route('/')
def index():
    return render_template('index.html')

# Меню
@app.route('/menu')
def menu():
    cat_id = request.args.get('cat')
    with get_db() as conn:
        categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
        if cat_id:
            items = conn.execute("SELECT * FROM menu_items WHERE category_id=? AND available=1 ORDER BY id", (cat_id,)).fetchall()
        else:
            items = conn.execute("SELECT * FROM menu_items WHERE available=1 ORDER BY category_id, id").fetchall()
    return render_template('menu.html', categories=categories, items=items, selected_cat=cat_id)

# Детали блюда и отзывы
@app.route('/dish/<int:item_id>', methods=['GET', 'POST'])
def dish_detail(item_id):
    with get_db() as conn:
        item = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            return "Блюдо не найдено", 404
        reviews = conn.execute('''
            SELECT r.*, u.first_name FROM reviews r
            JOIN users u ON r.user_id = u.id
            WHERE r.menu_item_id=?
            ORDER BY r.created_at DESC
        ''', (item_id,)).fetchall()
        category = conn.execute("SELECT * FROM categories WHERE id=?", (item['category_id'],)).fetchone()
    form = ReviewForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('Войдите, чтобы оставить отзыв', 'error')
            return redirect(url_for('login'))
        with get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (user_id, menu_item_id, rating, text) VALUES (?,?,?,?)",
                (current_user.id, item_id, int(form.rating.data), form.text.data.strip()))
        flash('Отзыв добавлен!', 'success')
        return redirect(url_for('dish_detail', item_id=item_id))
    return render_template('dish_detail.html', item=item, reviews=reviews, category=category, form=form)

# Бронирование
@app.route('/reservation', methods=['GET', 'POST'])
@login_required
def reservation():
    form = ReservationFilterForm()
    show_map = False
    if request.method == 'GET':
        form.date.data = date.today().isoformat()
        form.start_hour.data = '18'
        form.end_hour.data = '20'
        form.guests.data = 2
    if form.validate_on_submit():
        show_map = True
    if request.method == 'POST' and request.form.get('table_id'):
        # Обработка бронирования
        table_id = int(request.form['table_id'])
        d = form.date.data
        start = f"{form.start_hour.data}:{form.start_min.data}"
        end = f"{form.end_hour.data}:{form.end_min.data}"
        guests = form.guests.data
        with get_db() as conn:
            conflict = conn.execute('''
                SELECT id FROM reservations
                WHERE table_id=? AND date=? AND status='active'
                AND NOT (end_time <= ? OR start_time >= ?)
            ''', (table_id, d, start, end)).fetchone()
            if conflict:
                flash('Этот стол уже занят', 'error')
                return render_template('reservation.html', form=form, show_map=True)
            table = conn.execute("SELECT * FROM tables WHERE id=? AND active=1", (table_id,)).fetchone()
            if not table or table['capacity'] < guests:
                flash('Стол недоступен или недостаточно мест', 'error')
                return render_template('reservation.html', form=form, show_map=True)
            conn.execute(
                "INSERT INTO reservations (user_id, table_id, date, start_time, end_time, guests) VALUES (?,?,?,?,?,?)",
                (current_user.id, table_id, d, start, end, guests))
            conn.execute("UPDATE users SET bonus_points = bonus_points + 10 WHERE id=?", (current_user.id,))
        flash('Столик забронирован!', 'success')
        return redirect(url_for('profile'))
    return render_template('reservation.html', form=form, show_map=show_map)

# API для схемы зала
@app.route('/api/tables')
def api_tables():
    date_val = request.args.get('date')
    start_time = request.args.get('start')
    end_time = request.args.get('end')
    guests = int(request.args.get('guests', 2))
    if not date_val or not start_time or not end_time:
        return jsonify([])
    with get_db() as conn:
        tables = conn.execute("SELECT * FROM tables WHERE active=1 ORDER BY capacity, id").fetchall()
        occupied_ids = set()
        for t in tables:
            conflict = conn.execute('''
                SELECT id FROM reservations
                WHERE table_id = ? AND date = ? AND status = 'active'
                AND NOT (end_time <= ? OR start_time >= ?)
            ''', (t['id'], date_val, start_time, end_time)).fetchone()
            if conflict:
                occupied_ids.add(t['id'])
        result = []
        for t in tables:
            result.append({
                'id': t['id'],
                'capacity': t['capacity'],
                'location': t['location'] or '',
                'free': t['id'] not in occupied_ids,
                'suitable': t['capacity'] >= guests,
                'pos_x': t['pos_x'],
                'pos_y': t['pos_y'],
                'width': t['width'],
                'height': t['height'],
                'shape': t['shape']
            })
    return jsonify(result)

# Корзина
@app.route('/cart')
@login_required
def cart():
    cart_cookie = request.cookies.get('cart', '{}')
    try:
        cart = json.loads(cart_cookie)
    except:
        cart = {}
    items = []
    total = 0
    if cart:
        with get_db() as conn:
            ids = list(cart.keys())
            placeholders = ','.join('?' for _ in ids)
            rows = conn.execute(f"SELECT * FROM menu_items WHERE id IN ({placeholders}) AND available=1", ids).fetchall()
            for row in rows:
                item_id_str = str(row['id'])
                qty = cart.get(item_id_str, 0)
                if qty <= 0:
                    continue
                subtotal = row['price'] * qty
                total += subtotal
                items.append({'item': row, 'quantity': qty, 'subtotal': subtotal})
    return render_template('cart.html', items=items, total=total, cart_empty=len(items)==0)

@app.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    item_id = request.form.get('item_id')
    quantity = int(request.form.get('quantity', 1))
    cart_cookie = request.cookies.get('cart', '{}')
    try:
        cart = json.loads(cart_cookie)
    except:
        cart = {}
    if quantity <= 0:
        cart.pop(item_id, None)
        flash('Блюдо удалено из корзины', 'info')
    else:
        cart[item_id] = cart.get(item_id, 0) + quantity
        flash('Блюдо добавлено в корзину', 'success')
    resp = redirect(request.referrer or url_for('menu'))
    resp.set_cookie('cart', json.dumps(cart))
    return resp

@app.route('/cart/set', methods=['POST'])
@login_required
def set_cart_quantity():
    """Точно устанавливает количество товара в корзине (для формы в cart.html)"""
    item_id = request.form.get('item_id')
    quantity = int(request.form.get('quantity', 1))
    cart_cookie = request.cookies.get('cart', '{}')
    try:
        cart = json.loads(cart_cookie)
    except:
        cart = {}
    if quantity <= 0:
        cart.pop(item_id, None)
    else:
        cart[item_id] = quantity
    resp = redirect(url_for('cart'))
    resp.set_cookie('cart', json.dumps(cart))
    flash('Количество обновлено', 'success')
    return resp

@app.route('/cart/remove/<item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart_cookie = request.cookies.get('cart', '{}')
    try:
        cart = json.loads(cart_cookie)
    except:
        cart = {}
    cart.pop(item_id, None)
    resp = redirect(url_for('cart'))
    resp.set_cookie('cart', json.dumps(cart))
    return resp

# Оформление заказа
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_cookie = request.cookies.get('cart', '{}')
    try:
        cart = json.loads(cart_cookie)
    except:
        cart = {}
    if not cart:
        flash('Корзина пуста', 'error')
        return redirect(url_for('cart'))
    with get_db() as conn:
        ids = list(cart.keys())
        placeholders = ','.join('?' for _ in ids)
        menu_items = conn.execute(f"SELECT * FROM menu_items WHERE id IN ({placeholders}) AND available=1", ids).fetchall()
        total = sum(item['price'] * cart.get(str(item['id']), 0) for item in menu_items)
        addresses = conn.execute("SELECT * FROM delivery_addresses WHERE user_id=?", (current_user.id,)).fetchall()
        payment_methods = conn.execute("SELECT * FROM payment_methods WHERE user_id=?", (current_user.id,)).fetchall()
        allergens = conn.execute("SELECT * FROM user_allergens WHERE user_id=?", (current_user.id,)).fetchall()
    form = CheckoutForm()
    form.address_id.choices = [(a['id'], a['address']) for a in addresses]
    if form.validate_on_submit():
        bonus_used = form.bonus_used.data
        if bonus_used > current_user.bonus_points:
            flash('Недостаточно бонусов', 'error')
            return render_template('checkout.html', form=form, total=total, addresses=addresses, payment_methods=payment_methods, cart=cart, menu_names={}, prices={}, allergens=allergens)
        with get_db() as conn:
            address = ''
            if form.order_type.data == 'delivery' and form.address_id.data:
                addr_row = conn.execute("SELECT address FROM delivery_addresses WHERE id=?", (form.address_id.data,)).fetchone()
                if addr_row:
                    address = addr_row['address']
            cur = conn.execute(
                "INSERT INTO orders (user_id, order_type, address, status, total_price, bonus_used, payment_method) VALUES (?,?,?,?,?,?,?)",
                (current_user.id, form.order_type.data, address, 'paid', total, bonus_used, form.payment_method.data))
            order_id = cur.lastrowid
            for item_id, qty in cart.items():
                item_row = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
                conn.execute("INSERT INTO order_items (order_id, menu_item_id, quantity, price) VALUES (?,?,?,?)",
                             (order_id, item_id, qty, item_row['price']))
            if bonus_used > 0:
                conn.execute("UPDATE users SET bonus_points = bonus_points - ? WHERE id=?", (bonus_used, current_user.id))
        resp = redirect(url_for('order_detail', order_id=order_id))
        resp.set_cookie('cart', '{}')
        flash('Заказ оформлен!', 'success')
        return resp
    menu_names = {str(item['id']): item['name'] for item in menu_items}
    prices = {str(item['id']): item['price'] for item in menu_items}
    return render_template('checkout.html', form=form, total=total, addresses=addresses, payment_methods=payment_methods, cart=cart, menu_names=menu_names, prices=prices, allergens=allergens)

# Профиль и подмаршруты
@app.route('/profile')
@login_required
def profile():
    with get_db() as conn:
        orders = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (current_user.id,)).fetchall()
        reservations = conn.execute(
            "SELECT r.*, t.capacity, t.location FROM reservations r JOIN tables t ON r.table_id=t.id WHERE r.user_id=? ORDER BY date DESC",
            (current_user.id,)).fetchall()
        my_reviews = conn.execute('''
            SELECT r.*, mi.name FROM reviews r JOIN menu_items mi ON r.menu_item_id = mi.id
            WHERE r.user_id=? ORDER BY r.created_at DESC
        ''', (current_user.id,)).fetchall()
        addresses = conn.execute("SELECT * FROM delivery_addresses WHERE user_id=?", (current_user.id,)).fetchall()
        payments = conn.execute("SELECT * FROM payment_methods WHERE user_id=?", (current_user.id,)).fetchall()
        allergens = conn.execute("SELECT * FROM user_allergens WHERE user_id=?", (current_user.id,)).fetchall()
    return render_template('profile.html', user=current_user, orders=orders, reservations=reservations,
                           my_reviews=my_reviews, addresses=addresses, payments=payments, allergens=allergens)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email
    if form.validate_on_submit():
        with get_db() as conn:
            if form.new_password.data:
                if not form.password.data or not check_password_hash(current_user.password_hash, form.password.data):
                    flash('Неверный текущий пароль', 'error')
                    return render_template('edit_profile.html', form=form)
                conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(form.new_password.data), current_user.id))
            conn.execute("UPDATE users SET first_name=?, last_name=?, email=? WHERE id=?",
                         (form.first_name.data, form.last_name.data, form.email.data, current_user.id))
        flash('Профиль обновлён', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', form=form)

@app.route('/profile/address/add', methods=['POST'])
@login_required
def add_address():
    form = AddressForm()
    if form.validate_on_submit():
        with get_db() as conn:
            conn.execute("INSERT INTO delivery_addresses (user_id, address) VALUES (?,?)", (current_user.id, form.address.data))
        flash('Адрес добавлен', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/address/<int:addr_id>/delete', methods=['POST'])
@login_required
def delete_address(addr_id):
    with get_db() as conn:
        conn.execute("DELETE FROM delivery_addresses WHERE id=? AND user_id=?", (addr_id, current_user.id))
    flash('Адрес удалён', 'info')
    return redirect(url_for('profile'))

@app.route('/profile/payment/add', methods=['POST'])
@login_required
def add_payment():
    form = PaymentForm()
    if form.validate_on_submit():
        with get_db() as conn:
            conn.execute("INSERT INTO payment_methods (user_id, card_number) VALUES (?,?)", (current_user.id, form.card_number.data))
        flash('Карта добавлена', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/payment/<int:pay_id>/delete', methods=['POST'])
@login_required
def delete_payment(pay_id):
    with get_db() as conn:
        conn.execute("DELETE FROM payment_methods WHERE id=? AND user_id=?", (pay_id, current_user.id))
    flash('Карта удалена', 'info')
    return redirect(url_for('profile'))

@app.route('/profile/allergen/add', methods=['POST'])
@login_required
def add_allergen():
    form = AllergenForm()
    if form.validate_on_submit():
        with get_db() as conn:
            conn.execute("INSERT INTO user_allergens (user_id, allergen) VALUES (?,?)", (current_user.id, form.allergen.data))
        flash('Аллерген добавлен', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/allergen/<int:allergen_id>/delete', methods=['POST'])
@login_required
def delete_allergen(allergen_id):
    with get_db() as conn:
        conn.execute("DELETE FROM user_allergens WHERE id=? AND user_id=?", (allergen_id, current_user.id))
    flash('Аллерген удалён', 'info')
    return redirect(url_for('profile'))

# Деталь заказа пользователя
@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, current_user.id)).fetchone()
        if not order:
            return "Заказ не найден", 404
        items = conn.execute('''
            SELECT oi.*, mi.name, mi.image FROM order_items oi JOIN menu_items mi ON oi.menu_item_id=mi.id
            WHERE oi.order_id=?
        ''', (order_id,)).fetchall()
    return render_template('order_detail.html', order=order, items=items)

@app.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    with get_db() as conn:
        conn.execute("UPDATE orders SET status='cancelled' WHERE id=? AND user_id=?", (order_id, current_user.id))
    flash('Заказ отменён', 'info')
    return redirect(url_for('profile'))

@app.route('/reservation/<int:res_id>/cancel', methods=['POST'])
@login_required
def cancel_reservation(res_id):
    with get_db() as conn:
        conn.execute("UPDATE reservations SET status='cancelled' WHERE id=? AND user_id=?", (res_id, current_user.id))
    flash('Бронь отменена', 'info')
    return redirect(url_for('profile'))

# Аутентификация
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        phone = form.phone.data.strip()
        password = form.password.data.strip()
        with get_db() as conn:
            row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            if row and check_password_hash(row['password_hash'], password):
                user = User(row)
                login_user(user)
                flash('Вы вошли', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
        flash('Неверный телефон или пароль', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (first_name, last_name, phone, email, password_hash) VALUES (?,?,?,?,?)",
                    (form.first_name.data, form.last_name.data, form.phone.data,
                     form.email.data, generate_password_hash(form.password.data)))
            flash('Регистрация прошла успешно! Войдите.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Пользователь с таким телефоном уже существует', 'error')
    return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        phone = form.phone.data.strip()
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            if not user:
                flash('Пользователь не найден', 'error')
                return render_template('forgot_password.html', form=form)
            return render_template('forgot_password.html', phone=phone, show_reset=True, reset_form=ResetPasswordForm())
    return render_template('forgot_password.html', form=form)

@app.route('/reset-password', methods=['POST'])
def reset_password():
    form = ResetPasswordForm()
    phone = request.form.get('phone', '').strip()
    if form.validate_on_submit():
        with get_db() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE phone=?", (generate_password_hash(form.new_password.data), phone))
        flash('Пароль изменён! Войдите.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html', phone=phone, show_reset=True, reset_form=form)

# Админка
@app.route('/admin')
@login_required
def admin_redirect():
    if current_user.role in ('admin', 'manager', 'hostess'):
        return redirect(url_for('admin_dashboard'))
    flash('Доступ запрещён', 'error')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@role_required('admin', 'manager', 'hostess')
def admin_dashboard():
    with get_db() as conn:
        stats = {
            'users': conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt'],
            'orders': conn.execute("SELECT COUNT(*) as cnt FROM orders").fetchone()['cnt'],
            'reservations': conn.execute("SELECT COUNT(*) as cnt FROM reservations WHERE status='active'").fetchone()['cnt'],
            'menu_items': conn.execute("SELECT COUNT(*) as cnt FROM menu_items").fetchone()['cnt'],
        }
    return render_template('admin_dashboard.html', stats=stats)

# Экспорт БД (SQLite файл) – было
@app.route('/admin/export-database')
@role_required('admin')
def export_database():
    db_path = app.config['DATABASE']
    return send_file(db_path, as_attachment=True, download_name='myasko_backup.sqlite')

# Экспорт данных в JSON
@app.route('/admin/export-json')
@role_required('admin')
def export_json():
    data = {}
    with get_db() as conn:
        tables = ['users','categories','menu_items','tables','reservations','orders','order_items','reviews','payment_methods','delivery_addresses','user_allergens']
        for t in tables:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            data[t] = [dict(row) for row in rows]
    mem = io.BytesIO()
    mem.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name='myasko_data.json', mimetype='application/json')

# Импорт SQLite дампа (замена базы данных)
@app.route('/admin/import-sqlite', methods=['POST'])
@role_required('admin')
def import_sqlite():
    file = request.files.get('dbfile')
    if not file or not file.filename.endswith('.sqlite'):
        flash('Нужен файл .sqlite', 'error')
        return redirect(url_for('import_data'))
    # Создаём резервную копию текущей БД
    backup_name = DATABASE + '.backup_' + str(int(time.time()))
    shutil.copy(DATABASE, backup_name)
    file.save(DATABASE)
    flash('База данных заменена (старая сохранена как backup)', 'success')
    return redirect(url_for('admin_dashboard'))

# Пользователи
@app.route('/admin/users')
@role_required('admin')
def admin_users():
    with get_db() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    form = AdminAddUserForm()
    return render_template('admin_users.html', users=users, form=form)

@app.route('/admin/users/add', methods=['POST'])
@role_required('admin')
def admin_add_user():
    form = AdminAddUserForm()
    if form.validate_on_submit():
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (first_name, last_name, phone, email, password_hash, role) VALUES (?,?,?,?,?,?)",
                    (form.first_name.data, form.last_name.data, form.phone.data,
                     form.email.data, generate_password_hash(form.password.data), form.role.data))
            flash('Пользователь добавлен', 'success')
        except sqlite3.IntegrityError:
            flash('Телефон уже существует', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_user(user_id):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return "Пользователь не найден", 404
    form = AdminEditUserForm()
    if request.method == 'GET':
        form.first_name.data = user['first_name']
        form.last_name.data = user['last_name']
        form.email.data = user['email'] or ''
        form.role.data = user['role']
    if form.validate_on_submit():
        with get_db() as conn:
            if form.new_password.data:
                conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(form.new_password.data), user_id))
            conn.execute("UPDATE users SET first_name=?, last_name=?, email=?, role=? WHERE id=?",
                         (form.first_name.data, form.last_name.data, form.email.data, form.role.data, user_id))
        flash('Пользователь обновлён', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_edit_user.html', form=form, user=user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_user(user_id):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id=? AND role!='admin'", (user_id,))
    flash('Пользователь удалён', 'info')
    return redirect(url_for('admin_users'))

# Управление меню
@app.route('/admin/menu')
@role_required('admin', 'manager')
def admin_menu():
    with get_db() as conn:
        items = conn.execute("SELECT m.*, c.name as cat_name FROM menu_items m LEFT JOIN categories c ON m.category_id=c.id ORDER BY m.category_id, m.id").fetchall()
        categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    add_form = AdminAddMenuItemForm()
    add_form.category_id.choices = [(c['id'], c['name']) for c in categories]
    return render_template('admin_menu.html', items=items, categories=categories, add_form=add_form)

@app.route('/admin/menu/add', methods=['POST'])
@role_required('admin', 'manager')
def admin_add_menu():
    with get_db() as conn:
        categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    form = AdminAddMenuItemForm()
    form.category_id.choices = [(c['id'], c['name']) for c in categories]
    if form.validate_on_submit():
        image_path = form.image_url.data.strip()
        if not image_path and form.image_file.data:
            file = form.image_file.data
            filename = f"dish_{int(datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f"images/dishes/{filename}"
        with get_db() as conn:
            conn.execute(
                "INSERT INTO menu_items (name, price, category_id, description, available, image) VALUES (?,?,?,?,?,?)",
                (form.name.data, form.price.data, form.category_id.data, form.description.data, int(form.available.data), image_path))
        flash('Блюдо добавлено', 'success')
    return redirect(url_for('admin_menu'))

@app.route('/admin/menu/<int:item_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'manager')
def admin_edit_menu(item_id):
    with get_db() as conn:
        item = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            return "Блюдо не найдено", 404
        categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    form = AdminEditMenuItemForm()
    form.category_id.choices = [(c['id'], c['name']) for c in categories]
    if request.method == 'GET':
        form.name.data = item['name']
        form.price.data = item['price']
        form.category_id.data = item['category_id']
        form.description.data = item['description']
        form.available.data = bool(item['available'])
    if form.validate_on_submit():
        image_path = item['image']
        if form.image_url.data.strip():
            image_path = form.image_url.data.strip()
            if item['image'] and not item['image'].startswith('http'):
                old_path = os.path.join(app.static_folder, item['image'])
                if os.path.exists(old_path): os.remove(old_path)
        elif form.image_file.data:
            file = form.image_file.data
            filename = f"dish_{int(datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f"images/dishes/{filename}"
            if item['image'] and not item['image'].startswith('http'):
                old_path = os.path.join(app.static_folder, item['image'])
                if os.path.exists(old_path): os.remove(old_path)
        with get_db() as conn:
            conn.execute(
                "UPDATE menu_items SET name=?, price=?, category_id=?, description=?, available=?, image=? WHERE id=?",
                (form.name.data, form.price.data, form.category_id.data, form.description.data, int(form.available.data), image_path, item_id))
        flash('Блюдо обновлено', 'success')
        return redirect(url_for('admin_menu'))
    return render_template('admin_edit_menu.html', form=form, item=item)

@app.route('/admin/menu/<int:item_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_menu(item_id):
    with get_db() as conn:
        conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    flash('Блюдо удалено', 'info')
    return redirect(url_for('admin_menu'))

@app.route('/admin/menu/<int:item_id>/toggle', methods=['POST'])
@role_required('admin', 'manager')
def admin_toggle_menu(item_id):
    with get_db() as conn:
        item = conn.execute("SELECT available FROM menu_items WHERE id=?", (item_id,)).fetchone()
        if not item: return "Не найдено", 404
        new = 0 if item['available'] == 1 else 1
        conn.execute("UPDATE menu_items SET available=? WHERE id=?", (new, item_id))
    flash('Доступность изменена', 'success')
    return redirect(url_for('admin_menu'))

# Заказы
@app.route('/admin/orders')
@role_required('admin', 'manager')
def admin_orders():
    with get_db() as conn:
        orders = conn.execute('''
            SELECT o.*, u.first_name, u.last_name
            FROM orders o JOIN users u ON o.user_id=u.id
            ORDER BY o.created_at DESC
        ''').fetchall()
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/orders/<int:order_id>', methods=['GET', 'POST'])
@role_required('admin', 'manager')
def admin_order_detail(order_id):
    status_form = AdminChangeStatusForm()
    items_form = AdminEditOrderItemsForm()
    with get_db() as conn:
        order = conn.execute("SELECT o.*, u.first_name, u.last_name FROM orders o JOIN users u ON o.user_id=u.id WHERE o.id=?", (order_id,)).fetchone()
        if not order:
            return "Заказ не найден", 404
        items = conn.execute('''
            SELECT oi.*, mi.name, mi.image FROM order_items oi JOIN menu_items mi ON oi.menu_item_id=mi.id
            WHERE oi.order_id=?
        ''', (order_id,)).fetchall()
        menu_all = conn.execute("SELECT id, name, price FROM menu_items WHERE available=1 ORDER BY name").fetchall()
        items_form.menu_item_id.choices = [(m['id'], f"{m['name']} ({m['price']} ₽)") for m in menu_all]
    if status_form.validate_on_submit():
        new_status = status_form.status.data
        if new_status in ('created','paid','in_progress','completed','cancelled'):
            with get_db() as conn:
                conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
            flash('Статус обновлён', 'success')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    if items_form.validate_on_submit():
        action = items_form.action.data
        with get_db() as conn:
            order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if order and order['status'] in ('completed','cancelled'):
                flash('Нельзя менять завершённый заказ', 'error')
                return redirect(url_for('admin_order_detail', order_id=order_id))
            if action == 'add' and items_form.menu_item_id.data and items_form.quantity.data:
                menu_item = conn.execute("SELECT price FROM menu_items WHERE id=?", (items_form.menu_item_id.data,)).fetchone()
                if menu_item:
                    conn.execute("INSERT INTO order_items (order_id, menu_item_id, quantity, price) VALUES (?,?,?,?)",
                                 (order_id, items_form.menu_item_id.data, items_form.quantity.data, menu_item['price']))
                    flash('Добавлено', 'success')
            elif action == 'remove' and items_form.remove_item_id.data:
                conn.execute("DELETE FROM order_items WHERE id=? AND order_id=?", (items_form.remove_item_id.data, order_id))
                flash('Удалено', 'info')
            elif action == 'update' and items_form.update_item_id.data:
                new_qty = items_form.new_quantity.data
                if new_qty > 0:
                    conn.execute("UPDATE order_items SET quantity=? WHERE id=? AND order_id=?", (new_qty, items_form.update_item_id.data, order_id))
                else:
                    conn.execute("DELETE FROM order_items WHERE id=? AND order_id=?", (items_form.update_item_id.data, order_id))
                flash('Количество обновлено', 'success')
            total = conn.execute("SELECT SUM(price*quantity) FROM order_items WHERE order_id=?", (order_id,)).fetchone()[0] or 0
            conn.execute("UPDATE orders SET total_price=? WHERE id=?", (total, order_id))
        return redirect(url_for('admin_order_detail', order_id=order_id))
    return render_template('admin_order_detail.html', order=order, items=items, menu_all=menu_all,
                           status_form=status_form, items_form=items_form)

# Брони
@app.route('/admin/reservations', methods=['GET', 'POST'])
@role_required('admin', 'hostess')
def admin_reservations():
    add_form = AdminAddReservationForm()
    with get_db() as conn:
        reservations = conn.execute('''
            SELECT r.*, u.first_name, u.last_name, t.capacity, t.location
            FROM reservations r JOIN users u ON r.user_id=u.id JOIN tables t ON r.table_id=t.id
            ORDER BY r.date DESC
        ''').fetchall()
        tables = conn.execute("SELECT * FROM tables WHERE active=1 ORDER BY capacity").fetchall()
        users = conn.execute("SELECT id, first_name, last_name, phone FROM users ORDER BY last_name").fetchall()
    add_form.user_id.choices = [(u['id'], f"{u['first_name']} {u['last_name']} ({u['phone']})") for u in users]
    add_form.table_id.choices = [(t['id'], f"Стол {t['id']} ({t['capacity']} мест)") for t in tables]
    if add_form.validate_on_submit():
        with get_db() as conn:
            conflict = conn.execute('''
                SELECT id FROM reservations
                WHERE table_id=? AND date=? AND status='active'
                AND NOT (end_time <= ? OR start_time >= ?)
            ''', (add_form.table_id.data, add_form.date.data, add_form.start_time.data, add_form.end_time.data)).fetchone()
            if conflict:
                flash('Конфликт по времени', 'error')
            else:
                conn.execute(
                    "INSERT INTO reservations (user_id, table_id, date, start_time, end_time, guests) VALUES (?,?,?,?,?,?)",
                    (add_form.user_id.data, add_form.table_id.data, add_form.date.data, add_form.start_time.data, add_form.end_time.data, add_form.guests.data))
                flash('Бронь добавлена', 'success')
        return redirect(url_for('admin_reservations'))
    return render_template('admin_reservations.html', reservations=reservations, tables=tables, users=users, add_form=add_form)

@app.route('/admin/reservations/<int:res_id>/cancel', methods=['POST'])
@role_required('admin', 'hostess')
def admin_cancel_reservation(res_id):
    with get_db() as conn:
        conn.execute("UPDATE reservations SET status='cancelled' WHERE id=?", (res_id,))
    flash('Бронь отменена', 'info')
    return redirect(url_for('admin_reservations'))

# Столы и конструктор зала
@app.route('/admin/tables')
@role_required('admin', 'manager')
def admin_tables():
    with get_db() as conn:
        tables = conn.execute("SELECT * FROM tables ORDER BY id").fetchall()
    add_form = AdminAddTableForm()
    return render_template('admin_tables.html', tables=tables, add_form=add_form)

@app.route('/reservation/<int:res_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_reservation(res_id):
    with get_db() as conn:
        res = conn.execute("SELECT * FROM reservations WHERE id=? AND user_id=?",
                           (res_id, current_user.id)).fetchone()
        if not res or res['status'] != 'active':
            flash('Бронь не найдена или уже не активна', 'error')
            return redirect(url_for('profile'))
        table = conn.execute("SELECT * FROM tables WHERE id=?", (res['table_id'],)).fetchone()
    form = EditReservationForm()
    if request.method == 'GET':
        form.date.data = res['date']
        form.start_time.data = res['start_time']
        form.end_time.data = res['end_time']
        form.guests.data = res['guests']
    if form.validate_on_submit():
        new_date = form.date.data
        new_start = form.start_time.data
        new_end = form.end_time.data
        new_guests = form.guests.data
        # Проверка вместимости стола
        if new_guests > table['capacity']:
            flash(f'Стол вмещает не более {table["capacity"]} человек', 'error')
            return render_template('edit_reservation.html', form=form, reservation=res)
        # Проверка конфликтов, исключая текущую бронь
        with get_db() as conn:
            conflict = conn.execute('''
                SELECT id FROM reservations
                WHERE table_id=? AND date=? AND status='active'
                AND id != ?
                AND NOT (end_time <= ? OR start_time >= ?)
            ''', (res['table_id'], new_date, res_id, new_start, new_end)).fetchone()
            if conflict:
                flash('На это время стол уже занят', 'error')
                return render_template('edit_reservation.html', form=form, reservation=res)
            conn.execute('''
                UPDATE reservations SET date=?, start_time=?, end_time=?, guests=?
                WHERE id=?
            ''', (new_date, new_start, new_end, new_guests, res_id))
        flash('Бронь обновлена', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_reservation.html', form=form, reservation=res)

@app.route('/admin/tables/add', methods=['POST'])
@role_required('admin')
def admin_add_table():
    form = AdminAddTableForm()
    if form.validate_on_submit():
        with get_db() as conn:
            conn.execute("INSERT INTO tables (capacity, location, active) VALUES (?,?,1)", (form.capacity.data, form.location.data))
        flash('Стол добавлен', 'success')
    return redirect(url_for('admin_tables'))

@app.route('/admin/tables/<int:table_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_table(table_id):
    with get_db() as conn:
        table = conn.execute("SELECT * FROM tables WHERE id=?", (table_id,)).fetchone()
        if not table:
            return "Стол не найден", 404
    form = AdminEditTableForm()
    if request.method == 'GET':
        form.capacity.data = table['capacity']
        form.location.data = table['location']
        form.active.data = bool(table['active'])
    if form.validate_on_submit():
        with get_db() as conn:
            conn.execute("UPDATE tables SET capacity=?, location=?, active=? WHERE id=?",
                         (form.capacity.data, form.location.data, int(form.active.data), table_id))
        flash('Стол обновлён', 'success')
        return redirect(url_for('admin_tables'))
    return render_template('admin_edit_table.html', form=form, table=table)

@app.route('/admin/tables/<int:table_id>/toggle', methods=['POST'])
@role_required('admin', 'manager')
def admin_toggle_table(table_id):
    with get_db() as conn:
        table = conn.execute("SELECT active FROM tables WHERE id=?", (table_id,)).fetchone()
        if table:
            new = 0 if table['active'] == 1 else 1
            conn.execute("UPDATE tables SET active=? WHERE id=?", (new, table_id))
        flash('Доступность стола изменена', 'success')
    return redirect(url_for('admin_tables'))

@app.route('/admin/tables/<int:table_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_table(table_id):
    with get_db() as conn:
        conn.execute("DELETE FROM tables WHERE id=?", (table_id,))
    flash('Стол удалён', 'info')
    return redirect(url_for('admin_tables'))

@app.route('/admin/floor-plan')
@role_required('admin')
def admin_floor_plan():
    with get_db() as conn:
        tables = conn.execute("SELECT * FROM tables ORDER BY id").fetchall()
    return render_template('admin_floor_plan.html', tables=tables)

@app.route('/admin/tables/<int:table_id>/position', methods=['POST'])
@role_required('admin')
def admin_update_table_position(table_id):
    data = request.get_json()
    x = data.get('x', 0)
    y = data.get('y', 0)
    w = data.get('w', 100)
    h = data.get('h', 100)
    shape = data.get('shape', 'rectangle')
    with get_db() as conn:
        conn.execute("UPDATE tables SET pos_x=?, pos_y=?, width=?, height=?, shape=? WHERE id=?", (x, y, w, h, shape, table_id))
    return jsonify(success=True)

# База данных (админ)
@app.route('/admin/database')
@role_required('admin')
def admin_database():
    with get_db() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return render_template('admin_database.html', tables=[t['name'] for t in tables])

@app.route('/admin/database/table/<table_name>')
@role_required('admin')
def admin_view_table(table_name):
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    with get_db() as conn:
        # Безопасная проверка: получаем список допустимых таблиц
        allowed_tables = [t['name'] for t in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        if table_name not in allowed_tables:
            flash('Таблица не найдена', 'error')
            return redirect(url_for('admin_database'))
        columns = [col[1] for col in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
        rows = conn.execute(f"SELECT * FROM {table_name} LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    return render_template('admin_table_view.html', table_name=table_name, columns=columns, rows=rows,
                           page=page, total=total, per_page=per_page)

# Импорт данных (JSON)
@app.route('/import', methods=['GET', 'POST'])
@role_required('admin')
def import_data():
    form = AdminImportForm()
    if form.validate_on_submit():
        file = form.datafile.data
        try:
            data = json.load(file)
        except Exception as e:
            flash(f'Ошибка чтения JSON: {e}', 'error')
            return redirect(url_for('import_data'))
        with get_db() as conn:
            if form.import_menu.data:
                for item in data.get('menu_items', []):
                    cat_name = item.get('category')
                    if not cat_name: continue
                    cat_row = conn.execute("SELECT id FROM categories WHERE name=?", (cat_name,)).fetchone()
                    if not cat_row:
                        cur = conn.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
                        cat_id = cur.lastrowid
                    else:
                        cat_id = cat_row['id']
                    desc = item.get('description', '')
                    volume = item.get('volume', '')
                    if volume: desc = (desc + ' ' + volume).strip()
                    weight = item.get('weight', '')
                    if weight: desc = (desc + ' ' + weight).strip()
                    conn.execute(
                        "INSERT OR IGNORE INTO menu_items (category_id, name, description, price, image, allergens, available) VALUES (?,?,?,?,?,?,1)",
                        (cat_id, item['name'], desc, item['price'], item.get('images', ''), item.get('allergens', ''))
                    )
            if form.import_users.data:
                for user in data.get('users', []):
                    pwd = generate_password_hash(user.get('password', ''))
                    try:
                        conn.execute(
                            "INSERT INTO users (first_name, last_name, phone, email, password_hash, role, bonus_points) VALUES (?,?,?,?,?,?,?)",
                            (user['first_name'], user['last_name'], user['phone'],
                             user.get('email', ''), pwd, user.get('role', 'user'), user.get('bonus_points', 0))
                        )
                    except sqlite3.IntegrityError:
                        pass
            if form.import_tables.data:
                for t in data.get('tables', []):
                    conn.execute("INSERT INTO tables (capacity, location, active) VALUES (?,?,1)",
                                 (t['capacity'], t.get('location', '')))
        flash('Импорт завершён', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_import.html', form=form)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)