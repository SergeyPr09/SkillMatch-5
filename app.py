import os
import subprocess
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running"

@app.route('/health')
def health():
    return "OK"

def start_bot():
    # Запускаем bot.py как ОТДЕЛЬНЫЙ процесс
    subprocess.Popen(["python", "bot.py"])

if __name__ == "__main__":
    start_bot()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
