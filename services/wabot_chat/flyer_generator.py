# flyer_generator.py — Versión SIMPLIFICADA y ROBUSTA
from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
from datetime import datetime

BASE_URL = 'https://wabot-deployment.up.railway.app/cliente/'
W, H = 1080, 1080

# Colores
BG      = (15, 23, 42)
CARD    = (30, 41, 59)
INDIGO  = (99, 102, 241)
AMBER   = (245, 158, 11)
GREEN   = (16, 185, 129)
WHITE   = (255, 255, 255)
GRAY    = (148, 163, 184)

def _font(size, bold=False):
    paths = [
        f'/usr/share/fonts/truetype/dejavu/DejaVuSans{"-Bold" if bold else ""}.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()

def _center(draw, y, text, font, fill, W):
    b = draw.textbbox((0,0), text, font=font)
    draw.text(((W-b[2]+b[0])//2, y), text, font=font, fill=fill)

def _wrap(text, font, draw, max_w):
    words, lines, cur = text.split(), [], ''
    for w in words:
        test = (cur+' '+w).strip()
        b = draw.textbbox((0,0), test, font=font)
        if b[2]-b[0] <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def _qr(url, size):
    qr = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color=CARD, back_color=WHITE).convert('RGBA').resize((size, size), Image.LANCZOS)

def generar_flyer_promocion(negocio_nombre, titulo_promo, descripcion, descuento, fecha_fin, negocio_id, profesional_nombre='', output_path=None):
    try:
        img = Image.new('RGB', (W, H), BG)
        draw = ImageDraw.Draw(img)
        
        # Fondo con gradiente sutil
        for y in range(H):
            r = int(15 + (10 * y/H))
            g = int(23 + (18 * y/H))
            b = int(42 + (20 * y/H))
            draw.line([(0,y), (W,y)], fill=(r,g,b))
        
        # Borde superior de color
        draw.rectangle([(0,0), (W,8)], fill=INDIGO)
        draw.rectangle([(0,H-8), (W,H)], fill=AMBER)
        
        y_pos = 60
        
        # Nombre del negocio
        fn = _font(36, True)
        _center(draw, y_pos, negocio_nombre.upper(), fn, INDIGO, W)
        y_pos += 60
        
        # Línea separadora
        draw.line([(W//4, y_pos), (3*W//4, y_pos)], fill=INDIGO, width=2)
        y_pos += 40
        
        # Badge oferta
        fb = _font(24, True)
        _center(draw, y_pos, '✦ OFERTA ESPECIAL ✦', fb, AMBER, W)
        y_pos += 60
        
        # Título
        ft = _font(64, True)
        for line in _wrap(titulo_promo.upper(), ft, draw, W-100)[:2]:
            _center(draw, y_pos, line, ft, WHITE, W)
            y_pos += 80
        
        # Descuento
        if descuento:
            y_pos += 20
            fh = _font(120, True)
            txt = f'{descuento}%'
            _center(draw, y_pos, txt, fh, AMBER, W)
            y_pos += 100
            fo = _font(40, True)
            _center(draw, y_pos, 'OFF', fo, WHITE, W)
            y_pos += 80
        
        # Descripción
        if descripcion:
            fd = _font(30, False)
            for line in _wrap(descripcion, fd, draw, W-150)[:2]:
                _center(draw, y_pos, line, fd, GRAY, W)
                y_pos += 45
        
        # Profesional
        if profesional_nombre:
            y_pos += 20
            fp = _font(32, True)
            _center(draw, y_pos, f'👤 con {profesional_nombre}', fp, WHITE, W)
            y_pos += 60
        
        # Fecha
        if fecha_fin:
            ff = _font(28, False)
            _center(draw, y_pos, f'📅 Válido hasta: {fecha_fin}', ff, GRAY, W)
            y_pos += 50
        
        # QR Code
        qr_size = 180
        qr_x = + 30
        qr_y = H - qr_size - 120
        qr_url = f'{BASE_URL}{negocio_id}'
        qr_img = _qr(qr_url, qr_size)
        img.paste(qr_img, (qr_x, qr_y), qr_img)
        
        # Texto QR
        fqr = _font(22, False)
        draw.text((qr_x - 10, qr_y + qr_size + 10), 'Escanea para agendar', font=fqr, fill=GRAY)
        
        # Botón CTA (a la derecha del QR)
        btn_x = qr_x + qr_size + 50
        btn_y = qr_y + 40
        btn_w = 400
        btn_h = 70
        draw.rounded_rectangle([btn_x, btn_y, btn_x+btn_w, btn_y+btn_h], radius=35, fill=GREEN)
        fcta = _font(36, True)
        cta_txt = '¡Agenda Ahora!'
        b = draw.textbbox((0,0), cta_txt, font=fcta)
        tx = btn_x + (btn_w - b[2] + b[0])//2
        ty = btn_y + (btn_h - b[3] + b[1])//2
        draw.text((tx, ty), cta_txt, font=fcta, fill=WHITE)
        
        # Footer
        ff2 = _font(22, False)
        _center(draw, H-35, 'Powered by Wabot · agendamiento inteligente', ff2, DIM, W) # type: ignore
        
        # Guardar
        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = 'static/flyers'
            os.makedirs(output_dir, exist_ok=True)
            output_path = f'{output_dir}/promo_{ts}.png'
        
        img.save(output_path, 'PNG', optimize=True)
        print(f'✅ Flyer generado: {output_path}')
        return output_path
        
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()
        return None


def generar_flyer_concurso(negocio_nombre, titulo_promo, premio, fecha_fin, negocio_id, profesional_nombre='', output_path=None):
    try:
        img = Image.new('RGB', (W, H), BG)
        draw = ImageDraw.Draw(img)
        
        for y in range(H):
            r = int(15 + (10 * y/H))
            g = int(23 + (18 * y/H))
            b = int(42 + (20 * y/H))
            draw.line([(0,y), (W,y)], fill=(r,g,b))
        
        draw.rectangle([(0,0), (W,8)], fill=AMBER)
        draw.rectangle([(0,H-8), (W,H)], fill=AMBER)
        
        y_pos = 60
        
        fn = _font(36, True)
        _center(draw, y_pos, negocio_nombre.upper(), fn, AMBER, W)
        y_pos += 60
        
        draw.line([(W//4, y_pos), (3*W//4, y_pos)], fill=AMBER, width=2)
        y_pos += 40
        
        # Ícono cámara
        fc = _font(80, True)
        _center(draw, y_pos, '📸', fc, WHITE, W)
        y_pos += 100
        
        # Badge concurso
        fb = _font(24, True)
        _center(draw, y_pos, '✦ CONCURSO DE FOTOS ✦', fb, AMBER, W)
        y_pos += 60
        
        # Título
        ft = _font(56, True)
        for line in _wrap(titulo_promo.upper(), ft, draw, W-100)[:2]:
            _center(draw, y_pos, line, ft, WHITE, W)
            y_pos += 70
        
        # Premio
        if premio:
            y_pos += 20
            fp2 = _font(32, True)
            _center(draw, y_pos, '🏆 PREMIO', fp2, AMBER, W)
            y_pos += 50
            fp3 = _font(52, True)
            for line in _wrap(premio, fp3, draw, W-150)[:2]:
                _center(draw, y_pos, line, fp3, WHITE, W)
                y_pos += 65
        
        # Pasos
        y_pos += 30
        pasos = ['1️⃣ Ven a tu cita', '2️⃣ Tómate la foto', '3️⃣ Súbela al concurso', '4️⃣ ¡Gana con más likes!']
        fs = _font(28, False)
        for paso in pasos:
            _center(draw, y_pos, paso, fs, GRAY, W)
            y_pos += 45
        
        # QR
        qr_size = 180
        qr_x = 30
        qr_y = H - qr_size - 120
        qr_url = f'{BASE_URL}{negocio_id}'
        qr_img = _qr(qr_url, qr_size)
        img.paste(qr_img, (qr_x, qr_y), qr_img)
        
        fqr = _font(22, False)
        draw.text((qr_x - 10, qr_y + qr_size + 10), 'Escanea y participa', font=fqr, fill=GRAY)
        
        # Botón
        btn_x = qr_x + qr_size + 50
        btn_y = qr_y + 40
        btn_w = 400
        btn_h = 70
        draw.rounded_rectangle([btn_x, btn_y, btn_x+btn_w, btn_y+btn_h], radius=35, fill=GREEN)
        fcta = _font(36, True)
        cta_txt = '¡Participa!'
        b = draw.textbbox((0,0), cta_txt, font=fcta)
        tx = btn_x + (btn_w - b[2] + b[0])//2
        ty = btn_y + (btn_h - b[3] + b[1])//2
        draw.text((tx, ty), cta_txt, font=fcta, fill=WHITE)
        
        ff2 = _font(22, False)
        _center(draw, H-35, 'Powered by Wabot · agendamiento inteligente', ff2, DIM, W) # type: ignore
        
        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = 'static/flyers'
            os.makedirs(output_dir, exist_ok=True)
            output_path = f'{output_dir}/concurso_{ts}.png'
        
        img.save(output_path, 'PNG', optimize=True)
        print(f'✅ Flyer concurso generado: {output_path}')
        return output_path
        
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()
        return None