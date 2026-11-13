"""Monitoreo de la aplicación: estado de salud, latido del programador y registro de errores.

- ``salud()`` alimenta /health (¿está viva la base de datos?) y /health/completo (además: ¿corre el programador de
  recordatorios?, ¿hay una ráfaga de errores?). Un servicio externo gratuito (UptimeRobot, Better Stack...) consulta
  /health/completo cada pocos minutos y avisa por correo si deja de responder 200.
- ``registrar_error()`` guarda los errores en la tabla ``errores_app`` (agrupados: el mismo error repetido suma un
  contador en vez de llenar la tabla). Se ven en /admin/errores. No guarda cuerpos de peticiones ni teléfonos.
- Sentry es opcional: si defines SENTRY_DSN y el paquete sentry-sdk está instalado, los errores también viajan allá.

Todas las funciones de escritura son a prueba de fallos: monitorear NUNCA debe tumbar la aplicación.
"""
import hashlib
import os
import threading
import time
import traceback

import database as db

_INICIO = time.time()
_tablas_listas = False
_candado = threading.Lock()
_ventana = {'inicio': 0.0, 'escrituras': 0}
MAX_ESCRITURAS_POR_MINUTO = 30
UMBRAL_SCHEDULER_SEG = 300          # el programador late cada minuto: 5 min sin latido = detenido
UMBRAL_RAFAGA_ERRORES = 25          # más de N errores nuevos en 10 minutos = ráfaga


def _asegurar_tablas(cursor):
    global _tablas_listas
    if _tablas_listas:
        return
    with _candado:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS errores_app (
                id SERIAL PRIMARY KEY,
                huella TEXT NOT NULL,
                primera TIMESTAMP NOT NULL DEFAULT NOW(),
                ultima TIMESTAMP NOT NULL DEFAULT NOW(),
                veces INTEGER NOT NULL DEFAULT 1,
                tipo TEXT,
                mensaje TEXT,
                traza TEXT,
                ruta TEXT,
                metodo TEXT,
                contexto TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS errores_app_huella_idx ON errores_app (huella, ultima)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_latidos (
                clave TEXT PRIMARY KEY,
                actualizado TIMESTAMP NOT NULL DEFAULT NOW(),
                info TEXT
            )
        """)
        _tablas_listas = True


def _con_bd(funcion):
    """Ejecuta ``funcion(cursor)`` con commit; devuelve su resultado o None si algo falla."""
    if not db.is_postgresql():
        return None
    conn = None
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        _asegurar_tablas(cursor)
        resultado = funcion(cursor)
        conn.commit()
        return resultado
    except Exception as e:
        print(f"⚠️ [MONITOREO] {type(e).__name__}: {str(e)[:150]}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------

def _huella(exc, ruta):
    tb = traceback.extract_tb(exc.__traceback__) if getattr(exc, '__traceback__', None) else []
    ultimo = f"{os.path.basename(tb[-1].filename)}:{tb[-1].name}" if tb else ''
    return hashlib.sha1(f"{type(exc).__name__}|{ruta}|{ultimo}".encode('utf-8')).hexdigest()[:16]


def registrar_error(exc, ruta=None, metodo=None, contexto=None):
    """Guarda un error agrupado por huella. Nunca lanza excepciones. Devuelve True si lo guardó."""
    try:
        if exc is None:
            return False
        ahora = time.time()
        with _candado:
            if ahora - _ventana['inicio'] > 60:
                _ventana['inicio'], _ventana['escrituras'] = ahora, 0
            if _ventana['escrituras'] >= MAX_ESCRITURAS_POR_MINUTO:
                return False                 # protección: una tormenta de errores no debe llenar la base de datos
            _ventana['escrituras'] += 1

        _enviar_a_sentry(exc)
        huella = _huella(exc, ruta)
        tipo = type(exc).__name__
        mensaje = str(exc)[:500]
        traza = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]

        def guardar(cursor):
            cursor.execute("""
                UPDATE errores_app SET veces = veces + 1, ultima = NOW(), mensaje = %s, traza = %s
                WHERE id = (SELECT id FROM errores_app WHERE huella = %s AND ultima > NOW() - INTERVAL '1 day'
                            ORDER BY ultima DESC LIMIT 1)
            """, (mensaje, traza, huella))
            if cursor.rowcount == 0:
                cursor.execute("""
                    INSERT INTO errores_app (huella, tipo, mensaje, traza, ruta, metodo, contexto)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (huella, tipo, mensaje, traza, (ruta or '')[:200], (metodo or '')[:10], (contexto or '')[:200]))
            cursor.execute("DELETE FROM errores_app WHERE ultima < NOW() - INTERVAL '30 days'")
            return True

        return bool(_con_bd(guardar))
    except Exception as e:
        print(f"⚠️ [MONITOREO] No se pudo registrar el error: {e}")
        return False


def errores_recientes(limite=100):
    def leer(cursor):
        cursor.execute("""
            SELECT id, primera, ultima, veces, tipo, mensaje, traza, ruta, metodo, contexto
            FROM errores_app ORDER BY ultima DESC LIMIT %s
        """, (int(limite),))
        return [dict(f) for f in cursor.fetchall()]
    return _con_bd(leer) or []


def limpiar_errores():
    return _con_bd(lambda cursor: cursor.execute("DELETE FROM errores_app")) is not None


def _contar_errores(cursor, minutos):
    cursor.execute("SELECT COALESCE(SUM(veces), 0) AS n FROM errores_app WHERE ultima > NOW() - (%s * INTERVAL '1 minute')", (minutos,))
    fila = cursor.fetchone()
    return int(fila['n'] if hasattr(fila, 'keys') else fila[0])


# ---------------------------------------------------------------------------
# Latido del programador de recordatorios
# ---------------------------------------------------------------------------

def registrar_latido(clave, info=''):
    def guardar(cursor):
        cursor.execute("""
            INSERT INTO app_latidos (clave, actualizado, info) VALUES (%s, NOW(), %s)
            ON CONFLICT (clave) DO UPDATE SET actualizado = NOW(), info = EXCLUDED.info
        """, (clave, str(info)[:200]))
    _con_bd(guardar)


def _edad_latido(cursor, clave):
    cursor.execute("SELECT EXTRACT(EPOCH FROM (NOW() - actualizado)) AS seg FROM app_latidos WHERE clave = %s", (clave,))
    fila = cursor.fetchone()
    if not fila:
        return None
    return float(fila['seg'] if hasattr(fila, 'keys') else fila[0])


# ---------------------------------------------------------------------------
# Salud
# ---------------------------------------------------------------------------

def salud(completo=False):
    """(diccionario, código_http). Sin datos sensibles: solo estados, tiempos y contadores."""
    info = {
        'estado': 'ok',
        'version': (os.getenv('RAILWAY_GIT_COMMIT_SHA') or '')[:7] or 'n/d',
        'activa_hace_seg': int(time.time() - _INICIO),
    }
    codigo = 200

    inicio = time.time()
    bd_ok = False
    try:
        conn = db.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            bd_ok = True
        finally:
            conn.close()
    except Exception as e:
        info['bd_error'] = type(e).__name__
    info['bd'] = {'ok': bd_ok, 'ms': int((time.time() - inicio) * 1000)}
    if not bd_ok:
        info['estado'] = 'caida'
        return info, 503
    if not completo:
        return info, codigo

    problemas = []
    if db.is_postgresql():
        def leer(cursor):
            return _edad_latido(cursor, 'scheduler'), _contar_errores(cursor, 10), _contar_errores(cursor, 60)
        resultado = _con_bd(leer)
        if resultado is not None:
            edad, errores_10, errores_60 = resultado
            info['scheduler'] = {'ok': edad is not None and edad < UMBRAL_SCHEDULER_SEG,
                                 'ultimo_latido_seg': None if edad is None else int(edad)}
            info['errores'] = {'ultimos_10_min': errores_10, 'ultima_hora': errores_60}
            if not info['scheduler']['ok']:
                problemas.append('scheduler detenido: no se enviarán recordatorios')
            if errores_10 > UMBRAL_RAFAGA_ERRORES:
                problemas.append(f'{errores_10} errores en los últimos 10 minutos')
    info['push_configurado'] = bool((os.getenv('VAPID_PRIVATE_KEY') or '').strip() and (os.getenv('VAPID_PUBLIC_KEY') or '').strip())
    if not info['push_configurado']:
        problemas.append('notificaciones push sin configurar (faltan claves VAPID)')

    if problemas:
        info['estado'] = 'degradado'
        info['problemas'] = problemas
        codigo = 503
    return info, codigo


# ---------------------------------------------------------------------------
# Sentry (opcional)
# ---------------------------------------------------------------------------

_sentry_activo = False


def iniciar_sentry():
    """Activa Sentry si hay SENTRY_DSN y el paquete está instalado. Devuelve True si quedó activo."""
    global _sentry_activo
    dsn = (os.getenv('SENTRY_DSN') or '').strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.0,
            send_default_pii=False,
            environment=os.getenv('RAILWAY_ENVIRONMENT_NAME', 'produccion'),
            release=(os.getenv('RAILWAY_GIT_COMMIT_SHA') or '')[:7] or None,
        )
        _sentry_activo = True
        print("✅ [MONITOREO] Sentry activado")
    except ImportError:
        print("⚠️ [MONITOREO] SENTRY_DSN definido pero sentry-sdk no está instalado")
    except Exception as e:
        print(f"⚠️ [MONITOREO] No se pudo iniciar Sentry: {type(e).__name__}")
    return _sentry_activo


def _enviar_a_sentry(exc):
    if _sentry_activo:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
