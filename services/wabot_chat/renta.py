"""Renta de vehículos por días (negocios con tipo_negocio = 'renta_autos').

Modelo:
  * profesional = vehículo, servicio = plan de renta, cita = reserva.
  * Un plan con duración >= 1440 minutos es un plan POR DÍA: el precio del servicio es el precio de UN día y el
    cliente elige cuántos días (1 a MAX_DIAS).
  * Recogida el día D a la hora elegida y devolución el día D + N a esa misma hora. La reserva se guarda como una
    cita en D con ``fecha_fin`` = D + N.
  * Regla de disponibilidad: el vehículo debe estar libre TODOS los días de D a D + N (sin reservas, rentas ni
    bloqueos), y el negocio debe abrir el día de recogida y el de devolución. Mientras dura una renta, el vehículo no
    se puede reservar por horas ni rentar de nuevo.

Los planes por horas (4 h, 8 h, día completo del mismo día) siguen usando el flujo de citas de siempre.
"""
from datetime import date, datetime, timedelta

MINUTOS_DIA = 1440
MAX_DIAS = 30
VENTANA_DIAS = 45          # hasta cuántos días hacia adelante se buscan fechas de recogida
MAX_OPCIONES_FECHA = 7
OPCIONES_DIAS = (1, 2, 3, 5, 7, 10, 14)

_DIAS_SEMANA = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')


def es_renta_por_dias(tipo_negocio, duracion_minutos):
    try:
        return tipo_negocio == 'renta_autos' and int(duracion_minutos or 0) >= MINUTOS_DIA
    except (TypeError, ValueError):
        return False


def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()


def fecha_devolucion(fecha_recogida, dias):
    """'YYYY-MM-DD' del día de devolución: la recogida más N días."""
    return (_a_fecha(fecha_recogida) + timedelta(days=int(dias))).isoformat()


def dias_de_renta(fecha_recogida, fecha_fin):
    return max(1, (_a_fecha(fecha_fin) - _a_fecha(fecha_recogida)).days)


def precio_total(precio_por_dia, dias):
    try:
        return float(precio_por_dia or 0) * int(dias)
    except (TypeError, ValueError):
        return 0.0


def etiqueta_dia(fecha):
    d = _a_fecha(fecha)
    return f"{_DIAS_SEMANA[d.weekday()]} {d.strftime('%d/%m')}"


def formatear_fecha(fecha):
    return _a_fecha(fecha).strftime('%d/%m/%Y')


def horas_recogida(negocio_id, fecha, ahora=None):
    """Horas ('HH:MM', una por hora) a las que se puede recoger el vehículo ese día."""
    import database as db
    import disponibilidad
    return disponibilidad.calcular_horarios_libres(
        db.obtener_horarios_por_dia(negocio_id, _a_fecha(fecha).isoformat()), [], [], 60, _a_fecha(fecha),
        ahora=ahora, paso=60)


def candidatas_recogida(negocio_id, profesional_id, dias, hoy, ahora=None, ventana=VENTANA_DIAS, maximo=MAX_OPCIONES_FECHA):
    """Fechas de recogida posibles para rentar ``dias`` días: [{'fecha', 'mostrar', 'devolucion'}]."""
    import database as db
    resultado = []
    for i in range(int(ventana) + 1):
        d = hoy + timedelta(days=i)
        devolucion = d + timedelta(days=int(dias))
        horario_recogida = db.obtener_horarios_por_dia(negocio_id, d.isoformat())
        if not horario_recogida or not horario_recogida.get('activo'):
            continue
        horario_devolucion = db.obtener_horarios_por_dia(negocio_id, devolucion.isoformat())
        if not horario_devolucion or not horario_devolucion.get('activo'):
            continue                      # no se podría devolver el vehículo
        if i == 0 and not horas_recogida(negocio_id, d, ahora):
            continue                      # hoy ya no quedan horas de recogida
        if not db.profesional_libre_en_rango(profesional_id, d.isoformat(), devolucion.isoformat()):
            continue
        resultado.append({
            'fecha': d.isoformat(),
            'devolucion': devolucion.isoformat(),
            'mostrar': f"{etiqueta_dia(d)} → devuelves {etiqueta_dia(devolucion)}",
        })
        if len(resultado) >= maximo:
            break
    return resultado
