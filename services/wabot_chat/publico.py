"""Cara pública de Wabot: el perfil de cada negocio y de cada profesional, con reserva directa.

La idea central: el cliente abre un enlace corto (``/nacho``), ve el negocio y reserva en cuatro toques
(servicio → profesional → día y hora → nombre y WhatsApp). Nada de chat obligatorio: el asistente queda
como ayuda opcional para preguntas, y si la pregunta termina en una reserva, abre el formulario ya lleno.

Todo lo que toca la agenda reutiliza las piezas probadas del proyecto:
``disponibilidad.horarios_libres`` (horarios libres) y ``database.agregar_cita`` (bloqueo por profesional,
solapamientos y bloqueos recurrentes), y los avisos push al profesional de ``push_notifications``.
"""
import json
import re
import threading
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from psycopg2.extras import RealDictCursor

import database as db
import disponibilidad
import localizacion

bp = Blueprint('publico', __name__)

ACENTO_DEFECTO = '#d4a857'
DIAS_RESERVA = 21
TIPOS_ALQUILER = ('alquiler_vehiculos', 'renta_autos')

# Primer segmento de las rutas existentes: un negocio nunca puede tener uno de estos como enlace.
RESERVADOS = {
    'admin', 'api', 'app', 'cliente', 'negocio', 'profesional', 'login', 'logout', 'static', 'health', 'push',
    'manifest', 'manifest-login', 'service-worker', 'firebase-messaging-sw', 'calificar', 'vota', 'participar',
    'wabot-ventas', 'alquiler', 'actualizar-cache', 'directorio', 'explorar', 'reservar', 'mis-citas', 'ayuda',
    'favicon', 'robots', 'sitemap', 'wabot', 'www', 'panel', 'r',
}
# Palabras genéricas que se quitan para que el enlace quede corto: "Barbería Nacho" -> "nacho"
_GENERICAS = ('barberia', 'barber shop', 'barbershop', 'barber', 'peluqueria', 'spa', 'salon', 'estudio')

DIAS_CORTOS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
DIAS_LARGOS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
                'octubre', 'noviembre', 'diciembre']

VOCABULARIO = {
    'barberia': {'pro': 'barbero', 'pros': 'barberos', 'equipo': 'Nuestros barberos'},
    'peluqueria': {'pro': 'estilista', 'pros': 'estilistas', 'equipo': 'Nuestros estilistas'},
    'spa_unas': {'pro': 'manicurista', 'pros': 'manicuristas', 'equipo': 'Nuestro equipo'},
    'tattoo': {'pro': 'artista', 'pros': 'artistas', 'equipo': 'Nuestros artistas'},
}
VOCAB_DEFECTO = {'pro': 'profesional', 'pros': 'profesionales', 'equipo': 'Nuestro equipo'}

TIPOS_LEGIBLES = {
    'barberia': 'Barbería', 'spa_unas': 'Spa de uñas', 'peluqueria': 'Peluquería', 'estetica': 'Estética',
    'consultorio': 'Consultorio', 'gimnasio': 'Gimnasio', 'yoga': 'Yoga', 'masajes': 'Masajes',
    'tattoo': 'Tattoo', 'alquiler_vehiculos': 'Alquiler de vehículos', 'renta_autos': 'Renta de autos',
}


# =============================================================================
# Utilidades
# =============================================================================

def slugify(texto):
    texto = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode('ascii').lower()
    texto = re.sub(r'[^a-z0-9]+', '-', texto).strip('-')
    return re.sub(r'-{2,}', '-', texto)


def slug_corto(nombre):
    """Enlace corto sugerido para un nombre de negocio."""
    completo = slugify(nombre)
    corto = completo
    for generica in _GENERICAS:
        g = slugify(generica)
        if corto.startswith(g + '-'):
            corto = corto[len(g) + 1:]
        elif corto.endswith('-' + g):
            corto = corto[:-(len(g) + 1)]
    if len(corto) < 3:
        corto = completo
    return corto or 'negocio'


def slug_valido(slug):
    return bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])?', slug or '')) and slug not in RESERVADOS


def _conn():
    return db.get_db_connection()


def _hhmm(valor):
    return disponibilidad.normalizar_hhmm(valor)


def hora_12(valor):
    minutos = disponibilidad.a_minutos(valor)
    if minutos is None:
        return str(valor or '')
    h, m = divmod(minutos, 60)
    sufijo = 'a. m.' if h < 12 else 'p. m.'
    h = h % 12 or 12
    return f'{h}:{m:02d} {sufijo}'


def fecha_larga(fecha):
    d = datetime.strptime(str(fecha)[:10], '%Y-%m-%d')
    return f'{DIAS_LARGOS[d.weekday()]} {d.day} de {MESES_LARGOS[d.month - 1]}'


def simbolo_moneda(moneda):
    return {'COP': '$', 'USD': 'US$', 'EUR': '€', 'AWG': 'ƒ'}.get(str(moneda or 'COP').upper(), '$')


def formatear_precio(valor, moneda='COP'):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return ''
    simbolo = simbolo_moneda(moneda)
    if str(moneda or 'COP').upper() == 'COP' or numero == int(numero):
        texto = f'{int(round(numero)):,}'.replace(',', '.')
    else:
        texto = f'{numero:,.2f}'
    return f'{simbolo}{texto}'


def duracion_legible(minutos):
    try:
        minutos = int(minutos or 0)
    except (TypeError, ValueError):
        return ''
    if minutos < 60:
        return f'{minutos} min'
    h, m = divmod(minutos, 60)
    return f'{h} h {m} min' if m else f'{h} h'


def iniciales(nombre):
    partes = [p for p in re.split(r'\s+', str(nombre or '').strip()) if p]
    return (''.join(p[0] for p in partes[:2]) or '?').upper()


def url_publica(url):
    """Fotos guardadas como ruta relativa ('static/...') -> '/static/...'; las absolutas quedan igual."""
    url = (url or '').strip()
    if not url:
        return ''
    if url.startswith(('http://', 'https://', '/', 'data:')):
        return url
    return '/' + url.lstrip('/')


def acento_de(config):
    candidato = (config or {}).get('color_acento') or ''
    acento = candidato if re.fullmatch(r'#[0-9a-fA-F]{6}', str(candidato)) else ACENTO_DEFECTO
    r, g, b = (int(acento[i:i + 2], 16) for i in (1, 3, 5))
    luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return acento, ('#17110a' if luminancia > 0.55 else '#ffffff')


def _serializador():
    return URLSafeSerializer(current_app.secret_key, salt='wabot-cliente')


def token_cliente(telefono, negocio_id):
    return _serializador().dumps({'t': telefono, 'n': int(negocio_id)})


def telefono_desde_token(token, negocio_id):
    if not token:
        return None
    try:
        datos = _serializador().loads(token)
    except BadSignature:
        return None
    if int(datos.get('n', -1)) != int(negocio_id):
        return None
    return datos.get('t')


def telefono_cliente(negocio_id):
    """Teléfono del cliente: token del dispositivo (cabecera o cuerpo) o la sesión de este negocio."""
    token = request.headers.get('X-Cliente-Token') or (request.get_json(silent=True) or {}).get('token') \
        or request.args.get('token')
    telefono = telefono_desde_token(token, negocio_id)
    if telefono:
        return telefono
    if str(session.get('negocio_id')) == str(negocio_id):
        return session.get('cliente_telefono')
    return None


# Límite simple de solicitudes por IP (independiente del de app.py para no crear importaciones circulares)
_solicitudes = defaultdict(list)
_lock_limite = threading.Lock()


def permitir(clave, maximo, ventana):
    ahora = time.time()
    with _lock_limite:
        recientes = [t for t in _solicitudes[clave] if ahora - t < ventana]
        if len(recientes) >= maximo:
            _solicitudes[clave] = recientes
            return False
        recientes.append(ahora)
        _solicitudes[clave] = recientes
        if len(_solicitudes) > 5000:
            for k in [k for k, v in _solicitudes.items() if not v or ahora - v[-1] > ventana]:
                _solicitudes.pop(k, None)
        return True


# =============================================================================
# Enlaces cortos (columna negocios.slug)
# =============================================================================

_slugs_listos = False
_lock_slugs = threading.Lock()


def asegurar_slugs(forzar=False):
    """Crea la columna ``slug`` (si falta) y le asigna un enlace corto a cada negocio que no tenga."""
    global _slugs_listos
    if _slugs_listos and not forzar:
        return
    with _lock_slugs:
        if _slugs_listos and not forzar:
            return
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('ALTER TABLE negocios ADD COLUMN IF NOT EXISTS slug TEXT')
            cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS negocios_slug_unico ON negocios (lower(slug))')
            cur.execute('SELECT id, nombre, slug FROM negocios ORDER BY id')
            filas = cur.fetchall()
            usados = {f['slug'].lower() for f in filas if f['slug']}
            for fila in filas:
                if fila['slug']:
                    continue
                base = slug_corto(fila['nombre'])
                if base in RESERVADOS:
                    base = slugify(fila['nombre']) or 'negocio'
                candidato, n = base, 2
                while candidato in usados or candidato in RESERVADOS:
                    candidato = f'{base}-{n}'
                    n += 1
                cur.execute('UPDATE negocios SET slug = %s WHERE id = %s', (candidato, fila['id']))
                usados.add(candidato)
            conn.commit()
            _slugs_listos = True
        except Exception as e:
            conn.rollback()
            print(f'⚠️ No se pudieron preparar los enlaces cortos: {e}')
        finally:
            conn.close()


def slug_de(negocio_id):
    asegurar_slugs()
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT slug FROM negocios WHERE id = %s', (negocio_id,))
        fila = cur.fetchone()
        return fila['slug'] if fila else None
    finally:
        conn.close()


def cambiar_slug(negocio_id, nuevo):
    """Cambia el enlace corto. Devuelve (ok, mensaje)."""
    nuevo = slugify(nuevo)
    if not slug_valido(nuevo):
        return False, 'Usa entre 3 y 40 letras, números o guiones (y que no sea una palabra reservada).'
    asegurar_slugs()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM negocios WHERE lower(slug) = %s AND id <> %s', (nuevo, negocio_id))
        if cur.fetchone():
            return False, 'Ese enlace ya lo usa otro negocio.'
        cur.execute('UPDATE negocios SET slug = %s WHERE id = %s', (nuevo, negocio_id))
        conn.commit()
        return True, nuevo
    except Exception as e:
        conn.rollback()
        return False, f'No se pudo guardar: {e}'
    finally:
        conn.close()


# =============================================================================
# Lectura de datos públicos
# =============================================================================

def _config(texto):
    if isinstance(texto, dict):
        return texto
    try:
        valor = json.loads(texto or '{}')
        return valor if isinstance(valor, dict) else {}
    except (TypeError, ValueError):
        return {}


def _negocio_desde_fila(fila):
    n = dict(fila)
    config = _config(n.get('configuracion'))
    acento, tinta = acento_de(config)
    tipo = n.get('tipo_negocio') or 'general'
    vocab = VOCABULARIO.get(tipo, VOCAB_DEFECTO)
    pais = localizacion.configuracion_pais(n['id'])
    wa = re.sub(r'\D', '', str(n.get('telefono_whatsapp') or ''))
    if wa and pais.get('prefijo') and not wa.startswith(pais['prefijo']) and len(wa) <= 10:
        wa = pais['prefijo'] + wa
    return {
        'id': n['id'],
        'nombre': (n.get('nombre') or '').strip(),
        'slug': n.get('slug'),
        'tipo': tipo,
        'tipo_legible': TIPOS_LEGIBLES.get(tipo, ''),
        'es_alquiler': tipo in TIPOS_ALQUILER,
        'descripcion': (n.get('descripcion') or config.get('descripcion') or '').strip(),
        'direccion': (n.get('direccion') or '').strip(),
        'latitud': n.get('latitud'),
        'longitud': n.get('longitud'),
        'whatsapp': wa,
        'portada': url_publica(n.get('foto_portada')),
        'logo': url_publica(n.get('foto_perfil')),
        'calificacion': float(n.get('calificacion_promedio') or 0),
        'total_opiniones': int(n.get('total_opiniones') or 0),
        'redes': {k: (n.get(k) or '').strip() for k in ('instagram', 'facebook', 'tiktok', 'sitio_web') if (n.get(k) or '').strip()},
        'acento': acento,
        'acento_tinta': tinta,
        'vocab': vocab,
        'pais': pais,
        'activo': bool(n.get('activo')),
        'iniciales': iniciales(n.get('nombre')),
    }


_COLUMNAS_NEGOCIO = '''id, nombre, slug, tipo_negocio, configuracion, activo, direccion, latitud, longitud, descripcion,
    telefono_whatsapp, foto_portada, foto_perfil, calificacion_promedio, total_opiniones,
    instagram, facebook, tiktok, sitio_web'''


def negocio_por_slug(slug):
    asegurar_slugs()
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f'SELECT {_COLUMNAS_NEGOCIO} FROM negocios WHERE lower(slug) = %s', ((slug or '').lower(),))
        fila = cur.fetchone()
        return _negocio_desde_fila(fila) if fila else None
    finally:
        conn.close()


def negocio_por_id(negocio_id):
    asegurar_slugs()
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f'SELECT {_COLUMNAS_NEGOCIO} FROM negocios WHERE id = %s', (negocio_id,))
        fila = cur.fetchone()
        return _negocio_desde_fila(fila) if fila else None
    finally:
        conn.close()


def negocios_activos():
    asegurar_slugs()
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f'''
            SELECT {_COLUMNAS_NEGOCIO},
                   (SELECT url FROM fotos_negocio f WHERE f.negocio_id = n.id ORDER BY orden, id LIMIT 1) AS primera_foto,
                   (SELECT COUNT(*) FROM profesionales p WHERE p.negocio_id = n.id AND p.activo) AS total_pros,
                   (SELECT COUNT(*) FROM servicios s WHERE s.negocio_id = n.id AND s.activo) AS total_servicios,
                   (SELECT MIN(precio) FROM servicios s WHERE s.negocio_id = n.id AND s.activo AND s.precio > 0) AS desde
            FROM negocios n WHERE n.activo = TRUE ORDER BY n.id
        ''')
        resultado = []
        for fila in cur.fetchall():
            n = _negocio_desde_fila(fila)
            if not n['portada'] and fila.get('primera_foto'):
                n['portada'] = url_publica(fila['primera_foto'])
            n['total_pros'] = fila['total_pros']
            n['total_servicios'] = fila['total_servicios']
            n['desde'] = formatear_precio(fila['desde']) if fila.get('desde') else ''
            # Los negocios de demostración siguen funcionando por su enlace, pero no se listan en el inicio
            if re.search(r'\b(demo|modelo|prueba|test|premium)\b', slugify(n['nombre']).replace('-', ' ')):
                continue
            if n['total_servicios'] or n['es_alquiler']:
                resultado.append(n)
        return resultado
    finally:
        conn.close()


def servicios_de(negocio_id):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT id, nombre, duracion, precio, precio_maximo, tipo_precio, descripcion, foto_url,
                   COALESCE(moneda, 'COP') AS moneda
            FROM servicios WHERE negocio_id = %s AND activo = TRUE
            ORDER BY precio DESC NULLS LAST, nombre
        ''', (negocio_id,))
        servicios = []
        for s in cur.fetchall():
            tipo_precio = str(s.get('tipo_precio') or 'fijo').strip('"').lower()
            precio = formatear_precio(s['precio'], s['moneda'])
            if tipo_precio in ('rango', 'variable') and s.get('precio_maximo'):
                precio_txt = f"{precio} – {formatear_precio(s['precio_maximo'], s['moneda'])}"
            elif tipo_precio in ('desde', 'variable', 'rango'):
                precio_txt = f'Desde {precio}'
            else:
                precio_txt = precio
            servicios.append({
                'id': s['id'],
                'nombre': (s['nombre'] or '').strip(),
                'duracion': int(s['duracion'] or 30),
                'duracion_txt': duracion_legible(s['duracion']),
                'precio': float(s['precio'] or 0),
                'precio_txt': precio_txt if float(s['precio'] or 0) > 0 else 'A convenir',
                'descripcion': (s.get('descripcion') or '').strip(),
                'foto': url_publica(s.get('foto_url')),
                'moneda': s['moneda'],
            })
        return servicios
    finally:
        conn.close()


def profesionales_de(negocio_id):
    """Profesionales activos con su foto, calificación, servicios que hacen ([] = todos) y slug."""
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT p.id, p.nombre, p.especialidad, p.foto_url,
                   COALESCE(p.calificacion_promedio, 0) AS calificacion, COALESCE(p.total_opiniones, 0) AS total_opiniones,
                   (SELECT COALESCE(i.url_publica, i.ruta_archivo) FROM imagenes_profesionales i
                     WHERE i.profesional_id = p.id ORDER BY i.es_principal DESC, i.id DESC LIMIT 1) AS imagen,
                   (SELECT COUNT(*) FROM fotos_trabajo_profesional f WHERE f.profesional_id = p.id) AS total_trabajos,
                   COALESCE((SELECT array_agg(ps.servicio_id) FROM profesional_servicios ps WHERE ps.profesional_id = p.id), '{}') AS servicios
            FROM profesionales p
            WHERE p.negocio_id = %s AND p.activo = TRUE
            ORDER BY p.nombre
        ''', (negocio_id,))
        filas = cur.fetchall()
    finally:
        conn.close()

    usados = set()
    profesionales = []
    for p in filas:
        base = slugify(p['nombre']) or f"p{p['id']}"
        slug = base if base not in usados else f"{base}-{p['id']}"
        usados.add(slug)
        especialidad = (p.get('especialidad') or '').strip()
        if especialidad.lower() in ('general', 'sin especialidad', 'especialista'):
            especialidad = ''
        profesionales.append({
            'id': p['id'],
            'nombre': (p['nombre'] or '').strip(),
            'primer_nombre': (p['nombre'] or '').strip().split(' ')[0],
            'slug': slug,
            'especialidad': especialidad,
            'foto': url_publica(p.get('foto_url') or p.get('imagen')),
            'iniciales': iniciales(p['nombre']),
            'calificacion': float(p['calificacion'] or 0),
            'total_opiniones': int(p['total_opiniones'] or 0),
            'total_trabajos': int(p['total_trabajos'] or 0),
            'servicios': [int(x) for x in (p['servicios'] or [])],
        })
    return profesionales


def hace_servicio(profesional, servicio_id):
    return not profesional['servicios'] or int(servicio_id) in profesional['servicios']


def horario_semana(negocio_id):
    """Los 7 días (lunes a domingo) con su horario legible y el resumen 'abierto ahora'."""
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''SELECT dia_semana, activo, hora_inicio, hora_fin, almuerzo_inicio, almuerzo_fin
                       FROM configuracion_horarios WHERE negocio_id = %s''', (negocio_id,))
        por_dia = {int(f['dia_semana']): f for f in cur.fetchall()}
    finally:
        conn.close()
    ahora = localizacion.ahora_en(negocio_id)
    hoy = ahora.isoweekday()
    dias = []
    for d in range(1, 8):
        f = por_dia.get(d)
        abierto = bool(f and f['activo'])
        dias.append({
            'dia': DIAS_LARGOS[d - 1],
            'corto': DIAS_CORTOS[d - 1],
            'abierto': abierto,
            'texto': f"{hora_12(f['hora_inicio'])} – {hora_12(f['hora_fin'])}" if abierto else 'Cerrado',
            'hoy': d == hoy,
            'inicio': _hhmm(f['hora_inicio']) if abierto else None,
            'fin': _hhmm(f['hora_fin']) if abierto else None,
        })
    estado = {'abierto': False, 'texto': 'Cerrado hoy'}
    h = dias[hoy - 1]
    if h['abierto']:
        minutos = ahora.hour * 60 + ahora.minute
        ini, fin = disponibilidad.a_minutos(h['inicio']), disponibilidad.a_minutos(h['fin'])
        if ini is not None and fin is not None:
            if ini <= minutos < fin:
                estado = {'abierto': True, 'texto': f"Abierto · cierra a las {hora_12(h['fin'])}"}
            elif minutos < ini:
                estado = {'abierto': False, 'texto': f"Cerrado · abre a las {hora_12(h['inicio'])}"}
            else:
                estado = {'abierto': False, 'texto': 'Cerrado por hoy'}
    return dias, estado


def galeria_de(negocio_id, limite=12):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT url, descripcion FROM fotos_negocio WHERE negocio_id = %s ORDER BY orden, id LIMIT %s',
                    (negocio_id, limite))
        fotos = [{'url': url_publica(f['url']), 'texto': f.get('descripcion') or ''} for f in cur.fetchall()]
        cur.execute('''
            SELECT f.url, f.descripcion, p.nombre FROM fotos_trabajo_profesional f
            JOIN profesionales p ON p.id = f.profesional_id
            WHERE p.negocio_id = %s AND p.activo ORDER BY f.fecha_subida DESC NULLS LAST, f.id DESC LIMIT %s
        ''', (negocio_id, limite))
        trabajos = [{'url': url_publica(f['url']), 'texto': f.get('descripcion') or '', 'autor': f['nombre']}
                    for f in cur.fetchall()]
        return fotos, trabajos
    finally:
        conn.close()


def trabajos_de(profesional_id, limite=30):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''SELECT url, descripcion FROM fotos_trabajo_profesional WHERE profesional_id = %s
                       ORDER BY fecha_subida DESC NULLS LAST, id DESC LIMIT %s''', (profesional_id, limite))
        return [{'url': url_publica(f['url']), 'texto': f.get('descripcion') or ''} for f in cur.fetchall()]
    finally:
        conn.close()


def opiniones_de(negocio_id=None, profesional_id=None, limite=6):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if profesional_id:
            cur.execute('''SELECT o.calificacion, o.comentario, o.fecha, c.nombre FROM opiniones_profesional o
                           LEFT JOIN clientes c ON c.id = o.cliente_id
                           WHERE o.profesional_id = %s AND COALESCE(o.comentario, '') <> ''
                           ORDER BY o.fecha DESC LIMIT %s''', (profesional_id, limite))
        else:
            cur.execute('''SELECT o.calificacion, o.comentario, o.fecha, c.nombre FROM opiniones_negocio o
                           LEFT JOIN clientes c ON c.id = o.cliente_id
                           WHERE o.negocio_id = %s AND COALESCE(o.comentario, '') <> ''
                           ORDER BY o.fecha DESC LIMIT %s''', (negocio_id, limite))
        return [{'estrellas': int(o['calificacion'] or 0), 'texto': o['comentario'].strip(),
                 'autor': (o.get('nombre') or 'Cliente').strip().split(' ')[0].title()} for o in cur.fetchall()]
    except Exception:
        conn.rollback()
        return []
    finally:
        conn.close()


def promociones_activas(negocio_id):
    """Promociones de descuento vigentes (los concursos de fotos ya no se muestran al cliente)."""
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        hoy = localizacion.ahora_en(negocio_id).date()
        cur.execute('''SELECT titulo, descripcion, descuento_porcentaje, imagen_url FROM promociones
                       WHERE negocio_id = %s AND activo AND COALESCE(tipo_promocion, '') <> 'concurso_fotos'
                         AND (fecha_inicio IS NULL OR fecha_inicio <= %s) AND (fecha_fin IS NULL OR fecha_fin >= %s)
                       ORDER BY id DESC LIMIT 3''', (negocio_id, hoy, hoy))
        return [dict(f) for f in cur.fetchall()]
    except Exception:
        conn.rollback()
        return []
    finally:
        conn.close()


# =============================================================================
# Disponibilidad
# =============================================================================

def dias_abiertos(negocio_id, dias=DIAS_RESERVA):
    semana, _ = horario_semana(negocio_id)
    hoy = localizacion.ahora_en(negocio_id).date()
    resultado = []
    for i in range(dias):
        d = hoy + timedelta(days=i)
        resultado.append({
            'fecha': d.isoformat(),
            'dia': 'Hoy' if i == 0 else ('Mañana' if i == 1 else DIAS_CORTOS[d.weekday()]),
            'num': d.day,
            'mes': MESES_CORTOS[d.month - 1],
            'abierto': semana[d.weekday()]['abierto'],
        })
    return resultado


def horarios_para(negocio_id, servicio, profesionales, fecha, profesional_id=None):
    """{'HH:MM': [ids de profesionales libres]} para el servicio en esa fecha."""
    candidatos = [p for p in profesionales if hace_servicio(p, servicio['id'])
                  and (not profesional_id or p['id'] == int(profesional_id))]
    libres = defaultdict(list)
    for p in candidatos:
        for hora in disponibilidad.horarios_libres(negocio_id, p['id'], fecha, duracion=servicio['duracion']):
            libres[hora].append(p['id'])
    return dict(sorted(libres.items(), key=lambda kv: disponibilidad.a_minutos(kv[0])))


def _carga_del_dia(profesional_ids, fecha):
    """Citas activas de cada profesional en la fecha (para repartir el trabajo cuando el cliente dice 'cualquiera')."""
    if not profesional_ids:
        return {}
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''SELECT profesional_id, COUNT(*) AS n FROM citas
                       WHERE profesional_id = ANY(%s) AND fecha = %s AND estado NOT IN ('cancelado', 'cancelada')
                       GROUP BY profesional_id''', (list(profesional_ids), str(fecha)))
        return {f['profesional_id']: f['n'] for f in cur.fetchall()}
    finally:
        conn.close()


# =============================================================================
# Páginas
# =============================================================================

def _contexto_negocio(negocio):
    return {'negocio': negocio, 'acento': negocio['acento'], 'acento_tinta': negocio['acento_tinta']}


def _en_panel():
    return session.get('usuario_rol') in ('superadmin', 'propietario', 'profesional')


@bp.route('/')
def inicio():
    negocios = negocios_activos()
    return render_template('publico/inicio.html', negocios=negocios, en_panel=_en_panel(),
                           acento=ACENTO_DEFECTO, acento_tinta='#17110a')


def _datos_reserva(negocio, servicios, profesionales):
    """Lo mínimo que necesita el formulario de reserva en el navegador."""
    return {
        'negocio': {'id': negocio['id'], 'nombre': negocio['nombre'], 'slug': negocio['slug'],
                    'direccion': negocio['direccion'], 'whatsapp': negocio['whatsapp'],
                    'pro': negocio['vocab']['pro'], 'pros': negocio['vocab']['pros'],
                    'tel_ejemplo': negocio['pais']['ejemplo'], 'tel_digitos': negocio['pais']['digitos'],
                    'tel_prefijo': negocio['pais'].get('prefijo') or ''},
        'servicios': [{k: s[k] for k in ('id', 'nombre', 'duracion', 'duracion_txt', 'precio_txt', 'descripcion')}
                      for s in servicios],
        'profesionales': [{k: p[k] for k in ('id', 'nombre', 'primer_nombre', 'especialidad', 'foto', 'iniciales',
                                             'calificacion', 'servicios')} for p in profesionales],
    }


@bp.route('/<slug>')
def perfil_negocio(slug):
    if slug.lower() in RESERVADOS:
        abort(404)
    negocio = negocio_por_slug(slug)
    if not negocio:
        abort(404)
    if slug != negocio['slug']:
        return redirect(url_for('publico.perfil_negocio', slug=negocio['slug']), 301)
    if not negocio['activo']:
        return render_template('publico/no_disponible.html', **_contexto_negocio(negocio)), 404
    if negocio['es_alquiler']:
        # Los negocios de alquiler conservan su propio flujo (solicitud por días)
        return redirect(f"/cliente/{negocio['id']}?v=chat")

    servicios = servicios_de(negocio['id'])
    profesionales = profesionales_de(negocio['id'])
    semana, estado = horario_semana(negocio['id'])
    fotos, trabajos = galeria_de(negocio['id'])
    if not negocio['portada'] and fotos:
        negocio['portada'] = fotos[0]['url']
    return render_template(
        'publico/negocio.html',
        servicios=servicios, profesionales=profesionales, semana=semana, estado=estado,
        fotos=fotos, trabajos=trabajos, opiniones=opiniones_de(negocio_id=negocio['id']),
        promociones=promociones_activas(negocio['id']),
        datos=_datos_reserva(negocio, servicios, profesionales),
        preseleccion={'servicio': request.args.get('servicio', type=int), 'profesional': request.args.get('con', type=int)},
        **_contexto_negocio(negocio))


@bp.route('/<slug>/<pro_slug>')
def perfil_profesional(slug, pro_slug):
    if slug.lower() in RESERVADOS:
        abort(404)
    negocio = negocio_por_slug(slug)
    if not negocio or not negocio['activo'] or negocio['es_alquiler']:
        abort(404)
    if pro_slug == 'mis-citas':
        return render_template('publico/mis_citas.html', datos=_datos_reserva(negocio, [], []),
                               **_contexto_negocio(negocio))
    profesionales = profesionales_de(negocio['id'])
    pro = next((p for p in profesionales if p['slug'] == pro_slug or str(p['id']) == pro_slug), None)
    if not pro:
        abort(404)
    servicios = servicios_de(negocio['id'])
    suyos = [s for s in servicios if hace_servicio(pro, s['id'])]
    fotos, _ = galeria_de(negocio['id'], limite=1)
    if not negocio['portada'] and fotos:
        negocio['portada'] = fotos[0]['url']
    return render_template(
        'publico/profesional.html', pro=pro, servicios=suyos, trabajos=trabajos_de(pro['id']),
        opiniones=opiniones_de(profesional_id=pro['id']),
        companeros=[p for p in profesionales if p['id'] != pro['id']],
        datos=_datos_reserva(negocio, servicios, profesionales),
        preseleccion={'servicio': None, 'profesional': pro['id']},
        **_contexto_negocio(negocio))


# =============================================================================
# API de reserva
# =============================================================================

def _negocio_api(negocio_id):
    negocio = negocio_por_id(negocio_id)
    if not negocio or not negocio['activo']:
        respuesta = jsonify({'ok': False, 'error': 'Negocio no disponible'})
        respuesta.status_code = 404
        abort(respuesta)
    return negocio


@bp.route('/api/reserva/<int:negocio_id>/dias')
def api_dias(negocio_id):
    _negocio_api(negocio_id)
    return jsonify({'ok': True, 'dias': dias_abiertos(negocio_id)})


@bp.route('/api/reserva/<int:negocio_id>/horarios')
def api_horarios(negocio_id):
    _negocio_api(negocio_id)
    servicio_id = request.args.get('servicio_id', type=int)
    fecha = (request.args.get('fecha') or '')[:10]
    profesional_id = request.args.get('profesional_id', type=int)
    servicio = next((s for s in servicios_de(negocio_id) if s['id'] == servicio_id), None)
    if not servicio:
        return jsonify({'ok': False, 'error': 'Elige un servicio'}), 400
    try:
        datetime.strptime(fecha, '%Y-%m-%d')
    except ValueError:
        return jsonify({'ok': False, 'error': 'Fecha inválida'}), 400
    profesionales = profesionales_de(negocio_id)
    libres = horarios_para(negocio_id, servicio, profesionales, fecha, profesional_id)
    respuesta = {'ok': True, 'fecha': fecha, 'fecha_txt': fecha_larga(fecha),
                 'horarios': [{'hora': h, 'txt': hora_12(h), 'pros': ids} for h, ids in libres.items()]}
    if not libres:
        # Sugerir el siguiente día con espacio, para que el cliente no tenga que adivinar
        base = datetime.strptime(fecha, '%Y-%m-%d').date()
        for d in dias_abiertos(negocio_id):
            if d['fecha'] <= fecha or not d['abierto']:
                continue
            otros = horarios_para(negocio_id, servicio, profesionales, d['fecha'], profesional_id)
            if otros:
                primera = next(iter(otros))
                respuesta['siguiente'] = {'fecha': d['fecha'], 'hora': primera, 'txt': f"{fecha_larga(d['fecha'])} · {hora_12(primera)}"}
                break
            if (datetime.strptime(d['fecha'], '%Y-%m-%d').date() - base).days > 14:
                break
    return jsonify(respuesta)


def _guardar_cliente(negocio_id, telefono, nombre):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT id FROM clientes WHERE negocio_id = %s AND telefono = %s ORDER BY id LIMIT 1',
                    (negocio_id, telefono))
        fila = cur.fetchone()
        ahora = datetime.now().isoformat(timespec='seconds')
        if fila:
            cur.execute('UPDATE clientes SET nombre = %s, updated_at = %s WHERE id = %s', (nombre, ahora, fila['id']))
        else:
            cur.execute('INSERT INTO clientes (negocio_id, telefono, nombre, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)',
                        (negocio_id, telefono, nombre, ahora, ahora))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'⚠️ No se pudo guardar el cliente: {e}')
    finally:
        conn.close()


def _avisar_profesional(profesional_id, titulo, mensaje, cita_id):
    try:
        from push_notifications import enviar_push_profesional
        enviar_push_profesional(profesional_id, titulo, mensaje, cita_id=cita_id)
    except Exception as e:
        print(f'⚠️ No se pudo avisar al profesional {profesional_id}: {type(e).__name__}: {e}')


def _avisar_duenos(negocio_id, titulo, mensaje):
    try:
        from push_notifications import enviar_push_propietarios
        enviar_push_propietarios(negocio_id, titulo, mensaje, url='/agenda')
    except Exception as e:
        print(f'⚠️ No se pudo avisar a los dueños: {type(e).__name__}: {e}')


def _enlace_google(negocio, servicio_nombre, pro_nombre, fecha, hora, duracion):
    inicio = datetime.strptime(f'{fecha} {hora}', '%Y-%m-%d %H:%M')
    fin = inicio + timedelta(minutes=int(duracion or 30))
    from urllib.parse import urlencode
    return 'https://calendar.google.com/calendar/render?' + urlencode({
        'action': 'TEMPLATE',
        'text': f"{servicio_nombre} · {negocio['nombre']}",
        'dates': f"{inicio:%Y%m%dT%H%M%S}/{fin:%Y%m%dT%H%M%S}",
        'ctz': negocio['pais']['zona'],
        'details': f'Con {pro_nombre}. Reservado con Wabot.',
        'location': negocio['direccion'] or negocio['nombre'],
    })


@bp.route('/api/reserva/<int:negocio_id>', methods=['POST'])
def api_reservar(negocio_id):
    negocio = _negocio_api(negocio_id)
    if not permitir(f'reserva:{request.remote_addr}', 15, 600):
        return jsonify({'ok': False, 'error': 'Demasiados intentos. Espera unos minutos.'}), 429
    datos = request.get_json(silent=True) or {}
    nombre = re.sub(r'\s+', ' ', str(datos.get('nombre') or '')).strip()[:60]
    telefono = localizacion.normalizar_telefono(str(datos.get('telefono') or ''), negocio_id)
    fecha = str(datos.get('fecha') or '')[:10]
    hora = _hhmm(datos.get('hora'))
    try:
        servicio_id = int(datos.get('servicio_id'))
        profesional_id = int(datos['profesional_id']) if datos.get('profesional_id') else None
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Datos incompletos'}), 400

    if len(nombre) < 2:
        return jsonify({'ok': False, 'campo': 'nombre', 'error': 'Escribe tu nombre'}), 400
    if not telefono:
        pais = negocio['pais']
        return jsonify({'ok': False, 'campo': 'telefono',
                        'error': f"Número inválido: usa {pais['digitos']} dígitos (ej. {pais['ejemplo']})"}), 400
    servicio = next((s for s in servicios_de(negocio_id) if s['id'] == servicio_id), None)
    if not servicio or not hora:
        return jsonify({'ok': False, 'error': 'Datos incompletos'}), 400
    try:
        fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'ok': False, 'error': 'Fecha inválida'}), 400
    hoy = localizacion.ahora_en(negocio_id).date()
    if fecha_dt < hoy or (fecha_dt - hoy).days > 60:
        return jsonify({'ok': False, 'error': 'Elige una fecha dentro de los próximos días'}), 400

    profesionales = profesionales_de(negocio_id)
    localizacion.fijar_negocio(negocio_id)
    libres = horarios_para(negocio_id, servicio, profesionales, fecha, profesional_id)
    candidatos = libres.get(hora, [])
    if not candidatos:
        return jsonify({'ok': False, 'ocupado': True, 'error': 'Ese horario se acaba de ocupar. Elige otro.'}), 409
    if not profesional_id:
        carga = _carga_del_dia(candidatos, fecha)
        candidatos = sorted(candidatos, key=lambda pid: (carga.get(pid, 0), pid))

    cita_id, elegido = 0, None
    for pid in candidatos:
        cita_id = db.agregar_cita(negocio_id, pid, telefono, fecha, hora, servicio_id, nombre.title())
        if cita_id:
            elegido = next(p for p in profesionales if p['id'] == pid)
            break
    if not cita_id:
        return jsonify({'ok': False, 'ocupado': True, 'error': 'Ese horario se acaba de ocupar. Elige otro.'}), 409

    nombre = nombre.title()
    _guardar_cliente(negocio_id, telefono, nombre)
    fecha_txt = fecha_larga(fecha)
    _avisar_profesional(elegido['id'], 'Nueva cita',
                        f"{nombre} · {servicio['nombre']} · {DIAS_CORTOS[fecha_dt.weekday()]} {fecha_dt.day} a las {hora_12(hora)}",
                        cita_id)

    _avisar_duenos(negocio_id, 'Nueva reserva',
                   f"{nombre} con {elegido['primer_nombre']} · {servicio['nombre']} · {DIAS_CORTOS[fecha_dt.weekday()]} {fecha_dt.day} a las {hora_12(hora)}")

    session['cliente_telefono'] = telefono
    session['cliente_nombre'] = nombre
    session['negocio_id'] = negocio_id
    return jsonify({
        'ok': True,
        'token': token_cliente(telefono, negocio_id),
        'cliente': {'nombre': nombre, 'telefono': telefono},
        'cita': {
            'id': cita_id, 'fecha': fecha, 'hora': hora, 'fecha_txt': fecha_txt, 'hora_txt': hora_12(hora),
            'servicio': servicio['nombre'], 'precio_txt': servicio['precio_txt'], 'duracion': servicio['duracion'],
            'duracion_txt': servicio['duracion_txt'],
            'profesional': elegido['nombre'], 'profesional_foto': elegido['foto'], 'profesional_iniciales': elegido['iniciales'],
            'google': _enlace_google(negocio, servicio['nombre'], elegido['nombre'], fecha, hora, servicio['duracion']),
        },
    })


def citas_del_cliente(negocio_id, telefono):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT c.id, c.fecha, c.hora, c.estado, s.nombre AS servicio, s.precio, COALESCE(s.moneda, 'COP') AS moneda,
                   COALESCE(c.duracion_minutos, s.duracion) AS duracion, p.nombre AS profesional, p.id AS profesional_id,
                   p.foto_url
            FROM citas c JOIN servicios s ON s.id = c.servicio_id JOIN profesionales p ON p.id = c.profesional_id
            WHERE c.negocio_id = %s AND c.cliente_telefono = %s
            ORDER BY c.fecha DESC, c.hora DESC LIMIT 40
        ''', (negocio_id, telefono))
        filas = cur.fetchall()
    finally:
        conn.close()
    ahora = localizacion.ahora_en(negocio_id).replace(tzinfo=None)
    proximas, anteriores = [], []
    for c in filas:
        fecha, hora = str(c['fecha'])[:10], _hhmm(c['hora']) or '00:00'
        try:
            inicio = datetime.strptime(f'{fecha} {hora}', '%Y-%m-%d %H:%M')
        except ValueError:
            continue
        estado = (c['estado'] or 'confirmado').lower()
        activa = estado in ('confirmado', 'confirmada', 'pendiente')
        item = {
            'id': c['id'], 'fecha': fecha, 'hora': hora, 'fecha_txt': fecha_larga(fecha), 'hora_txt': hora_12(hora),
            'servicio': c['servicio'], 'precio_txt': formatear_precio(c['precio'], c['moneda']),
            'profesional': c['profesional'], 'profesional_id': c['profesional_id'], 'foto': url_publica(c['foto_url']),
            'iniciales': iniciales(c['profesional']),
            'estado': 'cancelada' if estado.startswith('cancel') else ('completada' if estado.startswith('complet') else
                                                                         ('confirmada' if activa else estado)),
        }
        if activa and inicio >= ahora - timedelta(minutes=30):
            item['puede_cancelar'] = inicio > ahora
            proximas.append(item)
        else:
            anteriores.append(item)
    proximas.sort(key=lambda x: (x['fecha'], x['hora']))
    return proximas, anteriores[:12]


@bp.route('/api/reserva/<int:negocio_id>/mis-citas')
def api_mis_citas(negocio_id):
    _negocio_api(negocio_id)
    telefono = telefono_cliente(negocio_id)
    if not telefono:
        return jsonify({'ok': False, 'error': 'Sin identificar'}), 401
    proximas, anteriores = citas_del_cliente(negocio_id, telefono)
    return jsonify({'ok': True, 'proximas': proximas, 'anteriores': anteriores})


@bp.route('/api/reserva/<int:negocio_id>/citas/<int:cita_id>/cancelar', methods=['POST'])
def api_cancelar(negocio_id, cita_id):
    _negocio_api(negocio_id)
    telefono = telefono_cliente(negocio_id)
    if not telefono:
        return jsonify({'ok': False, 'error': 'Sin identificar'}), 401
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''UPDATE citas SET estado = 'cancelado'
                       WHERE id = %s AND negocio_id = %s AND cliente_telefono = %s AND estado IN ('confirmado', 'confirmada', 'pendiente')
                       RETURNING profesional_id, cliente_nombre, fecha, hora''', (cita_id, negocio_id, telefono))
        fila = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if not fila:
        return jsonify({'ok': False, 'error': 'No encontramos esa cita activa'}), 404
    fecha = str(fila['fecha'])[:10]
    d = datetime.strptime(fecha, '%Y-%m-%d')
    _avisar_profesional(fila['profesional_id'], 'Cita cancelada',
                        f"{fila['cliente_nombre'] or 'Un cliente'} canceló · {DIAS_CORTOS[d.weekday()]} {d.day} a las {hora_12(fila['hora'])}",
                        cita_id)
    _avisar_duenos(negocio_id, 'Cita cancelada',
                   f"{fila['cliente_nombre'] or 'Un cliente'} canceló · {DIAS_CORTOS[d.weekday()]} {d.day} a las {hora_12(fila['hora'])}")
    return jsonify({'ok': True})


@bp.route('/api/reserva/<int:negocio_id>/push', methods=['POST'])
def api_push_cliente(negocio_id):
    _negocio_api(negocio_id)
    telefono = telefono_cliente(negocio_id)
    datos = request.get_json(silent=True) or {}
    suscripcion = datos.get('subscription')
    if not telefono:
        return jsonify({'ok': False, 'error': 'Sin identificar'}), 401
    if not isinstance(suscripcion, dict) or not suscripcion.get('endpoint'):
        return jsonify({'ok': False, 'error': 'Suscripción inválida'}), 400
    from push_notifications import guardar_suscripcion_cliente
    ok = guardar_suscripcion_cliente(telefono, negocio_id, suscripcion, request.headers.get('User-Agent', '')[:500])
    return jsonify({'ok': bool(ok)})


# =============================================================================
# Asistente de preguntas
# =============================================================================

@bp.route('/api/reserva/<int:negocio_id>/preguntar', methods=['POST'])
def api_preguntar(negocio_id):
    negocio = _negocio_api(negocio_id)
    if not permitir(f'preguntar:{request.remote_addr}', 30, 600):
        return jsonify({'ok': False, 'respuesta': 'Hiciste muchas preguntas seguidas. Espera un momento, por favor.'}), 429
    datos = request.get_json(silent=True) or {}
    mensajes = [m for m in (datos.get('mensajes') or []) if isinstance(m, dict)][-10:]
    import asistente
    resultado = asistente.responder(negocio, mensajes)
    return jsonify({'ok': True, **resultado})


@bp.app_template_filter('json_seguro')
def json_seguro(valor):
    """JSON para incrustar en <script>: escapa '<', '>' y '&' para que un nombre no pueda cerrar la etiqueta."""
    from markupsafe import Markup
    texto = json.dumps(valor, ensure_ascii=False, default=str)
    return Markup(texto.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


# =============================================================================
# Panel del negocio: su enlace de reservas (QR y cambio de enlace)
# =============================================================================

def _negocio_del_panel():
    if session.get('usuario_rol') not in ('propietario', 'superadmin') or not session.get('negocio_id'):
        abort(403)
    return int(session['negocio_id'])


@bp.route('/negocio/enlace/qr.png')
def qr_enlace():
    negocio_id = _negocio_del_panel()
    import io
    import qrcode
    from flask import send_file
    url = request.host_url.rstrip('/') + '/' + (slug_de(negocio_id) or '')
    qr = qrcode.QRCode(border=2, box_size=12, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(buffer, format='PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png', download_name=f'qr-{slug_de(negocio_id)}.png',
                     as_attachment=request.args.get('descargar') == '1')


@bp.route('/negocio/enlace', methods=['POST'])
def cambiar_enlace():
    from flask import flash
    negocio_id = _negocio_del_panel()
    token = request.form.get('csrf_token', '')
    if not token or token != session.get('csrf_token'):
        flash('Error de seguridad. Intenta de nuevo.', 'error')
        return redirect(request.referrer or '/negocio')
    ok, resultado = cambiar_slug(negocio_id, request.form.get('slug', ''))
    flash(f'Tu enlace ahora es /{resultado}' if ok else resultado, 'success' if ok else 'error')
    return redirect(request.referrer or '/negocio')


@bp.app_context_processor
def enlace_del_negocio():
    """'enlace_publico' disponible en las plantillas del panel (perfil con reserva del negocio en sesión)."""
    def enlace_publico():
        negocio_id = session.get('negocio_id')
        if not negocio_id or session.get('usuario_rol') not in ('propietario', 'superadmin', 'profesional'):
            return None
        try:
            slug = slug_de(negocio_id)
        except Exception:
            return None
        return {'slug': slug, 'url': request.host_url.rstrip('/') + '/' + slug, 'ruta': '/' + slug} if slug else None
    return {'enlace_publico': enlace_publico}


@bp.route('/profesional/<int:profesional_id>/publico')
def perfil_profesional_antiguo(profesional_id):
    """Enlace antiguo del directorio al perfil de un profesional -> /<enlace>/<profesional>."""
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT negocio_id FROM profesionales WHERE id = %s', (profesional_id,))
        fila = cur.fetchone()
    finally:
        conn.close()
    if not fila:
        abort(404)
    slug = slug_de(fila['negocio_id'])
    pro = next((p for p in profesionales_de(fila['negocio_id']) if p['id'] == profesional_id), None)
    return redirect(f"/{slug}/{pro['slug']}" if pro else f'/{slug}', 301)


@bp.route('/directorio')
def directorio_antiguo():
    return redirect('/', 301)
