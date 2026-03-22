from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Directorio Wabot - Servicio funcionando correctamente"

@app.route('/health')
def health():
    return {"status": "ok", "service": "directorio"}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)