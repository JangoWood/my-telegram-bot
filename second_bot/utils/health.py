from flask import Flask
import os

# Создаём Flask-приложение для healthcheck
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
@flask_app.route('/healthcheck')
def health():
    return "OK", 200

def run_flask():
    # Render задаёт порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)
