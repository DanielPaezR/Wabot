import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys
from datetime import datetime, timedelta
os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, _SERVICIO)
import pytz
import localizacion as L
import scheduler as S

L._consultar_bd = lambda nid: {1: {'pais': None, 'zona_horaria': None}, 2: {'pais': 'AW', 'zona_horaria': 'America/Aruba'}}.get(nid)

ok = True
def check(n, c):
    global ok; ok &= bool(c); print(('OK  ' if c else 'FALLO'), n)

aw = pytz.timezone('America/Aruba'); co = pytz.timezone('America/Bogota')
ahora_aw = datetime.now(aw).replace(tzinfo=None)

def cita(cid, negocio, fecha_hora_local):
    return {'id': cid, 'negocio_id': negocio, 'profesional_id': 10 + cid, 'cliente_telefono': '5601234',
            'cliente_nombre': 'X', 'fecha': fecha_hora_local.strftime('%Y-%m-%d'), 'hora': fecha_hora_local.strftime('%H:%M'),
            'recordatorio_1h_enviado': False, 'recordatorio_24h_enviado': False}

enviados = []
sched = S.AppointmentScheduler()
S.notification_system.notify_appointment_reminder = lambda pid, c, hours_before: enviados.append((c['id'], hours_before)) or 1
sched.enviar_recordatorio_push_cliente = lambda c, h: None
sched.marcar_recordatorio_enviado = lambda cid, tipo: True

# Hora de pared: ahora de Aruba + 70 min. Para Aruba son 1.17h (envía 1h); para Colombia (reloj 1h atrás) serían 2.17h (no envía 1h)
pared = ahora_aw + timedelta(minutes=70)
sched.obtener_citas_pendientes_recordatorio = lambda: [cita(1, 2, pared), cita(2, 1, pared)]
sched.verificar_recordatorios()
check('Aruba: cita a +70 min (hora de pared Aruba) recibe recordatorio de 1h', (1, 1) in enviados)
check('Colombia: la misma hora de pared está a +130 min, NO recibe recordatorio de 1h', (2, 1) not in enviados)

# Cita "mañana" según la fecha de Aruba
enviados.clear()
manana_aw = (ahora_aw + timedelta(days=1)).replace(hour=15, minute=0)
sched.obtener_citas_pendientes_recordatorio = lambda: [cita(3, 2, manana_aw)]
sched.verificar_recordatorios()
check('Aruba: cita de mañana recibe recordatorio de 24h', (3, 24) in enviados)

# Ventana de fechas consultadas incluye hoy/mañana de cualquier zona
consultadas = {}
class FakeCur:
    def execute(self, sql, params): consultadas['p'] = params
    def fetchall(self): return []
class FakeConn:
    def cursor(self): return FakeCur()
    def close(self): pass
S.db.get_db_connection = lambda: FakeConn()
S.AppointmentScheduler.obtener_citas_pendientes_recordatorio(sched)
check('consulta 5 fechas (ayer..+3)', len(consultadas['p']) == 5)

# Resumen diario: dispara a las 08:00 locales de cada zona, una sola vez por día
disparos = []
sched2 = S.AppointmentScheduler()
sched2.enviar_resumen_diario_profesionales = lambda ids, ahora: disparos.append((tuple(ids), ahora.strftime('%H:%M')))
L.negocios_por_zona = lambda: {'America/Bogota': [1], 'America/Aruba': [2]}
real_dt = S.datetime
class Fijo(real_dt):
    @classmethod
    def now(cls, tz=None):
        # 12:00 UTC => Aruba 08:00, Bogotá 07:00
        base = real_dt(2026, 11, 20, 12, 0, tzinfo=pytz.utc)
        return base.astimezone(tz) if tz else base
S.datetime = Fijo
sched2.verificar_resumen_diario(); sched2.verificar_resumen_diario()
S.datetime = real_dt
check('08:00 Aruba (07:00 Bogotá): dispara solo para Aruba y solo una vez', disparos == [((2,), '08:00')])
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
