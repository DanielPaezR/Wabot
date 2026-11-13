# localizacion.py - Zona horaria y formato de teléfono por negocio (país).
#
# Los negocios existentes no tienen país configurado y se comportan como
# Colombia (America/Bogota, celular de 10 dígitos que empieza con 3).
import re
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone, tzinfo

import pytz

PAIS_DEFECTO = 'CO'
ZONA_DEFECTO = 'America/Bogota'

PAISES = {
    'CO': {
        'nombre': 'Colombia',
        'zona': 'America/Bogota',
        'prefijo': '57',
        'regex': r'3\d{9}',
        'digitos': '10',
        'ejemplo': '3101234567',
    },
    'AW': {
        'nombre': 'Aruba',
        'zona': 'America/Aruba',
        'prefijo': '297',
        'regex': r'[2-9]\d{6}',
        'digitos': '7',
        'ejemplo': '5601234',
    },
    'OTRO': {
        'nombre': 'Otro país',
        'zona': ZONA_DEFECTO,
        'prefijo': None,
        'regex': r'\d{7,15}',
        'digitos': '7 a 15',
        'ejemplo': '12345678',
    },
}

_CACHE_TTL_SEGUNDOS = 120
_cache = {}
_negocio_actual = ContextVar('negocio_actual', default=None)


def _config_por_defecto():
    return PAIS_DEFECTO, ZONA_DEFECTO


def _consultar_bd(negocio_id):
    import database as db

    conn = db.get_db_connection()
    try:
        fila = db.fetch_one(
            conn.cursor(),
            'SELECT pais, zona_horaria FROM negocios WHERE id = ?',
            (negocio_id,),
        )
    finally:
        conn.close()
    return fila


def _resolver(fila):
    """(pais, zona) a partir de una fila con las columnas pais y zona_horaria."""
    pais, zona = _config_por_defecto()
    pais_bd = (fila.get('pais') or '').strip().upper()
    zona_bd = (fila.get('zona_horaria') or '').strip()
    if pais_bd in PAISES:
        pais = pais_bd
        zona = PAISES[pais]['zona']
    if zona_bd in pytz.all_timezones_set:
        zona = zona_bd
    return pais, zona


def negocios_por_zona():
    """{zona_horaria: [negocio_id, ...]} para tareas programadas."""
    import database as db

    agrupados = {}
    conn = db.get_db_connection()
    try:
        filas = db.fetch_all(conn.cursor(), 'SELECT id, pais, zona_horaria FROM negocios WHERE activo = TRUE')
    except Exception as e:
        print(f"⚠️ [LOCALIZACION] No se pudieron agrupar negocios por zona: {e}")
        return {}
    finally:
        conn.close()
    for fila in filas:
        fila = dict(fila)
        _, zona = _resolver(fila)
        agrupados.setdefault(zona, []).append(fila['id'])
    return agrupados


def _pais_y_zona(negocio_id):
    if not negocio_id:
        return _config_por_defecto()

    ahora = time.time()
    entrada = _cache.get(negocio_id)
    if entrada and entrada[0] > ahora:
        return entrada[1], entrada[2]

    pais, zona = _config_por_defecto()
    ttl = _CACHE_TTL_SEGUNDOS
    try:
        fila = _consultar_bd(negocio_id)
        if fila:
            pais, zona = _resolver(fila)
    except Exception as e:
        print(f"⚠️ [LOCALIZACION] No se pudo leer la configuración del negocio {negocio_id}: {e}")
        ttl = 15

    _cache[negocio_id] = (ahora + ttl, pais, zona)
    return pais, zona


def invalidar(negocio_id=None):
    if negocio_id is None:
        _cache.clear()
    else:
        _cache.pop(_a_entero(negocio_id), None)


def _a_entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def configuracion_pais(negocio_id=None):
    """Datos del país del negocio (teléfono, zona). Sin negocio => Colombia."""
    negocio_id = _a_entero(negocio_id) if negocio_id is not None else _negocio_actual.get()
    pais, zona = _pais_y_zona(negocio_id)
    config = dict(PAISES[pais])
    config['codigo'] = pais
    config['zona'] = zona
    return config


def zona_de(negocio_id=None):
    return pytz.timezone(configuracion_pais(negocio_id)['zona'])


def ahora_en(negocio_id=None):
    return datetime.now(zona_de(negocio_id))


def validar(pais, zona_horaria=None):
    """Devuelve (ok, mensaje, pais, zona) con los valores normalizados."""
    pais = (pais or PAIS_DEFECTO).strip().upper()
    if pais not in PAISES:
        return False, f'País no soportado: {pais}', pais, None
    zona_horaria = (zona_horaria or '').strip() or PAISES[pais]['zona']
    if zona_horaria not in pytz.all_timezones_set:
        return False, f'Zona horaria inválida: {zona_horaria}', pais, zona_horaria
    return True, 'ok', pais, zona_horaria


def guardar(negocio_id, pais, zona_horaria=None):
    """Guarda país y zona horaria de un negocio. Devuelve (ok, mensaje)."""
    ok, mensaje, pais, zona_horaria = validar(pais, zona_horaria)
    if not ok:
        return False, mensaje

    import database as db

    conn = db.get_db_connection()
    try:
        cursor = conn.cursor()
        db.execute_sql(
            cursor,
            'UPDATE negocios SET pais = ?, zona_horaria = ? WHERE id = ?',
            (pais, zona_horaria, negocio_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
    invalidar(negocio_id)
    return True, 'ok'


def obtener(negocio_id):
    config = configuracion_pais(negocio_id)
    return {'pais': config['codigo'], 'zona_horaria': config['zona']}


# ---------------------------------------------------------------------------
# Contexto: el negocio que se está atendiendo en la solicitud actual
# ---------------------------------------------------------------------------

def fijar_negocio(negocio_id):
    _negocio_actual.set(_a_entero(negocio_id))


def limpiar_negocio():
    _negocio_actual.set(None)


class ZonaNegocio(tzinfo):
    """tzinfo que usa la zona horaria del negocio de la solicitud actual."""

    def _zona(self):
        return zona_de(_negocio_actual.get())

    def utcoffset(self, dt):
        referencia = dt.replace(tzinfo=None) if dt is not None else datetime(2000, 1, 1)
        return self._zona().utcoffset(referencia, is_dst=False)

    def dst(self, dt):
        referencia = dt.replace(tzinfo=None) if dt is not None else datetime(2000, 1, 1)
        return self._zona().dst(referencia, is_dst=False)

    def tzname(self, dt):
        referencia = dt.replace(tzinfo=None) if dt is not None else datetime(2000, 1, 1)
        return self._zona().tzname(referencia, is_dst=False)

    def fromutc(self, dt):
        local = dt.replace(tzinfo=timezone.utc).astimezone(self._zona())
        return local.replace(tzinfo=self)

    def localize(self, dt, is_dst=False):
        return dt.replace(tzinfo=self)

    def __repr__(self):
        return '<ZonaNegocio>'


# Hora local del negocio de la solicitud actual (Colombia si no hay negocio).
tz_negocio = ZonaNegocio()
# Reloj fijo para marcas de tiempo internas (expiración de conversaciones).
tz_reloj = pytz.timezone(ZONA_DEFECTO)


# ---------------------------------------------------------------------------
# Teléfonos
# ---------------------------------------------------------------------------

def normalizar_telefono(texto, negocio_id=None, permisivo=False):
    """Devuelve el teléfono local (solo dígitos) o None si no es válido.

    Con permisivo=True (números que ya vienen identificados por WhatsApp, p. ej.
    turistas con número extranjero) se acepta cualquier número de 7 a 15 dígitos.
    """
    config = configuracion_pais(negocio_id)
    digitos = re.sub(r'\D', '', texto or '')
    if digitos.startswith('00'):
        digitos = digitos[2:]

    patron = re.compile(r'^' + config['regex'] + r'$')
    if patron.match(digitos):
        return digitos

    prefijo = config['prefijo']
    if prefijo and digitos.startswith(prefijo) and patron.match(digitos[len(prefijo):]):
        return digitos[len(prefijo):]
    if permisivo and re.match(r'^\d{7,15}$', digitos):
        return digitos
    return None


def adaptar_texto_telefono(texto, negocio_id=None):
    """Cambia las instrucciones de teléfono colombianas por las del país del negocio."""
    config = configuracion_pais(negocio_id)
    if config['codigo'] == 'CO' or not texto:
        return texto

    texto = re.sub(
        r'\s*\((?:debe empezar con 3,?\s*)?ej(?:emplo|\.)?:\s*3101234567\)',
        f" (ejemplo: {config['ejemplo']})",
        texto,
    )
    texto = texto.replace('3101234567', config['ejemplo'])
    return re.sub(r'\b10 d[ií]gitos\b', f"{config['digitos']} dígitos", texto)
