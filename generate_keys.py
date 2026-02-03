from pywebpush import generate_vapid_keys
import json

keys = generate_vapid_keys()
print("\n" + "="*50)
print("COPIA ESTAS CLAVES A RAILWAY:")
print("="*50)
print(f"VAPID_PUBLIC_KEY = {keys['publicKey']}")
print(f"VAPID_PRIVATE_KEY = {keys['privateKey']}")
print(f"VAPID_SUBJECT = mailto:admin@tuapp.com")
print("="*50)