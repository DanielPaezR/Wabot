# flyer_generator.py — Generador de flyers profesionales para Wabot
# Requiere: pip install pillow qrcode[pil]

from PIL import Image, ImageDraw, ImageFont
import qrcode
import os
import urllib.request
import sys
from datetime import datetime

# ─── CONFIGURACIÓN DE FUENTES (AUTO-DESCARGA) ────────────────────────────────

def descargar_fuente(url, path):
    """Descarga una fuente si no existe"""
    if os.path.exists(path):
        return True
    
    try:
        print(f"📥 Descargando fuente: {os.path.basename(path)}")
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Descargar la fuente
        urllib.request.urlretrieve(url, path)
        print(f"✅ Fuente descargada: {path}")
        return True
    except Exception as e:
        print(f"⚠️ No se pudo descargar {os.path.basename(path)}: {e}")
        return False

# URLs de las fuentes Poppins (usando GitHub de Google Fonts)
FONTS_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
os.makedirs(FONTS_DIR, exist_ok=True)

POPPINS_B_URL = 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf'
POPPINS_M_URL = 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf'
POPPINS_R_URL = 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf'
POPPINS_L_URL = 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf'

POPPINS_B = os.path.join(FONTS_DIR, 'Poppins-Bold.ttf')
POPPINS_M = os.path.join(FONTS_DIR, 'Poppins-Medium.ttf')
POPPINS_R = os.path.join(FONTS_DIR, 'Poppins-Regular.ttf')
POPPINS_L = os.path.join(FONTS_DIR, 'Poppins-Light.ttf')

# Descargar fuentes si no existen
descargar_fuente(POPPINS_B_URL, POPPINS_B)
descargar_fuente(POPPINS_M_URL, POPPINS_M)
descargar_fuente(POPPINS_R_URL, POPPINS_R)
descargar_fuente(POPPINS_L_URL, POPPINS_L)

# Fallback: usar fuentes del sistema si las descargas fallan
FALLBACK_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/System/Library/Fonts/Helvetica.ttf',  # macOS
    'C:\\Windows\\Fonts\\Arial.ttf',        # Windows
]

FALLBACK = None
for fb_path in FALLBACK_PATHS:
    if os.path.exists(fb_path):
        FALLBACK = fb_path
        break

if not FALLBACK:
    # Si no hay fuentes del sistema, usar la descargada o None
    FALLBACK = POPPINS_B if os.path.exists(POPPINS_B) else None

# ─── CONFIGURACIÓN GENERAL ───────────────────────────────────────────────────
BASE_URL = 'https://wabot-production-d544.up.railway.app/cliente/'  # URL base para QR

# ─── PALETA ──────────────────────────────────────────────────────────────────
C_BG      = (10,  12,  28)
C_CARD    = (18,  22,  48)
C_PRIMARY = (102, 126, 234)   # #667eea
C_ACCENT  = (245, 158,  11)   # #f59e0b
C_SUCCESS = (16,  185, 129)   # #10b981
C_WHITE   = (255, 255, 255)
C_LIGHT   = (148, 163, 184)
C_DIM     = ( 60,  70, 110)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _font(path, size):
    """Carga una fuente, con fallback si no existe"""
    if path and os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except:
            pass
    
    if FALLBACK and os.path.exists(FALLBACK):
        try:
            return ImageFont.truetype(FALLBACK, size)
        except:
            pass
    
    # Último recurso: fuente por defecto de PIL
    return ImageFont.load_default()


def _tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _center(draw, y, text, font, fill, W):
    draw.text(((W - _tw(draw, text, font)) // 2, y), text, font=font, fill=fill)


def _wrap(text, font, draw, max_w):
    words, lines, cur = text.split(), [], ''
    for w in words:
        test = (cur + ' ' + w).strip()
        if _tw(draw, test, font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _rounded_rect_ov(W, H, xy, r, fill=None, outline=None, lw=2):
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    x0, y0, x1, y1 = xy
    if fill:
        d.rectangle([x0+r, y0, x1-r, y1], fill=fill)
        d.rectangle([x0, y0+r, x1, y1-r], fill=fill)
        for ex, ey in [(x0,y0),(x1-2*r,y0),(x0,y1-2*r),(x1-2*r,y1-2*r)]:
            d.ellipse([ex, ey, ex+2*r, ey+2*r], fill=fill)
    if outline:
        for i in range(lw):
            d.arc([x0+i,y0+i,x0+2*r-i,y0+2*r-i], 180, 270, fill=outline)
            d.arc([x1-2*r+i,y0+i,x1-i,y0+2*r-i], 270, 360, fill=outline)
            d.arc([x0+i,y1-2*r+i,x0+2*r-i,y1-i], 90,  180, fill=outline)
            d.arc([x1-2*r+i,y1-2*r+i,x1-i,y1-i], 0,   90,  fill=outline)
            d.line([x0+r,y0+i,x1-r,y0+i], fill=outline)
            d.line([x0+r,y1-i,x1-r,y1-i], fill=outline)
            d.line([x0+i,y0+r,x0+i,y1-r], fill=outline)
            d.line([x1-i,y0+r,x1-i,y1-r], fill=outline)
    return ov


def _comp(img, ov):
    rgba = img.convert('RGBA')
    rgba.alpha_composite(ov)
    return rgba.convert('RGB')


def _gradient_stripe(draw, x0, y0, x1, y1, ca, cb):
    for x in range(x0, x1):
        r = (x - x0) / max(x1 - x0 - 1, 1)
        draw.line([(x, y0), (x, y1)],
                  fill=tuple(int(ca[i] + (cb[i]-ca[i])*r) for i in range(3)))


def _bg(W, H):
    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        r = y / H
        draw.line([(0,y),(W,y)],
                  fill=tuple(int(C_BG[i]+(C_CARD[i]-C_BG[i])*r) for i in range(3)))
    ov = Image.new('RGBA', (W, H), (0,0,0,0))
    od = ImageDraw.Draw(ov)
    od.ellipse([-180,-180,420,420],  fill=(*C_PRIMARY,28))
    od.ellipse([680,680,1260,1260],  fill=(*C_ACCENT, 18))
    od.ellipse([820,-120,1200,260],  fill=(*C_SUCCESS,16))
    return _comp(img, ov)


def _make_qr(url, size, negocio_id=None):
    """
    Genera un QR real apuntando a BASE_URL + negocio_id (o a url directamente).
    Devuelve una imagen PIL RGBA lista para pegar en el flyer.
    """
    # Construir la URL final
    if negocio_id is not None:
        target_url = BASE_URL + str(negocio_id)
    else:
        target_url = url  # si ya viene la URL completa, se usa tal cual

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    # Módulos oscuros sobre fondo blanco
    qr_img = qr.make_image(fill_color=C_CARD, back_color=(255, 255, 255))
    qr_img = qr_img.convert('RGBA')
    qr_img = qr_img.resize((size, size), Image.LANCZOS)
    return qr_img


def _paste_qr(img, draw, qr_url, negocio_id, x, y, size, border_color):
    """
    Genera el QR funcional, lo pega con fondo blanco redondeado y devuelve
    (img, draw) actualizados.
    """
    # Fondo blanco redondeado
    padding = 10
    bg_xy = [x - padding, y - padding, x + size + padding, y + size + padding]
    ov_bg = _rounded_rect_ov(img.width, img.height, bg_xy, r=14,
                              fill=(255,255,255,255),
                              outline=(*border_color, 180), lw=3)
    img = _comp(img, ov_bg)

    # QR real
    qr_img = _make_qr(qr_url, size, negocio_id)
    img_rgba = img.convert('RGBA')
    img_rgba.paste(qr_img, (x, y), qr_img)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)
    return img, draw


def _output_path(prefix):
    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = 'static/flyers'
    os.makedirs(out, exist_ok=True)
    return f'{out}/{prefix}_{ts}.png'


# ─── FLYER DE PROMOCIÓN ───────────────────────────────────────────────────────

def generar_flyer_promocion(negocio_nombre, titulo_promo, descripcion,
                             descuento, fecha_fin, negocio_id,
                             profesional_nombre='', output_path=None):
    """
    Genera un flyer 1080×1080 px para una promoción con descuento.

    Parámetros:
        negocio_nombre    – Nombre del negocio / salón
        titulo_promo      – Título corto del servicio o promo
        descripcion       – Descripción del servicio (1-2 oraciones)
        descuento         – Entero con el % de descuento, o None si no aplica
        fecha_fin         – String con la fecha límite (ej. "31 de enero 2025")
        negocio_id        – ID del negocio → genera QR a BASE_URL + negocio_id
        profesional_nombre– Nombre del profesional (opcional)
        output_path       – Ruta de salida. None = se genera automáticamente.

    Retorna la ruta del archivo generado, o None si hubo error.
    """
    try:
        W, H, PAD = 1080, 1080, 60
        img  = _bg(W, H)
        draw = ImageDraw.Draw(img)

        # Stripe superior
        _gradient_stripe(draw, 0, 0, W, 10, C_PRIMARY, C_ACCENT)

        # Pill nombre del negocio
        y     = 48
        f_neg = _font(POPPINS_M, 30)
        neg_u = negocio_nombre.upper()
        nw    = _tw(draw, neg_u, f_neg)
        pp    = 22
        px0, px1 = (W-nw-pp*2)//2, (W-nw-pp*2)//2 + nw + pp*2
        img = _comp(img, _rounded_rect_ov(W, H, [px0, y, px1, y+52], 26,
                                           fill=(*C_PRIMARY,32),
                                           outline=(*C_PRIMARY,160), lw=2))
        draw = ImageDraw.Draw(img)
        _center(draw, y+10, neg_u, f_neg, C_PRIMARY, W)

        # Badge oferta
        y = 132
        _center(draw, y, '✦  OFERTA ESPECIAL  ✦', _font(POPPINS_M, 22), C_ACCENT, W)

        # Separador
        y = 170
        mid = W // 2
        draw.line([(PAD, y+10), (mid-170, y+10)], fill=C_PRIMARY, width=2)
        draw.line([(mid+170, y+10), (W-PAD, y+10)], fill=C_PRIMARY, width=2)
        draw.polygon([(mid-9,y+10),(mid,y+2),(mid+9,y+10),(mid,y+18)], fill=C_ACCENT)

        # Título
        y = 195
        f_t = _font(POPPINS_B, 58)
        for line in _wrap(titulo_promo.upper(), f_t, draw, W-PAD*2)[:2]:
            _center(draw, y, line, f_t, C_WHITE, W); y += 70

        # Descuento grande
        if descuento:
            y += 8
            f_h, f_o = _font(POPPINS_B, 100), _font(POPPINS_B, 38)
            pt = f'{descuento}%'
            pw, ow = _tw(draw, pt, f_h), _tw(draw, 'OFF', f_o)
            total_w = pw + 28 + ow
            bx0, bx1 = (W-total_w-64)//2, (W-total_w-64)//2 + total_w + 64
            img = _comp(img, _rounded_rect_ov(W, H, [bx0, y-10, bx1, y+118], 30,
                                               fill=(*C_ACCENT,22),
                                               outline=(*C_ACCENT,80), lw=2))
            draw = ImageDraw.Draw(img)
            xs = (W - total_w) // 2
            draw.text((xs, y), pt, font=f_h, fill=C_ACCENT)
            draw.text((xs+pw+28, y+44), 'OFF', font=f_o, fill=C_WHITE)
            y += 128

        # Descripción
        if descripcion:
            f_b = _font(POPPINS_R, 28)
            for line in _wrap(descripcion, f_b, draw, W-PAD*3)[:3]:
                _center(draw, y, line, f_b, C_LIGHT, W); y += 40
            y += 8

        # Profesional
        if profesional_nombre:
            _center(draw, y, f'👤  con {profesional_nombre}',
                    _font(POPPINS_M, 28), C_WHITE, W); y += 50

        # Separador fino
        sep_y = max(y+14, 760)
        draw.line([(PAD*2, sep_y), (W-PAD*2, sep_y)], fill=(40,50,90), width=1)
        footer_y = sep_y + 28

        # QR funcional
        qr_size = 140
        qr_x, qr_y = PAD + 14, footer_y
        qr_url = BASE_URL + str(negocio_id)
        img, draw = _paste_qr(img, draw, qr_url, negocio_id,
                               qr_x, qr_y, qr_size, C_PRIMARY)
        draw.text((qr_x - 10, qr_y + qr_size + 14),
                  'Escanea para agendar', font=_font(POPPINS_L, 21), fill=C_LIGHT)

        # Info derecha del QR
        info_x, info_y = qr_x + qr_size + 50, footer_y + 8
        if fecha_fin:
            draw.text((info_x, info_y), '📅  Válido hasta',
                      font=_font(POPPINS_L, 22), fill=C_LIGHT)
            draw.text((info_x, info_y+30), str(fecha_fin),
                      font=_font(POPPINS_B, 28), fill=C_WHITE)
            info_y += 84

        cta, f_cta = '¡Agenda ahora!', _font(POPPINS_B, 26)
        cw = _tw(draw, cta, f_cta)
        img = _comp(img, _rounded_rect_ov(W, H,
                                           [info_x, info_y, info_x+cw+34, info_y+48],
                                           23, fill=(*C_SUCCESS,220)))
        draw = ImageDraw.Draw(img)
        draw.text((info_x+17, info_y+10), cta, font=f_cta, fill=C_WHITE)

        # Brand
        _center(draw, H-44, 'Powered by Wabot · agendamiento inteligente',
                _font(POPPINS_L, 20), C_DIM, W)
        _gradient_stripe(draw, 0, H-9, W, H, C_ACCENT, C_PRIMARY)

        path = output_path or _output_path('promo')
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        img.save(path, 'PNG', optimize=True)
        print(f'✅ Flyer promo generado: {path}')
        print(f'   QR apunta a: {qr_url}')
        return path

    except Exception as e:
        print(f'❌ Error generando flyer promo: {e}')
        import traceback; traceback.print_exc()
        return None


# ─── FLYER DE CONCURSO ───────────────────────────────────────────────────────

def generar_flyer_concurso(negocio_nombre, titulo_promo, premio,
                            fecha_fin, negocio_id,
                            profesional_nombre='', output_path=None):
    """
    Genera un flyer 1080×1080 px para un concurso de fotos.

    Parámetros:
        negocio_nombre    – Nombre del negocio / salón
        titulo_promo      – Título del concurso
        premio            – Descripción del premio principal
        fecha_fin         – String con la fecha límite
        negocio_id        – ID del negocio → genera QR a BASE_URL + negocio_id
        profesional_nombre– Nombre del profesional (opcional)
        output_path       – Ruta de salida. None = se genera automáticamente.

    Retorna la ruta del archivo generado, o None si hubo error.
    """
    try:
        W, H, PAD = 1080, 1080, 60
        img  = _bg(W, H)
        draw = ImageDraw.Draw(img)

        # Stripe superior (paleta concurso: dorado → rojo)
        _gradient_stripe(draw, 0, 0, W, 10, C_ACCENT, (239, 68, 68))

        # Pill nombre del negocio
        y     = 48
        f_neg = _font(POPPINS_M, 30)
        neg_u = negocio_nombre.upper()
        nw    = _tw(draw, neg_u, f_neg)
        pp    = 22
        px0, px1 = (W-nw-pp*2)//2, (W-nw-pp*2)//2 + nw + pp*2
        img = _comp(img, _rounded_rect_ov(W, H, [px0, y, px1, y+52], 26,
                                           fill=(*C_ACCENT,28),
                                           outline=(*C_ACCENT,160), lw=2))
        draw = ImageDraw.Draw(img)
        _center(draw, y+10, neg_u, f_neg, C_ACCENT, W)

        # Ícono cámara
        y = 130
        _center(draw, y, '📸', _font(POPPINS_B, 70), C_WHITE, W)

        # Badge concurso
        y = 218
        _center(draw, y, '✦  CONCURSO DE FOTOS  ✦', _font(POPPINS_M, 22), C_ACCENT, W)

        # Título
        y = 254
        f_t = _font(POPPINS_B, 54)
        for line in _wrap(titulo_promo.upper(), f_t, draw, W-PAD*2)[:2]:
            _center(draw, y, line, f_t, C_WHITE, W); y += 65

        # Premio
        if premio:
            y += 10
            _center(draw, y, '🏆  PREMIO', _font(POPPINS_M, 30), C_ACCENT, W)
            y += 46
            f_p = _font(POPPINS_B, 60)
            prize_lines = _wrap(premio, f_p, draw, W-PAD*2)[:2]
            bh = len(prize_lines)*72 + 20
            img = _comp(img, _rounded_rect_ov(W, H, [PAD*2, y-10, W-PAD*2, y+bh], 24,
                                               fill=(*C_ACCENT,20),
                                               outline=(*C_ACCENT,90), lw=2))
            draw = ImageDraw.Draw(img)
            for line in prize_lines:
                _center(draw, y, line, f_p, C_ACCENT, W); y += 72
            y += 18

        # Pasos
        y += 10
        pasos = [
            ('1', 'Ven a tu cita',          '→ Agenda con nosotros'),
            ('2', 'Tómate la foto',          '→ Muestra tu nuevo look'),
            ('3', 'Súbela al concurso',      '→ Escanea el QR'),
            ('4', 'Consigue más likes',      '→ ¡Gana el premio!'),
        ]
        f_pn = _font(POPPINS_B, 24)
        f_pt = _font(POPPINS_M, 24)
        f_pd = _font(POPPINS_L, 21)
        sx   = PAD + 20

        for num, tit, det in pasos:
            cr = 22
            cx_, cy_ = sx+cr, y+cr
            img = _comp(img, _rounded_rect_ov(W, H,
                                               [cx_-cr, cy_-cr, cx_+cr, cy_+cr],
                                               cr, fill=(*C_PRIMARY,220)))
            draw = ImageDraw.Draw(img)
            nw2 = _tw(draw, num, f_pn)
            draw.text((cx_-nw2//2, cy_-14), num, font=f_pn, fill=C_WHITE)
            tx = sx + cr*2 + 16
            draw.text((tx, y+4),  tit, font=f_pt, fill=C_WHITE)
            draw.text((tx, y+30), det, font=f_pd, fill=C_LIGHT)
            y += 54

        # Profesional
        if profesional_nombre:
            _center(draw, y+6, f'👤  con {profesional_nombre}',
                    _font(POPPINS_M, 26), C_WHITE, W); y += 44

        # Separador fino
        sep_y = max(y+10, 828)
        draw.line([(PAD*2, sep_y), (W-PAD*2, sep_y)], fill=(40,50,90), width=1)
        footer_y = sep_y + 24

        # QR funcional
        qr_size = 130
        qr_x, qr_y = PAD + 14, footer_y
        qr_url = BASE_URL + str(negocio_id)
        img, draw = _paste_qr(img, draw, qr_url, negocio_id,
                               qr_x, qr_y, qr_size, C_ACCENT)
        draw.text((qr_x - 10, qr_y + qr_size + 14),
                  'Escanea y participa', font=_font(POPPINS_L, 20), fill=C_LIGHT)

        # Info derecha
        info_x, info_y = qr_x + qr_size + 46, footer_y + 8
        if fecha_fin:
            draw.text((info_x, info_y), '📅  Válido hasta',
                      font=_font(POPPINS_L, 21), fill=C_LIGHT)
            draw.text((info_x, info_y+28), str(fecha_fin),
                      font=_font(POPPINS_B, 26), fill=C_WHITE)
            info_y += 76

        cta, f_cta = '¡Participa gratis!', _font(POPPINS_B, 25)
        cw = _tw(draw, cta, f_cta)
        img = _comp(img, _rounded_rect_ov(W, H,
                                           [info_x, info_y, info_x+cw+34, info_y+46],
                                           23, fill=(*C_SUCCESS,220)))
        draw = ImageDraw.Draw(img)
        draw.text((info_x+17, info_y+10), cta, font=f_cta, fill=C_WHITE)

        # Brand
        _center(draw, H-44, 'Powered by Wabot · agendamiento inteligente',
                _font(POPPINS_L, 20), C_DIM, W)
        _gradient_stripe(draw, 0, H-9, W, H, (239,68,68), C_ACCENT)

        path = output_path or _output_path('concurso')
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        img.save(path, 'PNG', optimize=True)
        print(f'✅ Flyer concurso generado: {path}')
        print(f'   QR apunta a: {qr_url}')
        return path

    except Exception as e:
        print(f'❌ Error generando flyer concurso: {e}')
        import traceback; traceback.print_exc()
        return None


# ─── EJEMPLO DE USO ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    generar_flyer_promocion(
        negocio_nombre     = 'Barbería Imperial',
        titulo_promo       = 'Corte + Barba Premium',
        descripcion        = 'Incluye lavado, corte personalizado y acabado con navaja.',
        descuento          = 30,
        fecha_fin          = '31 de enero 2025',
        negocio_id         = 42,
        profesional_nombre = 'Carlos Rodríguez',
    )

    generar_flyer_concurso(
        negocio_nombre     = 'Barbería Imperial',
        titulo_promo       = 'El Mejor Corte del Mes',
        premio             = 'Corte Gratis por 3 Meses',
        fecha_fin          = '28 de febrero 2025',
        negocio_id         = 42,
        profesional_nombre = 'Carlos Rodríguez',
    )