import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE = os.path.join(DATA_DIR, 'database.sqlite')
SECRET_KEY = 'replace-with-a-real-secret-key'  # Используется Flask и WTForms
WTF_CSRF_ENABLED = True
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'images', 'dishes')
