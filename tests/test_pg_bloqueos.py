"""Bloqueos de horario contra un PostgreSQL local real (puerto 55432). Nunca toca producción."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, datetime as dt
os.environ['DATABASE_URL'] = _url_bd_pg()
sys.path.insert(0, _SERVICIO)
import database as db
import web_chat_handler as H

ok = True
def check(nombre, cond, extra=''):
    global ok; ok &= bool(cond); print(('OK   ' if cond else 'FALLO'), nombre, extra)

NEG = 1
conn = db.get_db_connection(); cur = conn.cursor()
cur.execute("DELETE FROM citas"); conn.commit()
try:
    cur.execute("DELETE FROM bloqueos_recurrentes"); conn.commit()
except Exception:
    conn.rollback()
cur.execute("SELECT id, duracion FROM servicios WHERE negocio_id=%s AND activo=TRUE ORDER BY id", (NEG,))
servicios = cur.fetchall()
cur.execute("SELECT id FROM profesionales WHERE negocio_id=%s ORDER BY id", (NEG,))
PRO = cur.fetchall()[0]['id']
conn.close()
primer = servicios[0]
largo = max(servicios, key=lambda s: s['duracion'])
print('primer servicio', primer, '| mas largo', largo)

# próximo día laborable con horario activo
d = dt.date.today() + dt.timedelta(days=1)
for _ in range(10):
    h = db.obtener_horarios_por_dia(NEG, d.isoformat())
    if h and h['activo']:
        break
    d += dt.timedelta(days=1)
FECHA = d.isoformat()
print('fecha de prueba', FECHA, h['hora_inicio'], '-', h['hora_fin'], 'almuerzo', h.get('almuerzo_inicio'), h.get('almuerzo_fin'))

def disponibles(servicio_id):
    return H.generar_horarios_disponibles_actualizado(NEG, PRO, FECHA, servicio_id)

def a24(h12):
    return dt.datetime.strptime(h12, '%I:%M %p').strftime('%H:%M')

antes = [a24(x) for x in disponibles(primer['id'])]

# 1) bloqueo largo: 10:00 a 13:00 (180 min), que supera con creces la duración del primer servicio
r = db.bloquear_horario_profesional(NEG, PRO, FECHA, '10:00', duracion_minutos=180, motivo='Prueba')
check('bloqueo creado', r.get('success'), str(r.get('error', '')))
despues = [a24(x) for x in disponibles(primer['id'])]
dentro = [x for x in despues if '10:00' <= x < '13:00']
check('ningún horario ofrecido dentro del bloqueo 10:00-13:00', not dentro, f'(ofrecidos dentro: {dentro})')

# 2) reservar directamente dentro del bloqueo debe fallar
cita = db.agregar_cita(NEG, PRO, '3001234567', FECHA, '11:30', primer['id'], 'Cliente Prueba')
check('agregar_cita dentro del bloqueo es rechazada', not cita, f'(cita_id={cita})')

# 3) un servicio largo que empiece antes del bloqueo y lo invada no debe ofrecerse
inv = [x for x in disponibles(largo['id']) if True]
inv24 = [a24(x) for x in inv]
choque = []
for x in inv24:
    ini = dt.datetime.strptime(x, '%H:%M'); fin = ini + dt.timedelta(minutes=largo['duracion'])
    if ini < dt.datetime.strptime('13:00', '%H:%M') and fin > dt.datetime.strptime('10:00', '%H:%M'):
        choque.append(x)
check('servicio largo no se ofrece si invade el bloqueo', not choque, f'({choque[:4]})')

# 4) un segundo bloqueo que se solapa con el primero se rechaza
r2 = db.bloquear_horario_profesional(NEG, PRO, FECHA, '11:00', duracion_minutos=60, motivo='Solapado')
check('bloqueo solapado con otro bloqueo se rechaza', not r2.get('success'), str(r2))

# 5) fuera del bloqueo siguen ofreciéndose horarios
fuera = [x for x in despues if x < '10:00' or x >= '13:00']
check('quedan horarios fuera del bloqueo', len(fuera) > 0, f'({len(fuera)} horarios)')

# 6) cita normal antes del bloqueo funciona
if '09:00' in antes:
    c2 = db.agregar_cita(NEG, PRO, '3001234567', FECHA, '09:00', primer['id'], 'Cliente Prueba')
    check('cita normal fuera del bloqueo se agenda', bool(c2))

print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
