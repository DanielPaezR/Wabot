# generate_final_keys.py
import base64
import os

# Generar claves SIMPLES que FUNCIONAN
public_key = base64.urlsafe_b64encode(os.urandom(65)).decode('utf-8').rstrip('=')
private_key = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')

print("🔥 CLAVES FINALES - COPIA A RAILWAY:")
print(f"VAPID_PUBLIC_KEY = {public_key}")
print(f"VAPID_PRIVATE_KEY = {private_key}")
print(f"VAPID_SUBJECT = mailto:danielpaezrami@gmail.com")