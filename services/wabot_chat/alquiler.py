"""Alquiler de vehículos (tipo_negocio = 'alquiler_vehiculos').

Modelo (distinto al de citas con profesionales):
  * Los VEHÍCULOS son elementos alquilables del negocio (tabla ``vehiculos``): nombre, categoría, transmisión,
    pasajeros, precio por día, depósito, foto... No son cuentas de usuario.
  * Una RESERVA (tabla ``reservas_vehiculo``) es un vehículo + un rango de fechas: recogida el día D a una hora y
    devolución el día D + N a la misma hora. El precio es por día y se guarda el total.
  * Un vehículo está libre en un rango si no tiene otra reserva activa (pendiente, confirmada o en curso) que se
    solape; el día de devolución cuenta como ocupado. El negocio debe abrir el día de recogida y el de devolución.
  * Los avisos (push) llegan al/los propietario(s) del negocio y al cliente; no a "cuentas de vehículo".

Todo el SQL es de PostgreSQL. Las fechas son texto ISO 'YYYY-MM-DD' (igual que ``citas``).
"""
import json
import re
from datetime import date, datetime, timedelta

import database as db

TIPO = 'alquiler_vehiculos'
MAX_DIAS = 30
VENTANA_DIAS = 60
MAX_FECHAS_RECOGIDA = 10
OPCIONES_DIAS = (1, 2, 3, 5, 7, 10, 14)
ESTADOS_ACTIVOS = ('pendiente', 'confirmada', 'en_curso')
CATEGORIAS = ('Económico', 'Compacto', 'Sedán', 'SUV', 'Camioneta', 'Van', 'Lujo')
TRANSMISIONES = ('Automática', 'Manual')
COMBUSTIBLES = ('Gasolina', 'Diésel', 'Híbrido', 'Eléctrico')
ETIQUETAS_ESTADO = {
    'pendiente': 'Pendiente', 'confirmada': 'Confirmada', 'en_curso': 'En curso',
    'completada': 'Completada', 'cancelada': 'Cancelada',
}
_DIAS_SEMANA = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')


class ReservaError(Exception):
    """Error de negocio al reservar. ``codigo`` sirve para decidir el mensaje al cliente."""
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def asegurar_tablas():
    """Crea las tablas del módulo si no existen (PostgreSQL)."""
    if not db.is_postgresql():
        return
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehiculos (
                id SERIAL PRIMARY KEY,
                negocio_id INTEGER NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL,
                marca TEXT, modelo TEXT, anio INTEGER,
                categoria TEXT DEFAULT 'Compacto',
                transmision TEXT DEFAULT 'Automática',
                combustible TEXT DEFAULT 'Gasolina',
                pasajeros INTEGER DEFAULT 5,
                maletas INTEGER DEFAULT 2,
                puertas INTEGER DEFAULT 4,
                color TEXT, placa TEXT,
                precio_dia NUMERIC(12,2) NOT NULL DEFAULT 0,
                deposito NUMERIC(12,2) NOT NULL DEFAULT 0,
                descripcion TEXT,
                foto_url TEXT,
                activo BOOLEAN NOT NULL DEFAULT TRUE,
                creado TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS vehiculos_negocio_idx ON vehiculos (negocio_id, activo)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservas_vehiculo (
                id SERIAL PRIMARY KEY,
                negocio_id INTEGER NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
                vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id) ON DELETE CASCADE,
                cliente_telefono TEXT NOT NULL,
                cliente_nombre TEXT,
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                hora TEXT NOT NULL DEFAULT '09:00',
                dias INTEGER NOT NULL DEFAULT 1,
                precio_dia NUMERIC(12,2) NOT NULL DEFAULT 0,
                total NUMERIC(12,2) NOT NULL DEFAULT 0,
                deposito NUMERIC(12,2) NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'confirmada',
                notas TEXT,
                origen TEXT DEFAULT 'chat',
                recordatorio_24h_enviado BOOLEAN NOT NULL DEFAULT FALSE,
                recordatorio_1h_enviado BOOLEAN NOT NULL DEFAULT FALSE,
                creado TIMESTAMP NOT NULL DEFAULT NOW(),
                actualizado TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS reservas_vehiculo_veh_idx ON reservas_vehiculo (vehiculo_id, fecha_inicio, fecha_fin)")
        cur.execute("CREATE INDEX IF NOT EXISTS reservas_vehiculo_neg_idx ON reservas_vehiculo (negocio_id, fecha_inicio)")
        cur.execute("CREATE INDEX IF NOT EXISTS reservas_vehiculo_cli_idx ON reservas_vehiculo (cliente_telefono, negocio_id)")
        # Dispositivos push de los usuarios (propietarios): los de los profesionales viven en suscripciones_push
        cur.execute("""
            CREATE TABLE IF NOT EXISTS suscripciones_push_usuarios (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                subscription_json TEXT NOT NULL,
                dispositivo_info TEXT,
                activa BOOLEAN NOT NULL DEFAULT TRUE,
                UNIQUE (usuario_id, subscription_json)
            )
        """)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️ [ALQUILER] No se pudieron asegurar las tablas: {e}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()


def fecha_devolucion(fecha_inicio, dias):
    return (_a_fecha(fecha_inicio) + timedelta(days=int(dias))).isoformat()


def etiqueta_dia(fecha):
    d = _a_fecha(fecha)
    return f"{_DIAS_SEMANA[d.weekday()]} {d.strftime('%d/%m')}"


def formatear_fecha(fecha):
    return _a_fecha(fecha).strftime('%d/%m/%Y')


def dinero(valor):
    """$1.234.567 (punto como separador de miles)."""
    try:
        return '$' + f"{float(valor or 0):,.0f}".replace(',', '.')
    except (TypeError, ValueError):
        return '$0'


def _num(valor):
    return float(valor) if valor is not None else 0.0


def _con_cursor(funcion, escribir=False):
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        resultado = funcion(cur)
        if escribir:
            conn.commit()
        return resultado
    except Exception:
        if escribir:
            conn.rollback()
        raise
    finally:
        conn.close()


def _vehiculo_dict(fila):
    v = dict(fila)
    v['precio_dia'] = _num(v.get('precio_dia'))
    v['deposito'] = _num(v.get('deposito'))
    return v


def _reserva_dict(fila):
    r = dict(fila)
    for k in ('precio_dia', 'total', 'deposito'):
        r[k] = _num(r.get(k))
    return r


def estado_efectivo(reserva, hoy):
    """Estado que se muestra: una reserva confirmada cuyas fechas incluyen hoy está 'en curso' aunque nadie lo marcó."""
    hoy = _a_fecha(hoy).isoformat()
    if reserva['estado'] == 'confirmada' and reserva['fecha_inicio'] <= hoy <= reserva['fecha_fin']:
        return 'en_curso'
    return reserva['estado']


# ---------------------------------------------------------------------------
# Vehículos
# ---------------------------------------------------------------------------

def listar_vehiculos(negocio_id, solo_activos=True):
    def q(cur):
        cur.execute(f"SELECT * FROM vehiculos WHERE negocio_id = %s {'AND activo = TRUE' if solo_activos else ''} ORDER BY precio_dia, nombre", (negocio_id,))
        return [_vehiculo_dict(f) for f in cur.fetchall()]
    return _con_cursor(q)


def obtener_vehiculo(vehiculo_id, negocio_id=None):
    def q(cur):
        if negocio_id is None:
            cur.execute("SELECT * FROM vehiculos WHERE id = %s", (vehiculo_id,))
        else:
            cur.execute("SELECT * FROM vehiculos WHERE id = %s AND negocio_id = %s", (vehiculo_id, negocio_id))
        f = cur.fetchone()
        return _vehiculo_dict(f) if f else None
    return _con_cursor(q)


_CAMPOS_VEHICULO = ('nombre', 'marca', 'modelo', 'anio', 'categoria', 'transmision', 'combustible', 'pasajeros', 'maletas',
                    'puertas', 'color', 'placa', 'precio_dia', 'deposito', 'descripcion', 'foto_url')
_ENTEROS = ('anio', 'pasajeros', 'maletas', 'puertas')
_DECIMALES = ('precio_dia', 'deposito')


def _a_decimal(valor):
    """'60000', '60.000', '60.000,50', '60,5', '$ 60.000' -> float."""
    t = re.sub(r'[^\d.,-]', '', str(valor))
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.')
    elif ',' in t:
        t = t.replace(',', '.')
    elif re.fullmatch(r'-?\d{1,3}(\.\d{3})+', t):
        t = t.replace('.', '')
    return float(t)


def validar_vehiculo(datos):
    """Devuelve (datos_limpios, errores). Acepta los valores crudos de un formulario."""
    limpio, errores = {}, []
    for campo in _CAMPOS_VEHICULO:
        valor = datos.get(campo)
        if isinstance(valor, str):
            valor = valor.strip()
        if valor in ('', None):
            limpio[campo] = None
            continue
        if campo in _ENTEROS:
            try:
                limpio[campo] = int(valor)
            except (TypeError, ValueError):
                errores.append(f"'{campo}' debe ser un número entero")
        elif campo in _DECIMALES:
            try:
                limpio[campo] = float(str(valor).replace('.', '').replace(',', '.')) if re.search(r'[.,]\d{3}\b', str(valor)) else float(valor)
            except (TypeError, ValueError):
                errores.append(f"'{campo}' debe ser un número")
        else:
            limpio[campo] = str(valor)[:500]
    if not limpio.get('nombre'):
        errores.append('El nombre del vehículo es obligatorio')
    if limpio.get('precio_dia') is None or limpio.get('precio_dia', 0) <= 0:
        errores.append('El precio por día debe ser mayor que cero')
    if limpio.get('deposito') is None:
        limpio['deposito'] = 0.0
    if limpio.get('deposito', 0) < 0:
        errores.append('El depósito no puede ser negativo')
    for campo, minimo, maximo in (('pasajeros', 1, 20), ('maletas', 0, 20), ('puertas', 2, 6), ('anio', 1980, 2100)):
        v = limpio.get(campo)
        if v is not None and not (minimo <= v <= maximo):
            errores.append(f"'{campo}' debe estar entre {minimo} y {maximo}")
    foto = limpio.get('foto_url')
    if foto and not re.match(r'^https?://', foto):
        errores.append('La foto debe ser una dirección http(s)')
    return limpio, errores


def crear_vehiculo(negocio_id, datos):
    limpio, errores = validar_vehiculo(datos)
    if errores:
        raise ValueError('; '.join(errores))
    columnas = [c for c in _CAMPOS_VEHICULO if limpio.get(c) is not None]

    def q(cur):
        cur.execute(
            f"INSERT INTO vehiculos (negocio_id, {', '.join(columnas)}) VALUES (%s, {', '.join(['%s'] * len(columnas))}) RETURNING id",
            [negocio_id] + [limpio[c] for c in columnas])
        return cur.fetchone()['id']
    return _con_cursor(q, escribir=True)


def actualizar_vehiculo(vehiculo_id, negocio_id, datos):
    limpio, errores = validar_vehiculo(datos)
    if errores:
        raise ValueError('; '.join(errores))

    def q(cur):
        cur.execute(
            f"UPDATE vehiculos SET {', '.join(c + ' = %s' for c in _CAMPOS_VEHICULO)} WHERE id = %s AND negocio_id = %s",
            [limpio.get(c) for c in _CAMPOS_VEHICULO] + [vehiculo_id, negocio_id])
        return cur.rowcount > 0
    return _con_cursor(q, escribir=True)


def activar_vehiculo(vehiculo_id, negocio_id, activo):
    return _con_cursor(lambda cur: (cur.execute("UPDATE vehiculos SET activo = %s WHERE id = %s AND negocio_id = %s", (bool(activo), vehiculo_id, negocio_id)) or cur.rowcount > 0), escribir=True)


# ---------------------------------------------------------------------------
# Disponibilidad
# ---------------------------------------------------------------------------

def vehiculo_libre(vehiculo_id, fecha_inicio, fecha_fin, excluir_reserva_id=None):
    def q(cur):
        cur.execute("""
            SELECT 1 FROM reservas_vehiculo
            WHERE vehiculo_id = %s AND estado IN ('pendiente', 'confirmada', 'en_curso')
              AND fecha_inicio <= %s AND fecha_fin >= %s AND (%s::int IS NULL OR id <> %s)
            LIMIT 1
        """, (vehiculo_id, fecha_fin, fecha_inicio, excluir_reserva_id, excluir_reserva_id))
        return cur.fetchone() is None
    return _con_cursor(q)


def vehiculos_disponibles(negocio_id, fecha_inicio, dias):
    """Vehículos activos libres de ``fecha_inicio`` a la devolución, con el total calculado."""
    fin = fecha_devolucion(fecha_inicio, dias)

    def q(cur):
        cur.execute("""
            SELECT v.* FROM vehiculos v
            WHERE v.negocio_id = %s AND v.activo = TRUE
              AND NOT EXISTS (
                SELECT 1 FROM reservas_vehiculo r
                WHERE r.vehiculo_id = v.id AND r.estado IN ('pendiente', 'confirmada', 'en_curso')
                  AND r.fecha_inicio <= %s AND r.fecha_fin >= %s)
            ORDER BY v.precio_dia, v.nombre
        """, (negocio_id, fin, fecha_inicio))
        lista = [_vehiculo_dict(f) for f in cur.fetchall()]
        for v in lista:
            v['total'] = v['precio_dia'] * int(dias)
        return lista
    return _con_cursor(q)


def negocio_abre(negocio_id, fecha):
    horario = db.obtener_horarios_por_dia(negocio_id, _a_fecha(fecha).isoformat())
    return bool(horario and horario.get('activo'))


def horas_recogida(negocio_id, fecha, ahora=None):
    """Horas ('HH:MM', una por hora) a las que se puede recoger ese día (respeta el horario, el almuerzo y la hora actual)."""
    import disponibilidad
    return disponibilidad.calcular_horarios_libres(
        db.obtener_horarios_por_dia(negocio_id, _a_fecha(fecha).isoformat()), [], [], 60, _a_fecha(fecha), ahora=ahora, paso=60)


def fechas_recogida(negocio_id, hoy, ahora=None, maximo=MAX_FECHAS_RECOGIDA, ventana=VENTANA_DIAS):
    """Próximos días en que se puede recoger: [{'fecha', 'mostrar'}]."""
    resultado = []
    for i in range(ventana + 1):
        d = _a_fecha(hoy) + timedelta(days=i)
        if not negocio_abre(negocio_id, d):
            continue
        if i == 0 and not horas_recogida(negocio_id, d, ahora):
            continue
        resultado.append({'fecha': d.isoformat(), 'mostrar': etiqueta_dia(d)})
        if len(resultado) >= maximo:
            break
    return resultado


def validar_rango(negocio_id, fecha_inicio, dias, hoy):
    """Lanza ReservaError si las fechas no se pueden usar."""
    if not isinstance(dias, int) or not (1 <= dias <= MAX_DIAS):
        raise ReservaError('dias_invalidos', f'Los días deben estar entre 1 y {MAX_DIAS}')
    inicio = _a_fecha(fecha_inicio)
    if inicio < _a_fecha(hoy):
        raise ReservaError('fecha_pasada', 'La fecha de recogida ya pasó')
    if not negocio_abre(negocio_id, inicio):
        raise ReservaError('cerrado_recogida', 'El negocio no abre el día de recogida')
    if not negocio_abre(negocio_id, fecha_devolucion(inicio, dias)):
        raise ReservaError('cerrado_devolucion', 'El negocio no abre el día de devolución')


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------

def crear_reserva(negocio_id, vehiculo_id, telefono, nombre, fecha_inicio, dias, hora, hoy, notas='', origen='chat', estado='confirmada'):
    """Crea la reserva o lanza ReservaError. Devuelve el diccionario de la reserva con los datos del vehículo."""
    dias = int(dias)
    validar_rango(negocio_id, fecha_inicio, dias, hoy)
    fecha_fin = fecha_devolucion(fecha_inicio, dias)
    hora = (hora or '09:00')[:5]

    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM vehiculos WHERE id = %s AND negocio_id = %s AND activo = TRUE", (vehiculo_id, negocio_id))
        v = cur.fetchone()
        if not v:
            raise ReservaError('vehiculo_invalido', 'El vehículo no existe o no está disponible')
        # una reserva a la vez por vehículo: el lock evita que dos clientes tomen el mismo vehículo al mismo tiempo
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"vehiculo_{vehiculo_id}",))
        cur.execute("""
            SELECT 1 FROM reservas_vehiculo
            WHERE vehiculo_id = %s AND estado IN ('pendiente', 'confirmada', 'en_curso')
              AND fecha_inicio <= %s AND fecha_fin >= %s LIMIT 1
        """, (vehiculo_id, fecha_fin, fecha_inicio))
        if cur.fetchone():
            raise ReservaError('no_disponible', 'El vehículo ya está reservado en esas fechas')
        precio = _num(v['precio_dia'])
        cur.execute("""
            INSERT INTO reservas_vehiculo (negocio_id, vehiculo_id, cliente_telefono, cliente_nombre, fecha_inicio, fecha_fin,
                                           hora, dias, precio_dia, total, deposito, estado, notas, origen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
        """, (negocio_id, vehiculo_id, telefono, nombre, fecha_inicio, fecha_fin, hora, dias, precio, precio * dias,
              _num(v['deposito']), estado, (notas or None), origen))
        reserva = _reserva_dict(cur.fetchone())
        conn.commit()
    except ReservaError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    reserva['vehiculo_nombre'] = v['nombre']
    return reserva


_SELECT_RESERVA = """
    SELECT r.*, v.nombre AS vehiculo_nombre, v.categoria, v.foto_url, v.placa
    FROM reservas_vehiculo r JOIN vehiculos v ON v.id = r.vehiculo_id
"""


def obtener_reserva(reserva_id, negocio_id):
    def q(cur):
        cur.execute(_SELECT_RESERVA + " WHERE r.id = %s AND r.negocio_id = %s", (reserva_id, negocio_id))
        f = cur.fetchone()
        return _reserva_dict(f) if f else None
    return _con_cursor(q)


def reservas_cliente(telefono, negocio_id, limite=60):
    def q(cur):
        cur.execute(_SELECT_RESERVA + " WHERE r.cliente_telefono = %s AND r.negocio_id = %s ORDER BY r.fecha_inicio DESC, r.id DESC LIMIT %s",
                    (telefono, negocio_id, limite))
        return [_reserva_dict(f) for f in cur.fetchall()]
    return _con_cursor(q)


def reservas_negocio(negocio_id, vista, hoy, limite=300):
    """vista: 'proximas' | 'en_curso' | 'hoy' | 'historial' | 'todas'."""
    hoy = _a_fecha(hoy).isoformat()
    filtros = {
        'proximas': "r.estado IN ('pendiente', 'confirmada') AND r.fecha_inicio > %s",
        'en_curso': "r.estado IN ('confirmada', 'en_curso') AND r.fecha_inicio <= %s AND r.fecha_fin >= %s",
        'hoy': "r.estado IN ('pendiente', 'confirmada', 'en_curso') AND (r.fecha_inicio = %s OR r.fecha_fin = %s)",
        'historial': "(r.estado IN ('completada', 'cancelada') OR r.fecha_fin < %s)",
        'todas': "TRUE",
    }
    if vista not in filtros:
        vista = 'proximas'
    n_param = filtros[vista].count('%s')
    orden = "r.fecha_inicio DESC, r.id DESC" if vista in ('historial', 'todas') else "r.fecha_inicio, r.hora, r.id"

    def q(cur):
        cur.execute(_SELECT_RESERVA + f" WHERE r.negocio_id = %s AND {filtros[vista]} ORDER BY {orden} LIMIT %s",
                    [negocio_id] + [hoy] * n_param + [limite])
        return [_reserva_dict(f) for f in cur.fetchall()]
    return _con_cursor(q)


def cancelar_reserva(reserva_id, negocio_id, telefono=None):
    """Cancela una reserva activa. Si se pasa ``telefono`` debe ser el del cliente que la hizo. Devuelve la reserva o None."""
    def q(cur):
        cur.execute("""
            UPDATE reservas_vehiculo SET estado = 'cancelada', actualizado = NOW()
            WHERE id = %s AND negocio_id = %s AND estado IN ('pendiente', 'confirmada', 'en_curso')
              AND (%s::text IS NULL OR cliente_telefono = %s) RETURNING id
        """, (reserva_id, negocio_id, telefono, telefono))
        return cur.fetchone() is not None
    if not _con_cursor(q, escribir=True):
        return None
    return obtener_reserva(reserva_id, negocio_id)


_TRANSICIONES = {            # acción del propietario -> (estados de origen, estado nuevo)
    'confirmar': (('pendiente',), 'confirmada'),
    'entregar': (('pendiente', 'confirmada'), 'en_curso'),
    'devolver': (('en_curso', 'confirmada'), 'completada'),
    'cancelar': (('pendiente', 'confirmada', 'en_curso'), 'cancelada'),
}


def aplicar_accion(reserva_id, negocio_id, accion):
    """Acciones del propietario: confirmar, entregar, devolver, cancelar. Devuelve la reserva o None si no procede."""
    if accion not in _TRANSICIONES:
        return None
    origenes, nuevo = _TRANSICIONES[accion]

    def q(cur):
        cur.execute("UPDATE reservas_vehiculo SET estado = %s, actualizado = NOW() WHERE id = %s AND negocio_id = %s AND estado = ANY(%s) RETURNING id",
                    (nuevo, reserva_id, negocio_id, list(origenes)))
        return cur.fetchone() is not None
    if not _con_cursor(q, escribir=True):
        return None
    return obtener_reserva(reserva_id, negocio_id)


# ---------------------------------------------------------------------------
# Resumen para el panel
# ---------------------------------------------------------------------------

def resumen_negocio(negocio_id, hoy):
    hoy_s = _a_fecha(hoy).isoformat()
    mes = hoy_s[:7]

    def q(cur):
        r = {}
        cur.execute("SELECT COUNT(*) AS n FROM vehiculos WHERE negocio_id = %s AND activo = TRUE", (negocio_id,))
        r['vehiculos'] = cur.fetchone()['n']
        cur.execute("""SELECT COUNT(*) AS n FROM reservas_vehiculo WHERE negocio_id = %s AND estado IN ('pendiente','confirmada') AND fecha_inicio = %s""", (negocio_id, hoy_s))
        r['recogidas_hoy'] = cur.fetchone()['n']
        cur.execute("""SELECT COUNT(*) AS n FROM reservas_vehiculo WHERE negocio_id = %s AND estado IN ('confirmada','en_curso') AND fecha_fin = %s""", (negocio_id, hoy_s))
        r['devoluciones_hoy'] = cur.fetchone()['n']
        cur.execute("""SELECT COUNT(DISTINCT vehiculo_id) AS n FROM reservas_vehiculo WHERE negocio_id = %s AND estado IN ('confirmada','en_curso') AND fecha_inicio <= %s AND fecha_fin >= %s""", (negocio_id, hoy_s, hoy_s))
        r['en_curso'] = cur.fetchone()['n']
        r['libres_hoy'] = max(0, r['vehiculos'] - r['en_curso'])
        cur.execute("""SELECT COUNT(*) AS n FROM reservas_vehiculo WHERE negocio_id = %s AND estado IN ('pendiente','confirmada') AND fecha_inicio > %s AND fecha_inicio <= %s""",
                    (negocio_id, hoy_s, fecha_devolucion(hoy_s, 7)))
        r['proximas_7d'] = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM reservas_vehiculo WHERE negocio_id = %s AND estado = 'pendiente'", (negocio_id,))
        r['pendientes'] = cur.fetchone()['n']
        cur.execute("""SELECT COALESCE(SUM(total), 0) AS t, COUNT(*) AS n FROM reservas_vehiculo
                       WHERE negocio_id = %s AND estado IN ('confirmada','en_curso','completada') AND substr(fecha_inicio, 1, 7) = %s""", (negocio_id, mes))
        fila = cur.fetchone()
        r['ingresos_mes'] = _num(fila['t'])
        r['reservas_mes'] = fila['n']
        return r
    return _con_cursor(q)


def actividad_reciente(negocio_id, limite=8):
    def q(cur):
        cur.execute(_SELECT_RESERVA + " WHERE r.negocio_id = %s ORDER BY r.creado DESC LIMIT %s", (negocio_id, limite))
        return [_reserva_dict(f) for f in cur.fetchall()]
    return _con_cursor(q)


# ---------------------------------------------------------------------------
# Avisos (push al propietario y al cliente)
# ---------------------------------------------------------------------------

def _resumen_corto(reserva):
    return (f"{reserva.get('cliente_nombre') or 'Un cliente'} - {reserva['vehiculo_nombre']} - "
            f"{formatear_fecha(reserva['fecha_inicio'])} a {formatear_fecha(reserva['fecha_fin'])} ({dinero(reserva['total'])})")


def notificar_nueva_reserva(reserva):
    """Aviso al propietario (push a todos sus dispositivos) y confirmación al cliente. Nunca lanza excepciones."""
    try:
        from push_notifications import enviar_push_propietarios, enviar_notificacion_cliente
        enviar_push_propietarios(reserva['negocio_id'], 'Nueva reserva', _resumen_corto(reserva), url='/negocio/reservas')
        enviar_notificacion_cliente(
            reserva['cliente_telefono'], reserva['negocio_id'], 'Reserva confirmada',
            f"{reserva['vehiculo_nombre']}: recoges el {formatear_fecha(reserva['fecha_inicio'])} a las {reserva['hora']} "
            f"y devuelves el {formatear_fecha(reserva['fecha_fin'])}",
            cita_id=reserva['id'], url=f"/cliente/{reserva['negocio_id']}")
    except Exception as e:
        print(f"⚠️ [ALQUILER] No se pudo avisar de la nueva reserva: {type(e).__name__}: {e}")


def notificar_cancelacion(reserva, por='cliente'):
    try:
        from push_notifications import enviar_push_propietarios, enviar_notificacion_cliente
        if por == 'cliente':
            enviar_push_propietarios(reserva['negocio_id'], 'Reserva cancelada', _resumen_corto(reserva), url='/negocio/reservas')
        else:
            enviar_notificacion_cliente(reserva['cliente_telefono'], reserva['negocio_id'], 'Reserva cancelada',
                                        f"Tu reserva de {reserva['vehiculo_nombre']} del {formatear_fecha(reserva['fecha_inicio'])} fue cancelada",
                                        cita_id=reserva['id'], url=f"/cliente/{reserva['negocio_id']}")
    except Exception as e:
        print(f"⚠️ [ALQUILER] No se pudo avisar de la cancelación: {type(e).__name__}: {e}")


def enviar_recordatorios(ahora_por_negocio=None):
    """Recordatorios al cliente: el día anterior (24 h) y ~1 hora antes de la recogida. Cada uno se reclama atómicamente.

    ``ahora_por_negocio(negocio_id)`` -> datetime naive en la hora local del negocio (por defecto, la zona de cada negocio).
    """
    import localizacion
    enviados = 0

    def candidatos(cur):
        cur.execute("""
            SELECT r.*, v.nombre AS vehiculo_nombre FROM reservas_vehiculo r JOIN vehiculos v ON v.id = r.vehiculo_id
            WHERE r.estado = 'confirmada' AND (r.recordatorio_24h_enviado = FALSE OR r.recordatorio_1h_enviado = FALSE)
              AND r.fecha_inicio >= %s AND r.fecha_inicio <= %s
        """, ((date.today() - timedelta(days=1)).isoformat(), (date.today() + timedelta(days=2)).isoformat()))
        return [_reserva_dict(f) for f in cur.fetchall()]
    try:
        filas = _con_cursor(candidatos)
    except Exception as e:
        print(f"⚠️ [ALQUILER] Error buscando recordatorios: {e}")
        return 0

    for r in filas:
        try:
            if ahora_por_negocio:
                ahora = ahora_por_negocio(r['negocio_id'])
            else:
                ahora = datetime.now(localizacion.zona_de(r['negocio_id'])).replace(tzinfo=None)
            recogida = datetime.strptime(f"{r['fecha_inicio']} {r['hora'][:5]}", '%Y-%m-%d %H:%M')
            horas = (recogida - ahora).total_seconds() / 3600
            tipo = None
            if 0 < horas <= 1.5 and not r['recordatorio_1h_enviado']:
                tipo = '1h'
            elif 1.5 < horas <= 30 and not r['recordatorio_24h_enviado'] and r['fecha_inicio'] == (ahora.date() + timedelta(days=1)).isoformat():
                tipo = '24h'
            if not tipo:
                continue
            columna = 'recordatorio_1h_enviado' if tipo == '1h' else 'recordatorio_24h_enviado'

            def reclamar(cur, columna=columna, rid=r['id']):
                cur.execute(f"UPDATE reservas_vehiculo SET {columna} = TRUE WHERE id = %s AND {columna} = FALSE", (rid,))
                return cur.rowcount > 0
            if not _con_cursor(reclamar, escribir=True):
                continue
            from push_notifications import enviar_notificacion_cliente
            cuando = 'mañana' if tipo == '24h' else 'en aproximadamente 1 hora'
            enviar_notificacion_cliente(
                r['cliente_telefono'], r['negocio_id'], 'Recordatorio de tu reserva',
                f"Recoges {r['vehiculo_nombre']} {cuando} ({formatear_fecha(r['fecha_inicio'])} a las {r['hora'][:5]}). "
                f"Devuelves el {formatear_fecha(r['fecha_fin'])}.", cita_id=r['id'], url=f"/cliente/{r['negocio_id']}")
            enviados += 1
        except Exception as e:
            print(f"⚠️ [ALQUILER] Error enviando recordatorio de la reserva {r.get('id')}: {type(e).__name__}: {e}")
    return enviados


def resumen_diario(negocio_ids, hoy_por_negocio=None):
    """Aviso de las 8:00 al propietario: recogidas y devoluciones de hoy. Una sola vez por negocio y día."""
    import localizacion
    enviados = 0
    for negocio_id in negocio_ids or []:
        try:
            negocio = db.obtener_negocio_por_id(negocio_id)
            if not negocio or dict(negocio).get('tipo_negocio') != TIPO:
                continue
            hoy = hoy_por_negocio(negocio_id) if hoy_por_negocio else datetime.now(localizacion.zona_de(negocio_id)).date()
            if not db.reclamar_ejecucion(f'alquiler_resumen_{negocio_id}_{hoy.isoformat()}'):
                continue
            r = resumen_negocio(negocio_id, hoy)
            if not (r['recogidas_hoy'] or r['devoluciones_hoy']):
                continue
            from push_notifications import enviar_push_propietarios
            enviar_push_propietarios(
                negocio_id, 'Resumen del día',
                f"Hoy: {r['recogidas_hoy']} recogida(s) y {r['devoluciones_hoy']} devolución(es). {r['en_curso']} vehículo(s) en la calle.",
                url='/negocio')
            enviados += 1
        except Exception as e:
            print(f"⚠️ [ALQUILER] Error en el resumen diario del negocio {negocio_id}: {type(e).__name__}: {e}")
    return enviados


# ---------------------------------------------------------------------------
# "Mis reservas" del cliente (misma forma que la lista de citas de la página del cliente)
# ---------------------------------------------------------------------------

def citas_cliente_api(telefono, negocio_id, hoy):
    """Reservas del cliente con el formato de /api/cliente/mis-citas (vehículo = 'profesional', total = 'precio')."""
    hoy_s = _a_fecha(hoy).isoformat()
    negocio = db.obtener_negocio_por_id(negocio_id)
    nombre_negocio = dict(negocio or {}).get('nombre', '')
    salida = []
    for r in reservas_cliente(telefono, negocio_id):
        efectivo = estado_efectivo(r, hoy_s)
        activa = r['estado'] in ESTADOS_ACTIVOS and r['fecha_fin'] >= hoy_s
        salida.append({
            'id': r['id'],
            'fecha': formatear_fecha(r['fecha_inicio']),
            'fecha_fin': formatear_fecha(r['fecha_fin']),
            'hora': r['hora'][:5],
            'estado': 'confirmado' if r['estado'] in ESTADOS_ACTIVOS else r['estado'],
            'es_proxima': bool(activa),
            'estado_texto': ETIQUETAS_ESTADO['confirmada'] if (activa and efectivo != 'en_curso' and r['estado'] != 'pendiente')
                            else ETIQUETAS_ESTADO['en_curso'] if (activa and efectivo == 'en_curso')
                            else ('Pasada' if r['estado'] in ('confirmada', 'en_curso', 'pendiente') else ETIQUETAS_ESTADO.get(r['estado'], r['estado'])),
            'estado_icono': '🚗' if efectivo == 'en_curso' else '📅',
            'servicio': f"Alquiler por {r['dias']} día(s)",
            'precio': r['total'],
            'profesional': r['vehiculo_nombre'],
            'profesional_id': r['vehiculo_id'],
            'negocio': nombre_negocio,
            'ya_calificada': False,
        })
    return {'success': True, 'citas': salida, 'total': len(salida)}
