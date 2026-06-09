#!/usr/bin/env python3
# admin_console.py - Административная консоль (КЛИЕНТ, НЕ СЕРВЕР)

import requests
import json
import os
from datetime import datetime

API_BASE = "http://localhost:8000/api"

class AdminConsole:
    def __init__(self):
        self.session = requests.Session()
        self._auto_login()

    def _auto_login(self):
        login_data = {"phone": "+70000000000", "password": "admin"}
        try:
            resp = self.session.post(f"{API_BASE}/login", json=login_data)
            if resp.status_code == 200:
                print("Авторизация администратора выполнена.")
                return True
            else:
                print("Ошибка авторизации администратора. Убедитесь, что сервер запущен и админ существует.")
                return False
        except Exception as e:
            print(f"Не удалось подключиться к серверу: {e}")
            return False

    def _request(self, method, endpoint, json_data=None, params=None, files=None):
        url = f"{API_BASE}{endpoint}"
        try:
            if files:
                resp = self.session.request(method, url, files=files, data=json_data)
            else:
                resp = self.session.request(method, url, json=json_data, params=params)
            if resp.status_code in (200, 201):
                return resp.json() if resp.text else None
            elif resp.status_code == 204:
                return None
            else:
                error = resp.json().get('error', 'Неизвестная ошибка') if resp.text else f"HTTP {resp.status_code}"
                print(f"Ошибка {resp.status_code}: {error}")
                return None
        except requests.exceptions.ConnectionError:
            print("Ошибка подключения к серверу. Запустите WSGI-приложение.")
            return None

    def list_users(self):
        users = self._request('GET', '/admin/users')
        if users:
            print("\n--- ПОЛЬЗОВАТЕЛИ ---")
            for u in users:
                print(f"{u['id']}. {u['first_name']} {u['last_name']} | {u['phone']} | {u['role']} | бонусы: {u['bonus_points']}")
        else:
            print("Нет пользователей или ошибка")

    def add_user(self):
        print("Добавление пользователя:")
        first = input("Имя: ")
        last = input("Фамилия: ")
        phone = input("Телефон: ")
        pwd = input("Пароль: ")
        role = input("Роль (user/manager/hostess/admin): ").strip()
        if role not in ('user','manager','hostess','admin'):
            role = 'user'
        data = {"first_name": first, "last_name": last, "phone": phone, "password": pwd, "role": role}
        res = self._request('POST', '/admin/users', json_data=data)
        if res:
            print("Пользователь создан")

    def edit_user(self):
        uid = input("ID пользователя: ")
        if not uid.isdigit():
            print("Неверный ID")
            return
        users = self._request('GET', '/admin/users')
        if not users:
            return
        user = next((u for u in users if u['id'] == int(uid)), None)
        if not user:
            print("Пользователь не найден")
            return
        print(f"Редактирование: {user['first_name']} {user['last_name']}")
        first = input(f"Имя ({user['first_name']}): ").strip() or user['first_name']
        last = input(f"Фамилия ({user['last_name']}): ").strip() or user['last_name']
        role = input(f"Роль ({user['role']}): ").strip() or user['role']
        bonus = input(f"Бонусы ({user['bonus_points']}): ").strip()
        bonus = int(bonus) if bonus.isdigit() else user['bonus_points']
        new_pwd = input("Новый пароль (оставьте пустым, чтобы не менять): ").strip()
        data = {"first_name": first, "last_name": last, "role": role, "bonus_points": bonus}
        if new_pwd:
            data["password"] = new_pwd
        res = self._request('PUT', f'/admin/users/{uid}', json_data=data)
        if res:
            print("Пользователь обновлён")

    def delete_user(self):
        uid = input("ID пользователя для удаления: ")
        if not uid.isdigit():
            print("Неверный ID")
            return
        if self._request('DELETE', f'/admin/users/{uid}') is not None:
            print("Пользователь удалён")

    def list_menu(self):
        items = self._request('GET', '/menu?all=true')
        if items:
            print("\n--- МЕНЮ (все блюда) ---")
            for it in items:
                avail = "✅" if it['available'] else "❌"
                print(f"{it['id']}. {it['name']} - {it['price']} руб. {avail} (кат.{it['category_id']})")
        else:
            print("Меню пусто")

    def add_menu_item(self):
        name = input("Название: ")
        price = float(input("Цена: "))
        cat_id = int(input("ID категории (посмотрите через категории): "))
        desc = input("Описание: ")
        avail = input("Доступно (да/нет): ").lower() in ('да','yes','1')
        data = {"name": name, "price": price, "category_id": cat_id, "description": desc, "available": avail}
        res = self._request('POST', '/menu', json_data=data)
        if res:
            print(f"Блюдо добавлено, ID {res['id']}")

    def edit_menu_item(self):
        item_id = input("ID блюда: ")
        if not item_id.isdigit():
            print("Неверный ID")
            return
        item = self._request('GET', f'/menu/{item_id}')
        if not item:
            return
        print(f"Редактирование: {item['name']}")
        name = input(f"Название ({item['name']}): ").strip() or item['name']
        price = input(f"Цена ({item['price']}): ").strip()
        price = float(price) if price else item['price']
        desc = input(f"Описание ({item.get('description','')}): ").strip() or item.get('description','')
        avail = input("Доступно (да/нет, оставьте пустым): ").strip().lower()
        if avail:
            available = avail in ('да','yes','1')
        else:
            available = item['available']
        data = {"name": name, "price": price, "description": desc, "available": available, "category_id": item['category_id']}
        res = self._request('PUT', f'/menu/{item_id}', json_data=data)
        if res:
            print("Блюдо обновлено")

    def delete_menu_item(self):
        item_id = input("ID блюда для удаления: ")
        if not item_id.isdigit():
            print("Неверный ID")
            return
        if self._request('DELETE', f'/menu/{item_id}') is not None:
            print("Блюдо удалено")

    def list_orders(self):
        orders = self._request('GET', '/orders')
        if orders:
            print("\n--- ВСЕ ЗАКАЗЫ ---")
            for o in orders:
                print(f"#{o['id']} | пользователь {o.get('user_id')} | {o['status']} | {o['total_price']} руб. | {o['created_at']}")
        else:
            print("Нет заказов")

    def change_order_status(self):
        oid = input("ID заказа: ")
        if not oid.isdigit():
            print("Неверный ID")
            return
        status = input("Новый статус (created/paid/in_progress/completed/cancelled): ")
        res = self._request('PATCH', f'/orders/{oid}/status', json_data={"status": status})
        if res:
            print("Статус изменён")

    def list_reservations(self):
        reservations = self._request('GET', '/admin/reservations/all')
        if reservations:
            print("\n--- ВСЕ БРОНИ ---")
            for r in reservations:
                print(f"ID {r['id']} | {r['date']} {r['start_time']}-{r['end_time']} | стол {r['table_id']} | {r['guests']} чел. | {r['status']} | {r.get('first_name','')} {r.get('last_name','')}")
        else:
            print("Нет броней")

    def cancel_reservation(self):
        rid = input("ID брони для отмены: ")
        if not rid.isdigit():
            print("Неверный ID")
            return
        if self._request('DELETE', f'/admin/reservations/{rid}') is not None:
            print("Бронь отменена")

    def list_tables(self):
        tables = self._request('GET', '/admin/tables')
        if tables:
            print("\n--- СТОЛЫ ---")
            for t in tables:
                print(f"#{t['id']} | мест: {t['capacity']} | локация: {t.get('location','')} | активен: {'✅' if t['active'] else '❌'}")
        else:
            print("Нет столов")

    def add_table(self):
        cap = input("Вместимость: ")
        if not cap.isdigit():
            print("Неверное число")
            return
        loc = input("Расположение: ")
        data = {"capacity": int(cap), "location": loc}
        res = self._request('POST', '/admin/tables', json_data=data)
        if res:
            print(f"Стол добавлен, ID {res['id']}")

    def delete_table(self):
        tid = input("ID стола для удаления: ")
        if not tid.isdigit():
            print("Неверный ID")
            return
        if self._request('DELETE', f'/admin/tables/{tid}') is not None:
            print("Стол удалён")

    def export_json(self):
        data = self._request('GET', '/admin/export-json')
        if data:
            filename = input("Имя файла для экспорта (например, backup.json): ").strip()
            if not filename:
                filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Экспорт выполнен в {filename}")

    def import_json(self):
        filename = input("Имя JSON-файла для импорта: ").strip()
        if not os.path.exists(filename):
            print("Файл не найден")
            return
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        res = self._request('POST', '/admin/import-json', json_data=data)
        if res:
            print("Данные импортированы на сервер")

    def clear_all_data(self):
        confirm = input("Очистить ВСЕ данные (кроме администратора)? (да/нет): ").lower()
        if confirm == 'да':
            res = self._request('POST', '/admin/clear-all')
            if res:
                print("Все данные очищены")

    def download_db(self):
        url = f"{API_BASE}/admin/database-file"
        try:
            resp = self.session.get(url)
            if resp.status_code == 200:
                filename = input("Имя для сохранения (например, myasko.sqlite): ").strip()
                if not filename:
                    filename = f"database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
                with open(filename, 'wb') as f:
                    f.write(resp.content)
                print(f"База данных сохранена в {filename}")
            else:
                print(f"Ошибка {resp.status_code}")
        except Exception as e:
            print(f"Ошибка: {e}")

    def upload_db(self):
        filename = input("Путь к файлу .sqlite: ").strip()
        if not os.path.exists(filename):
            print("Файл не найден")
            return
        with open(filename, 'rb') as f:
            files = {'file': (filename, f, 'application/octet-stream')}
            url = f"{API_BASE}/admin/database-file"
            try:
                resp = self.session.post(url, files=files)
                if resp.status_code == 200:
                    print("База данных заменена на сервере")
                else:
                    print(f"Ошибка: {resp.text}")
            except Exception as e:
                print(f"Ошибка: {e}")

    def run(self):
        if not self._auto_login():
            print("Не удалось войти как администратор. Убедитесь, что сервер запущен и админ существует.")
            return

        menu = [
            ("Список пользователей", self.list_users),
            ("Добавить пользователя", self.add_user),
            ("Редактировать пользователя", self.edit_user),
            ("Удалить пользователя", self.delete_user),
            ("Показать меню", self.list_menu),
            ("Добавить блюдо", self.add_menu_item),
            ("Редактировать блюдо", self.edit_menu_item),
            ("Удалить блюдо", self.delete_menu_item),
            ("Все заказы", self.list_orders),
            ("Изменить статус заказа", self.change_order_status),
            ("Все брони", self.list_reservations),
            ("Отменить бронь", self.cancel_reservation),
            ("Список столов", self.list_tables),
            ("Добавить стол", self.add_table),
            ("Удалить стол", self.delete_table),
            ("Экспорт в JSON", self.export_json),
            ("Импорт из JSON", self.import_json),
            ("Очистить все данные", self.clear_all_data),
            ("Скачать БД (SQLite)", self.download_db),
            ("Загрузить БД на сервер", self.upload_db),
            ("Выход", None)
        ]

        while True:
            print("\n" + "="*50)
            print("   АДМИНИСТРАТИВНАЯ КОНСОЛЬ РЕСТОРАНА 'МЯСКО'")
            print("="*50)
            for idx, (name, _) in enumerate(menu, 1):
                print(f"{idx}. {name}")
            choice = input("Выберите действие: ").strip()
            if not choice.isdigit():
                print("Введите число")
                continue
            choice = int(choice)
            if 1 <= choice <= len(menu):
                name, func = menu[choice-1]
                if func is None:
                    print("До свидания!")
                    break
                func()
            else:
                print("Неверный пункт")

if __name__ == "__main__":
    console = AdminConsole()
    console.run()