# generate_keys_fixed.py - VERSIÓN DEFINITIVA
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

print("🔥 GENERANDO CLAVES VAPID VÁLIDAS - VERSIÓN CORREGIDA 🔥")
print("=" * 60)

# 1. Generar PAR de claves EC
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

print("✅ Par de claves EC generado correctamente")

# 2. Extraer los 32 bytes REALES de la clave privada
private_numbers = private_key.private_numbers()
private_value = private_numbers.private_value  # <- ¡Esto son los 32 bytes!

# Convertir a bytes (big-endian)
private_bytes = private_value.to_bytes(32, 'big')

print(f"📏 Private key REAL: {len(private_bytes)} bytes (32 correcto)")

# 3. Exportar clave PÚBLICA en formato sin comprimir
public_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

print(f"📏 Public key raw: {len(public_bytes)} bytes (65 correcto)")
print(f"🔍 Primer byte: 0x{public_bytes[0]:02x} (debe ser 0x04)")

# 4. Convertir a base64 URL-safe SIN PADDING
vapid_private = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
vapid_public = base64.urlsafe_b64encode(public_bytes[1:]).decode('utf-8').rstrip('=')  # Quitar 0x04

print("\n" + "="*60)
print("🎯 ¡ESTAS SÍ SON LAS CLAVES CORRECTAS!")
print("="*60)

print("\n1️⃣ CLAVE PRIVADA (VAPID_PRIVATE_KEY):")
print("-" * 50)
print(vapid_private)
print(f"📏 Longitud: {len(vapid_private)} caracteres (¡CORRECTO! ~43)")

print("\n2️⃣ CLAVE PÚBLICA (VAPID_PUBLIC_KEY):")
print("-" * 50)
print(vapid_public)
print(f"📏 Longitud: {len(vapid_public)} caracteres (¡CORRECTO! ~87)")

print("\n3️⃣ PARA RAILWAY (Variables de entorno):")
print("-" * 50)
print("COPIA Y PEGA EXACTAMENTE:")
print()
print(f"VAPID_PRIVATE_KEY={vapid_private}")
print(f"VAPID_PUBLIC_KEY={vapid_public}")
print("VAPID_SUBJECT=mailto:danielpaezrami@gmail.com")

print("\n4️⃣ PARA push-simple.js:")
print("-" * 50)
print(f"const publicKey = '{vapid_public}';")

print("\n5️⃣ VERIFICACIÓN RÁPIDA:")
print("-" * 50)
print(f"✅ Privada empieza con: {vapid_private[:10]}...")
print(f"✅ Pública empieza con: {vapid_public[:10]}...")
print(f"✅ Privada longitud: {len(vapid_private)} (debe ser ~43)")
print(f"✅ Pública longitud: {len(vapid_public)} (debe ser ~87)")