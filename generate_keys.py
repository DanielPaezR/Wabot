# generate_vapid_keys_fixed.py
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

# Generar clave privada
private_key = ec.generate_private_key(ec.SECP256R1())

# Obtener clave pública en formato crudo
public_key = private_key.public_key()
public_key_raw = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

# Convertir a Base64 URL-safe sin padding
public_key_b64 = base64.urlsafe_b64encode(public_key_raw).decode('utf-8').rstrip('=')

# Convertir clave privada a Base64
private_key_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
private_key_b64 = base64.urlsafe_b64encode(private_key_pem).decode('utf-8').rstrip('=')

print("\n" + "="*60)
print("🔑 CLAVES VAPID CORRECTAS")
print("="*60)
print(f"\nVAPID_PUBLIC_KEY = {public_key_b64}")
print(f"\nVAPID_PRIVATE_KEY = {private_key_b64}")
print(f"\nVAPID_SUBJECT = mailto:tuemail@gmail.com")
print("\n" + "="*60)