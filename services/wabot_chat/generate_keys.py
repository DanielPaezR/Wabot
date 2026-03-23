# generate_webpush_keys.py - CLAVES QUE SÍ FUNCIONAN CON PUSH API
import json
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

print("🎯 GENERANDO CLAVES VAPID PARA WEB PUSH API 🎯")
print("=" * 60)

# 1. Generar par de claves EC P-256
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

print("✅ Par EC P-256 generado")

# 2. Extraer los 32 bytes REALES de la clave privada
private_numbers = private_key.private_numbers()
private_int = private_numbers.private_value
private_bytes = private_int.to_bytes(32, 'big')  # 32 bytes exactos

print(f"📏 Private bytes: {len(private_bytes)} bytes")

# 3. Obtener clave pública en formato sin comprimir (65 bytes)
public_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

print(f"📏 Public bytes: {len(public_bytes)} bytes")
print(f"🔍 Primer byte público: 0x{public_bytes[0]:02x}")

# 4. Convertir a base64 URL-safe (sin padding)
vapid_private = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
vapid_public = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')

print("\n" + "="*60)
print("🔥 ¡CLAVES LISTAS PARA WEB PUSH API! 🔥")
print("="*60)

print(f"\n1️⃣ VAPID_PRIVATE_KEY ({len(vapid_private)} chars):")
print("-" * 50)
print(vapid_private)

print(f"\n2️⃣ VAPID_PUBLIC_KEY ({len(vapid_public)} chars):")
print("-" * 50)
print(vapid_public)

print("\n3️⃣ PARA RAILWAY (Variables de entorno):")
print("-" * 50)
print("COPIA Y PEGA:")
print()
print(f"VAPID_PRIVATE_KEY={vapid_private}")
print(f"VAPID_PUBLIC_KEY={vapid_public}")
print("VAPID_SUBJECT=mailto:danielpaezrami@gmail.com")

print("\n4️⃣ PARA push-simple.js:")
print("-" * 50)
print("Reemplaza la línea con const publicKey = ...")
print()
print(f"const publicKey = '{vapid_public}';")

print("\n5️⃣ VERIFICACIÓN:")
print("-" * 50)
print("⚠️ La clave pública debe tener ~87 caracteres")
print("⚠️ La clave privada debe tener ~43 caracteres")
print(f"✅ Pública: {len(vapid_public)} chars")
print(f"✅ Privada: {len(vapid_private)} chars")

# 6. También generar versión para probar en consola
print("\n6️⃣ PARA PROBAR EN CONSOLA JS:")
print("-" * 50)
print("Pega esto en la consola del navegador:")
print()
print(f"const testKey = '{vapid_public}';")
print('function urlBase64ToUint8Array(base64String) {')
print('  const padding = "=".repeat((4 - base64String.length % 4) % 4);')
print('  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");')
print('  const rawData = window.atob(base64);')
print('  const outputArray = new Uint8Array(rawData.length);')
print('  for (let i = 0; i < rawData.length; ++i) {')
print('    outputArray[i] = rawData.charCodeAt(i);')
print('  }')
print('  return outputArray;')
print('}')
print('const keyArray = urlBase64ToUint8Array(testKey);')
print('console.log("Key length:", keyArray.length, "debe ser 65");')
print('console.log("First byte:", keyArray[0], "debe ser 4");')