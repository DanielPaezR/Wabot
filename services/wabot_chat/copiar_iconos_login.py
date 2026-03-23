# copiar_iconos_login.py
import shutil
import os

# Asegurar que existe la carpeta
os.makedirs('static/icons', exist_ok=True)

# Copiar iconos existentes con nuevos nombres
iconos_a_copiar = [
    ('icon-192x192.png', 'icon-login-192.png'),
    ('icon-512x512.png', 'icon-login-512.png'),
    ('favicon.ico', 'favicon-login.ico')
]

for origen, destino in iconos_a_copiar:
    origen_path = f'static/icons/{origen}'
    destino_path = f'static/icons/{destino}'
    
    if os.path.exists(origen_path):
        shutil.copy2(origen_path, destino_path)
        print(f"✅ Copiado: {origen} → {destino}")
    else:
        print(f"⚠️ No existe: {origen_path}")

print("🎯 Listo! Ahora prueba de nuevo.")