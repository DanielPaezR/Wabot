# flyer_generator.py - Generador de flyers para promociones
from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime

def generar_flyer_promocion(negocio_nombre, titulo_promo, descripcion, descuento, fecha_fin, qr_url, profesional_nombre='', output_path=None):
    """
    Genera un flyer para una promoción.
    Retorna la ruta del archivo generado.
    """
    try:
        # Configuración de la imagen
        width, height = 1080, 1080  # Tamaño cuadrado para Instagram
        img = Image.new('RGB', (width, height), color='#1e293b')
        draw = ImageDraw.Draw(img)
        
        # Intentar cargar fuentes
        try:
            font_title = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 60)
            font_subtitle = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 36)
            font_body = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 28)
            font_big = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 80)
        except:
            # Fallback a fuente por defecto
            font_title = ImageFont.load_default()
            font_subtitle = ImageFont.load_default()
            font_body = ImageFont.load_default()
            font_big = ImageFont.load_default()
        
        # Colores
        primary = '#6366f1'
        gold = '#f59e0b'
        white = '#ffffff'
        light = '#94a3b8'
        dark_bg = '#0f172a'
        
        # Fondo con gradiente simple (bandas de color)
        for y in range(height):
            ratio = y / height
            r = int(30 + (15 * ratio))
            g = int(41 + (23 * ratio))
            b = int(59 + (30 * ratio))
            for x in range(width):
                img.putpixel((x, y), (r, g, b))
        
        # Borde decorativo
        draw.rectangle([20, 20, width-20, height-20], outline=primary, width=3)
        draw.rectangle([30, 30, width-30, height-30], outline=gold, width=1)
        
        # Logo / Nombre del negocio
        draw.text((width//2, 80), negocio_nombre, fill=gold, font=font_title, anchor='mt')
        
        # Línea decorativa
        draw.line([(width//4, 140), (width*3//4, 140)], fill=primary, width=2)
        
        # Título de la promo
        draw.text((width//2, 200), titulo_promo.upper(), fill=white, font=font_title, anchor='mt')
        
        # Descuento (grande)
        if descuento:
            descuento_texto = f"¡{descuento}% OFF!"
            draw.text((width//2, 340), descuento_texto, fill=gold, font=font_big, anchor='mt')
        
        # Descripción
        if descripcion:
            # Dividir en líneas
            palabras = descripcion.split()
            lineas = []
            linea_actual = ''
            for palabra in palabras:
                if len(linea_actual + palabra) < 40:
                    linea_actual += palabra + ' '
                else:
                    lineas.append(linea_actual.strip())
                    linea_actual = palabra + ' '
            lineas.append(linea_actual.strip())
            
            y_texto = 430 if descuento else 300
            for linea in lineas[:3]:
                draw.text((width//2, y_texto), linea, fill=light, font=font_body, anchor='mt')
                y_texto += 40
        
        # Profesional
        if profesional_nombre:
            draw.text((width//2, 520), f"con {profesional_nombre}", fill=white, font=font_subtitle, anchor='mt')
        
        # Fecha
        if fecha_fin:
            draw.text((width//2, 580), f"Válido hasta: {fecha_fin}", fill=light, font=font_body, anchor='mt')
        
        # QR (simulado con un rectángulo)
        qr_size = 200
        qr_x = (width - qr_size) // 2
        qr_y = 660
        draw.rectangle([qr_x, qr_y, qr_x + qr_size, qr_y + qr_size], fill=white, outline=primary, width=2)
        draw.text((width//2, qr_y + qr_size//2), "📱 QR", fill=dark_bg, font=font_subtitle, anchor='mt')
        
        # Texto debajo del QR
        draw.text((width//2, qr_y + qr_size + 30), "Escanea y agenda tu cita", fill=white, font=font_body, anchor='mt')
        
        # Footer
        draw.text((width//2, height - 60), "Wabot · Agendamiento Inteligente", fill=primary, font=font_body, anchor='mt')
        
        # Guardar
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = 'static/flyers'
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/promo_{timestamp}.png"
        
        img.save(output_path, 'PNG')
        print(f"✅ Flyer generado: {output_path}")
        
        return output_path
        
    except Exception as e:
        print(f"❌ Error generando flyer: {e}")
        import traceback
        traceback.print_exc()
        return None


def generar_flyer_concurso(negocio_nombre, titulo_promo, premio, fecha_fin, qr_url, profesional_nombre='', output_path=None):
    """
    Genera un flyer específico para concurso de fotos.
    """
    try:
        width, height = 1080, 1080
        img = Image.new('RGB', (width, height), color='#1e293b')
        draw = ImageDraw.Draw(img)
        
        try:
            font_title = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 55)
            font_body = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30)
            font_big = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 70)
        except:
            font_title = ImageFont.load_default()
            font_body = ImageFont.load_default()
            font_big = ImageFont.load_default()
        
        primary = '#6366f1'
        gold = '#f59e0b'
        white = '#ffffff'
        light = '#94a3b8'
        
        # Fondo gradiente
        for y in range(height):
            ratio = y / height
            r = int(30 + (15 * ratio))
            g = int(41 + (23 * ratio))
            b = int(59 + (30 * ratio))
            for x in range(width):
                img.putpixel((x, y), (r, g, b))
        
        # Borde
        draw.rectangle([20, 20, width-20, height-20], outline=gold, width=4)
        
        # Título
        draw.text((width//2, 100), negocio_nombre, fill=gold, font=font_title, anchor='mt')
        draw.line([(width//4, 150), (width*3//4, 150)], fill=primary, width=2)
        
        draw.text((width//2, 220), "📸 CONCURSO DE FOTOS", fill=white, font=font_title, anchor='mt')
        draw.text((width//2, 300), titulo_promo, fill=primary, font=font_body, anchor='mt')
        
        if premio:
            draw.text((width//2, 400), "🏆 PREMIO:", fill=gold, font=font_title, anchor='mt')
            draw.text((width//2, 480), premio, fill=white, font=font_big, anchor='mt')
        
        # Instrucciones
        instrucciones = [
            "1. Ven a la barbería",
            "2. Tómate una foto con tu corte",
            "3. Súbela a nuestro concurso",
            "4. ¡Gana la foto con más likes!"
        ]
        y_inst = 580
        for instruccion in instrucciones:
            draw.text((width//2, y_inst), instruccion, fill=light, font=font_body, anchor='mt')
            y_inst += 50
        
        if fecha_fin:
            draw.text((width//2, 820), f"Válido hasta: {fecha_fin}", fill=light, font=font_body, anchor='mt')
        
        # QR
        qr_size = 160
        qr_x = (width - qr_size) // 2
        qr_y = 860
        draw.rectangle([qr_x, qr_y, qr_x + qr_size, qr_y + qr_size], fill=white, outline=gold, width=2)
        draw.text((width//2, qr_y + qr_size//2), "📱", fill='#1e293b', font=font_big, anchor='mt')
        
        draw.text((width//2, height - 40), "Wabot · Agendamiento Inteligente", fill=primary, font=font_body, anchor='mt')
        
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = 'static/flyers'
            os.makedirs(output_dir, exist_ok=True)
            output_path = f"{output_dir}/concurso_{timestamp}.png"
        
        img.save(output_path, 'PNG')
        print(f"✅ Flyer concurso generado: {output_path}")
        
        return output_path
        
    except Exception as e:
        print(f"❌ Error generando flyer concurso: {e}")
        return None