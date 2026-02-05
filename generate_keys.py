# generate_valid_vapid_keys.py
import base64
import os

print("🔥 GENERANDO CLAVES VAPID VÁLIDAS 🔥")
print("=" * 50)

# Generar bytes aleatorios para claves EC válidas
# Clave pública: 65 bytes (0x04 + X(32) + Y(32))
public_bytes = os.urandom(65)
# El primer byte DEBE ser 0x04 para formato sin comprimir
public_bytes = b'\x04' + public_bytes[1:]

# Clave privada: 32 bytes
private_bytes = os.urandom(32)

# Convertir a base64 URL-safe
vapid_public_key = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')
vapid_private_key = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')

print("\n1️⃣ CLAVE PÚBLICA (VAPID_PUBLIC_KEY):")
print("-" * 40)
print(vapid_public_key)
print(f"📏 Longitud: {len(vapid_public_key)} caracteres (debe ser 87)")

print("\n2️⃣ CLAVE PRIVADA (VAPID_PRIVATE_KEY):")
print("-" * 40)
print(vapid_private_key)
print(f"📏 Longitud: {len(vapid_private_key)} caracteres (debe ser 43)")

print("\n3️⃣ PARA RAILWAY:")
print("-" * 40)
print("COPIA Y PEGA EXACTAMENTE:")
print()
print(f"VAPID_PUBLIC_KEY={vapid_public_key}")
print(f"VAPID_PRIVATE_KEY={vapid_private_key}")
print("VAPID_SUBJECT=mailto:danielpaezrami@gmail.com")

print("\n4️⃣ VERIFICACIÓN:")
print("-" * 40)
print("Para verificar que son válidas:")
print("1. Copia la clave pública")
print("2. Ve a: https://wabot-deployment.up.railway.app/verify-key-tool")
print("3. Pega la clave y verifica")

# Guardar en archivo por si acaso
with open('vapid_keys.txt', 'w') as f:
    f.write(f"VAPID_PUBLIC_KEY={vapid_public_key}\n")
    f.write(f"VAPID_PRIVATE_KEY={vapid_private_key}\n")
    f.write("VAPID_SUBJECT=mailto:danielpaezrami@gmail.com\n")

print("\n✅ Claves guardadas en 'vapid_keys.txt'")