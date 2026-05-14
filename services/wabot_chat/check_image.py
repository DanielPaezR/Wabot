# Crea un archivo llamado check_image.py
import os
print(f"📁 ¿Existe logo.png? {os.path.exists('logo.png')}")
print(f"📏 Tamaño del archivo: {os.path.getsize('logo.png') if os.path.exists('logo.png') else 'No existe'} bytes")

if os.path.exists('logo.png'):
    from PIL import Image
    try:
        img = Image.open('logo.png')
        print(f"✅ Se puede abrir la imagen")
        print(f"📐 Dimensiones: {img.size}")
        print(f"🎨 Modo: {img.mode}")
        img.close()
    except Exception as e:
        print(f"❌ Error abriendo imagen: {e}")