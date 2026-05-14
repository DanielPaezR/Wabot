#!/usr/bin/env python3
"""
Script para generar iconos PWA a partir de una imagen base.
Uso: python generate_icons.py
"""

from PIL import Image, ImageDraw, ImageFont
import os
import sys

def ensure_square_image(image_path):
    """Asegura que la imagen sea cuadrada recortando si es necesario"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            
            if width == height:
                print(f"   ✓ Imagen ya es cuadrada: {width}x{height}")
                return img.copy()  # IMPORTANTE: Devuelve una copia
            
            # Recortar para hacerla cuadrada
            print(f"   ⚠️  Imagen no es cuadrada: {width}x{height}, recortando...")
            min_size = min(width, height)
            left = (width - min_size) // 2
            top = (height - min_size) // 2
            right = left + min_size
            bottom = top + min_size
            
            cropped_img = img.crop((left, top, right, bottom))
            print(f"   ✓ Recortado a: {cropped_img.size}")
            return cropped_img
            
    except Exception as e:
        print(f"   ❌ Error procesando imagen: {e}")
        return None

def generate_pwa_icons(base_image_path, output_dir="static/icons"):
    """Genera todos los iconos necesarios para PWA"""
    
    print(f"🎨 Generando iconos PWA desde: {base_image_path}")
    
    # Crear directorios si no existen
    os.makedirs(output_dir, exist_ok=True)
    
    # Tamaños estándar para PWA
    pwa_sizes = [
        16, 32, 72, 96, 128, 144, 152, 167, 180, 192, 256, 384, 512
    ]
    
    # Tamaños específicos para iOS
    ios_sizes = [
        57, 60, 72, 76, 114, 120, 144, 152, 167, 180, 192, 512
    ]
    
    # Tamaños para Android
    android_sizes = [
        36, 48, 72, 96, 144, 192, 512
    ]
    
    # Todos los tamaños necesarios
    all_sizes = sorted(set(pwa_sizes + ios_sizes + android_sizes))
    
    try:
        # Abrir y procesar imagen base
        print("📐 Procesando imagen base...")
        img = ensure_square_image(base_image_path)
        
        # Generar iconos en cada tamaño
        for size in all_sizes:
            output_path = os.path.join(output_dir, f"icon-{size}x{size}.png")
            
            # Redimensionar manteniendo calidad
            resized_img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # Guardar como PNG
            resized_img.save(output_path, 'PNG', optimize=True)
            print(f"  ✅ {size}x{size} -> {output_path}")
        
        # Generar favicon.ico (formato ICO con múltiples tamaños)
        print("\n🎯 Generando favicon.ico...")
        ico_sizes = [(16, 16), (32, 32), (48, 48)]
        ico_images = []
        
        for ico_size in ico_sizes:
            ico_img = img.resize(ico_size, Image.Resampling.LANCZOS)
            if ico_img.mode != 'RGBA':
                ico_img = ico_img.convert('RGBA')
            ico_images.append(ico_img)
        
        ico_images[0].save(
            os.path.join(output_dir, "favicon.ico"),
            format='ICO',
            sizes=[(s[0], s[1]) for s in ico_sizes],
            append_images=ico_images[1:]
        )
        print(f"  ✅ favicon.ico generado")
        
        # Generar icono para apple-touch-icon (sin etiquetas)
        print("\n🍎 Generando iconos para Apple...")
        apple_sizes = [57, 60, 72, 76, 114, 120, 144, 152, 167, 180]
        
        for size in apple_sizes:
            output_path = os.path.join(output_dir, f"apple-touch-icon-{size}x{size}.png")
            apple_img = img.resize((size, size), Image.Resampling.LANCZOS)
            apple_img.save(output_path, 'PNG', optimize=True)
            print(f"  ✅ Apple {size}x{size}")
        
        # Generar icono maskable (con bordes redondeados)
        print("\n🟢 Generando iconos maskable...")
        maskable_sizes = [192, 512]
        
        for size in maskable_sizes:
            # Crear imagen con bordes redondeados
            rounded_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            mask = Image.new('L', (size, size), 0)
            draw = ImageDraw.Draw(mask)
            
            # Dibujar círculo como máscara
            draw.ellipse([(0, 0), (size, size)], fill=255)
            
            # Redimensionar imagen original
            resized_img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # Aplicar máscara
            if resized_img.mode != 'RGBA':
                resized_img = resized_img.convert('RGBA')
            
            rounded_img.paste(resized_img, (0, 0), mask)
            
            output_path = os.path.join(output_dir, f"icon-maskable-{size}x{size}.png")
            rounded_img.save(output_path, 'PNG', optimize=True)
            print(f"  ✅ Maskable {size}x{size}")
        
        print(f"\n🎉 ¡Iconos generados exitosamente!")
        print(f"📁 Guardados en: {os.path.abspath(output_dir)}")
        print(f"\n📋 Total de iconos generados: {len(all_sizes) + len(apple_sizes) + len(maskable_sizes) + 1}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error generando iconos: {e}")
        return False

def create_default_icon_if_needed():
    """Crea un icono por defecto si no existe imagen base"""
    
    print("🎨 Creando icono por defecto...")
    
    # Crear icono simple con círculo azul y letra "A"
    size = 512
    img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Dibujar círculo
    draw.ellipse([(50, 50), (size-50, size-50)], fill=(0, 123, 255, 255))
    
    # Dibujar texto
    try:
        font = ImageFont.truetype("arial.ttf", 200)
    except:
        font = ImageFont.load_default()
    
    # Calcular posición del texto
    text = "A"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((size - text_width) // 2, (size - text_height) // 2 - 20)
    
    draw.text(position, text, fill=(255, 255, 255, 255), font=font)
    
    # Guardar como imagen base temporal
    img.save("default-logo.png", "PNG")
    print("✅ Icono por defecto creado: default-logo.png")
    
    return "default-logo.png"

def main():
    """Función principal del script"""
    
    print("=" * 50)
    print("🛠️  GENERADOR DE ICONOS PWA")
    print("=" * 50)
    
    # Buscar imagen base
    possible_names = [
        "logo.png", "logo.jpg", "logo.jpeg", "logo.webp",
        "icon.png", "icon.jpg",
        "brand.png", "brand.jpg",
        "logotipo.png", "logotipo.jpg"
    ]
    
    base_image = None
    
    # Buscar archivos en el directorio actual
    for filename in possible_names:
        if os.path.exists(filename):
            base_image = filename
            break
    
    # Si no se encuentra, crear uno por defecto
    if not base_image:
        print("⚠️  No se encontró ninguna imagen base.")
        print("   Buscando: " + ", ".join(possible_names))
        
        create_default = input("¿Crear icono por defecto? (s/n): ").lower()
        if create_default == 's':
            base_image = create_default_icon_if_needed()
        else:
            print("❌ No se puede continuar sin imagen base.")
            sys.exit(1)
    
    # Ejecutar generación
    success = generate_pwa_icons(base_image)
    
    if success:
        print("\n" + "=" * 50)
        print("✅ PROCESO COMPLETADO")
        print("=" * 50)
        print("\n📋 Pasos siguientes:")
        print("1. Verifica que los iconos se generaron en static/icons/")
        print("2. Actualiza tu template HTML con las meta tags")
        print("3. Crea o actualiza el archivo manifest.json")
        print("\n🚀 ¡Tu PWA ahora tendrá iconos profesionales!")
    else:
        print("\n❌ No se pudieron generar los iconos")

if __name__ == "__main__":
    main()