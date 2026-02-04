from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

# Generar clave privada ECDSA
private_key = ec.generate_private_key(ec.SECP256R1())

# Obtener clave pública
public_key = private_key.public_key()

# 1. Clave pública en Base64 URL-safe (para VAPID_PUBLIC_KEY)
public_key_raw = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)
public_key_b64 = base64.urlsafe_b64encode(public_key_raw).decode('utf-8').rstrip('=')

# 2. Clave privada en PEM (para VAPID_PRIVATE_KEY)
private_key_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
).decode('utf-8')

print("\n" + "="*60)
print("🔑 CLAVES VAPID CORRECTAS PARA pywebpush")
print("="*60)
print(f"\nVAPID_PUBLIC_KEY = {public_key_b64}")
print(f"\nVAPID_PRIVATE_KEY = {private_key_pem.strip()}")
print(f"\nVAPID_SUBJECT = mailto:danielpaezrami@gmail.com")
print("\n" + "="*60)
print("\n⚠️ NOTA: La clave PRIVADA debe tener el formato PEM completo")
print("   (con -----BEGIN PRIVATE KEY----- y -----END PRIVATE KEY-----)")
print("="*60)