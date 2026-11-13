"""Estado de las conversaciones del chat guardado en PostgreSQL.

Antes vivía solo en la memoria del proceso: se perdía en cada despliegue y no funcionaba con más de un
proceso (cada uno tenía su propia copia). Ahora la base de datos es la fuente de verdad: se carga al empezar
cada mensaje y se guarda al terminar. Sin PostgreSQL (desarrollo local) todo es un no-op y se sigue usando la memoria.
"""
import json
import threading
from datetime import date, datetime, time
from decimal import Decimal

import database as db

_tabla_lista = False
_candado = threading.Lock()
_LIMPIEZA_DIAS = 2


# ---------------------------------------------------------------------------
# Codificación JSON que conserva fechas, horas y decimales
# ---------------------------------------------------------------------------

def _a_json(valor):
    if isinstance(valor, datetime):
        return {'__dt__': valor.isoformat()}
    if isinstance(valor, date):
        return {'__date__': valor.isoformat()}
    if isinstance(valor, time):
        return {'__time__': valor.isoformat()}
    if isinstance(valor, Decimal):
        return {'__dec__': str(valor)}
    if isinstance(valor, (set, frozenset, tuple)):
        return list(valor)
    raise TypeError(f'tipo no serializable: {type(valor).__name__}')


def _desde_json(obj):
    if len(obj) == 1:
        if '__dt__' in obj:
            return datetime.fromisoformat(obj['__dt__'])
        if '__date__' in obj:
            return date.fromisoformat(obj['__date__'])
        if '__time__' in obj:
            return time.fromisoformat(obj['__time__'])
        if '__dec__' in obj:
            return Decimal(obj['__dec__'])
    return obj


def codificar(estado):
    return json.dumps(estado, default=_a_json, ensure_ascii=False)


def decodificar(texto):
    return json.loads(texto, object_hook=_desde_json)


# ---------------------------------------------------------------------------
# Acceso a la base de datos
# ---------------------------------------------------------------------------

def _asegurar_tabla(cursor):
    global _tabla_lista
    if _tabla_lista:
        return
    with _candado:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones_chat (
                clave TEXT PRIMARY KEY,
                datos TEXT NOT NULL,
                actualizado TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        _tabla_lista = True


def cargar(clave, ttl_minutos=30):
    """(estado, disponible). ``estado`` es el dict guardado, o None si no hay o ya caducó.
    ``disponible`` es False si no se pudo consultar la base (el llamador conserva entonces su copia en memoria)."""
    if not db.is_postgresql():
        return None, False
    conn = None
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        _asegurar_tabla(cursor)
        cursor.execute(
            "SELECT datos FROM conversaciones_chat WHERE clave = %s AND actualizado > NOW() - (%s * INTERVAL '1 minute')",
            (clave, int(ttl_minutos)),
        )
        fila = cursor.fetchone()
        conn.commit()
        if not fila:
            return None, True
        datos = fila['datos'] if hasattr(fila, 'keys') else fila[0]
        return decodificar(datos), True
    except Exception as e:
        print(f"⚠️ [ESTADO] No se pudo cargar la conversación: {e}")
        if conn:
            conn.rollback()
        return None, False
    finally:
        if conn:
            conn.close()


def guardar(clave, estado):
    """Guarda (o reemplaza) el estado. Devuelve False si no se pudo, sin romper la conversación."""
    if not db.is_postgresql():
        return False
    conn = None
    try:
        texto = codificar(estado)
        conn = db.get_db_connection()
        cursor = conn.cursor()
        _asegurar_tabla(cursor)
        cursor.execute("""
            INSERT INTO conversaciones_chat (clave, datos, actualizado) VALUES (%s, %s, NOW())
            ON CONFLICT (clave) DO UPDATE SET datos = EXCLUDED.datos, actualizado = NOW()
        """, (clave, texto))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ [ESTADO] No se pudo guardar la conversación: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def borrar(clave):
    if not db.is_postgresql():
        return False
    conn = None
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        _asegurar_tabla(cursor)
        cursor.execute("DELETE FROM conversaciones_chat WHERE clave = %s", (clave,))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ [ESTADO] No se pudo borrar la conversación: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def limpiar_antiguas():
    """Borra conversaciones sin actividad desde hace días (se llama de vez en cuando)."""
    if not db.is_postgresql():
        return
    conn = None
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        _asegurar_tabla(cursor)
        cursor.execute("DELETE FROM conversaciones_chat WHERE actualizado < NOW() - (%s * INTERVAL '1 day')", (_LIMPIEZA_DIAS,))
        conn.commit()
    except Exception as e:
        print(f"⚠️ [ESTADO] No se pudo limpiar conversaciones antiguas: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
