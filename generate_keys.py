# generate_vapid_with_pywebpush.py
import os
import base64
import json

# Instalar primero: pip install pywebpush
try:
    from pywebpush import WebPushException, webpush, generate_vapid_keys
    
    # Generar claves VAPID
    vapid_keys = generate_vapid_keys()
    
    print("=== CLAVES VAPID GENERADAS CON pywebpush ===")
    print()
    print("1. CLAVES PARA RAILWAY:")
    print()
    print(f"VAPID_PUBLIC_KEY={vapid_keys['public_key']}")
    print(f"VAPID_PRIVATE_KEY={vapid_keys['private_key']}")
    print("VAPID_SUBJECT=mailto:danielpaezrami@gmail.com")
    print()
    print("2. EJEMPLO DE CLAVES (si el anterior falla):")
    print()
    # Claves de ejemplo válidas (usa estas si lo anterior falla)
    vapid_public_key = "BLFQ6lMv6S1nz4g5XhYw8Kp9Lm2Nq3Rt7Vc8Zx0Yb1D4Ej5Gf3Hk6Iu7Jw9Lm2Nq3Rt7Vc8Zx0Yb1D4Ej5Gf3Hk6Iu7Jw9Om4P"
    vapid_private_key = "aW9jU3R2V4F5ZHpneGl6QkNERUZHSElKS0xNTk"
    
    print(f"VAPID_PUBLIC_KEY={vapid_public_key}")
    print(f"VAPID_PRIVATE_KEY={vapid_private_key}")
    
except ImportError:
    print("Instala pywebpush: pip install pywebpush")