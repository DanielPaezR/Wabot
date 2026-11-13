"""Disponibilidad de horarios: UNA sola implementación para el chat, el asistente de IA y los paneles.

Antes había cuatro copias (chat, IA y dos endpoints) y cada una comparaba las horas de forma distinta;
con PostgreSQL la columna ``citas.hora`` es TIME y varias copias fallaban en silencio, de modo que
ignoraban las citas y bloqueos ya existentes. Aquí todo se normaliza a minutos desde medianoche.

La parte pura (``calcular_horarios_libres``) no toca la base de datos y se prueba sola.
"""
import re
from datetime import date, datetime, timedelta

PASO_MINUTOS = 15          # separación entre horarios ofrecidos
MARGEN_HOY_MINUTOS = 30    # anticipación mínima para reservar hoy
DURACION_MINIMA = 15       # una cita sin duración válida ocupa al menos esto

_HORA_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?\s*([AaPp]\.?[Mm]\.?)?\s*$')


def a_minutos(valor):
    """Hora -> minutos desde medianoche. Acepta time, datetime, 'HH:MM', 'HH:MM:SS' y 'h:mm AM/PM'. None si no se entiende."""
    if valor is None:
        return None
    if hasattr(valor, 'hour') and hasattr(valor, 'minute'):
        return valor.hour * 60 + valor.minute
    m = _HORA_RE.match(str(valor))
    if not m:
        return None
    horas, minutos, sufijo = int(m.group(1)), int(m.group(2)), m.group(3)
    if sufijo:
        pm = sufijo.lower().startswith('p')
        if horas == 12:
            horas = 12 if pm else 0
        elif pm:
            horas += 12
    if horas > 24 or minutos > 59:
        return None
    return horas * 60 + minutos


def a_hhmm(minutos):
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def normalizar_hhmm(valor):
    """Cualquier hora reconocible -> 'HH:MM' (o None)."""
    minutos = a_minutos(valor)
    return None if minutos is None else a_hhmm(minutos)


def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()


def intervalos_ocupados(citas):
    """Citas/bloqueos [{'hora', 'duracion', 'estado'}] -> [(inicio, fin)] en minutos. Ignora las canceladas."""
    ocupados = []
    for cita in citas or []:
        estado = str(cita.get('estado') or 'confirmado').lower()
        if estado in ('cancelado', 'cancelada'):
            continue
        inicio = a_minutos(cita.get('hora'))
        if inicio is None:
            continue
        try:
            duracion = int(cita.get('duracion') or 0)
        except (TypeError, ValueError):
            duracion = 0
        ocupados.append((inicio, inicio + max(duracion, DURACION_MINIMA)))
    return ocupados


def intervalos_bloqueo_recurrente(bloqueos, fecha):
    """Bloqueos recurrentes activos que aplican en ``fecha`` -> [(inicio, fin)]. Aplica TODOS, no solo el primero."""
    fecha = _a_fecha(fecha)
    dia = fecha.isoweekday()
    intervalos = []
    for bloqueo in bloqueos or []:
        if not bloqueo.get('activo', True):
            continue
        dias = bloqueo.get('dias_semana_lista') or []
        if dia not in [int(d) for d in dias if str(d).isdigit()]:
            continue
        desde, hasta = bloqueo.get('fecha_inicio'), bloqueo.get('fecha_fin')
        if desde and fecha < _a_fecha(desde):
            continue
        if hasta and fecha > _a_fecha(hasta):
            continue
        inicio, fin = a_minutos(bloqueo.get('hora_inicio')), a_minutos(bloqueo.get('hora_fin'))
        if inicio is not None and fin is not None and fin > inicio:
            intervalos.append((inicio, fin))
    return intervalos


def _se_solapan(a_ini, a_fin, b_ini, b_fin):
    return a_ini < b_fin and a_fin > b_ini


def calcular_horarios_libres(horario_dia, citas, bloqueos_recurrentes, duracion, fecha, ahora=None,
                             paso=PASO_MINUTOS, margen_hoy=MARGEN_HOY_MINUTOS):
    """Horarios de inicio libres ('HH:MM', ordenados) para un servicio de ``duracion`` minutos.

    horario_dia: {'activo', 'hora_inicio', 'hora_fin', 'almuerzo_inicio', 'almuerzo_fin'}
    citas: citas y bloqueos puntuales del día  [{'hora', 'duracion', 'estado'}]
    ahora: datetime en la zona horaria del negocio (para no ofrecer horas pasadas ni demasiado cercanas)
    """
    if not horario_dia or not horario_dia.get('activo'):
        return []
    apertura, cierre = a_minutos(horario_dia.get('hora_inicio')), a_minutos(horario_dia.get('hora_fin'))
    if apertura is None or cierre is None or cierre <= apertura:
        return []
    try:
        duracion = int(duracion)
    except (TypeError, ValueError):
        return []
    if duracion <= 0:
        return []

    fecha = _a_fecha(fecha)
    a_ini, a_fin = a_minutos(horario_dia.get('almuerzo_inicio')), a_minutos(horario_dia.get('almuerzo_fin'))
    tiene_almuerzo = a_ini is not None and a_fin is not None and a_fin > a_ini

    ocupados = intervalos_ocupados(citas) + intervalos_bloqueo_recurrente(bloqueos_recurrentes, fecha)

    minuto_minimo = None
    if ahora is not None and ahora.date() == fecha:
        minuto_minimo = ahora.hour * 60 + ahora.minute + ahora.second / 60 + margen_hoy

    libres = []
    inicio = apertura
    while inicio + duracion <= cierre:
        fin = inicio + duracion
        libre = True
        if minuto_minimo is not None and inicio < minuto_minimo:
            libre = False
        elif tiene_almuerzo and _se_solapan(inicio, fin, a_ini, a_fin):
            libre = False
        elif any(_se_solapan(inicio, fin, o_ini, o_fin) for o_ini, o_fin in ocupados):
            libre = False
        if libre:
            libres.append(a_hhmm(inicio))
        inicio += paso
    return libres


# ---------------------------------------------------------------------------
# Acceso a la base de datos
# ---------------------------------------------------------------------------

def horarios_libres(negocio_id, profesional_id, fecha, servicio_id=None, duracion=None, paso=PASO_MINUTOS):
    """Horarios libres de un profesional ('HH:MM') para un servicio (o una duración en minutos)."""
    import database as db
    from localizacion import tz_negocio

    fecha_str = fecha if isinstance(fecha, str) else _a_fecha(fecha).isoformat()
    if duracion is None:
        duracion = db.obtener_duracion_servicio(negocio_id, servicio_id) if servicio_id else None
    if not duracion:
        return []
    return calcular_horarios_libres(
        db.obtener_horarios_por_dia(negocio_id, fecha_str),
        db.obtener_citas_dia(negocio_id, profesional_id, fecha_str),
        db.obtener_bloqueos_recurrentes(negocio_id, profesional_id),
        duracion,
        fecha_str,
        ahora=datetime.now(tz_negocio),
        paso=paso,
    )


def duracion_minima_servicios(negocio_id):
    """Duración del servicio activo más corto del negocio (None si no hay servicios)."""
    import database as db
    duraciones = []
    for servicio in db.obtener_servicios(negocio_id) or []:
        try:
            if servicio.get('duracion'):
                duraciones.append(int(servicio['duracion']))
        except (TypeError, ValueError, AttributeError):
            continue
    return min(duraciones) if duraciones else None
