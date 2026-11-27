"""Agenda del equipo (/agenda): permisos de barbero y dueño, el día, huecos libres, cambiar estado, cita sin reserva,
bloqueos, notificaciones y textos de recordatorio. PostgreSQL local; nunca toca producción."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, importlib, types
os.environ['DATABASE_URL'] = _url_bd_pg()
os.environ['SECRET_KEY'] = 'test'
os.environ['VAPID_PRIVATE_KEY'] = 'x'; os.environ['VAPID_PUBLIC_KEY'] = 'y'
os.environ.pop('SENTRY_DSN', None)
sys.path.insert(0, _SERVICIO)
for nombre in ['flask_login', 'cloudinary', 'cloudinary.uploader', 'openai']:
    try:
        importlib.import_module(nombre)
    except ImportError:
        m = types.ModuleType(nombre)
        if nombre == 'flask_login':
            class _LM:
                def __init__(self, *a, **k): pass
                def __getattr__(self, n): return lambda *a, **k: (lambda f: f)
            m.LoginManager = _LM
            for n in ['login_user', 'logout_user', 'login_required', 'current_user']:
                setattr(m, n, (lambda f=None, *a, **k: f))
        if nombre == 'cloudinary':
            m.config = lambda **k: None
        sys.modules[nombre] = m
if 'cloudinary.uploader' in sys.modules and not hasattr(sys.modules['cloudinary'], 'uploader'):
    sys.modules['cloudinary'].uploader = sys.modules['cloudinary.uploader']

import datetime as dt
import database as db
import localizacion
import notification_system as NS
import app as A

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

def sql(q, p=(), uno=False, todos=False):
    c = db.get_db_connection(); k = c.cursor(); k.execute(q, p)
    r = k.fetchone() if uno else (k.fetchall() if todos else None)
    c.commit(); c.close(); return r

NOMBRE = 'Barbería Prueba Agenda'
viejo = sql("SELECT id FROM negocios WHERE nombre = %s", (NOMBRE,), uno=True)
if viejo:
    for t in ('citas', 'clientes', 'configuracion_horarios', 'servicios'):
        sql(f"DELETE FROM {t} WHERE negocio_id = %s", (viejo['id'],))
    sql("DELETE FROM notificaciones_profesional WHERE profesional_id IN (SELECT id FROM profesionales WHERE negocio_id = %s)", (viejo['id'],))
    sql("DELETE FROM profesionales WHERE negocio_id = %s", (viejo['id'],))
    sql("DELETE FROM negocios WHERE id = %s", (viejo['id'],))
for t in ('negocios', 'servicios', 'profesionales', 'configuracion_horarios', 'citas', 'clientes', 'notificaciones_profesional'):
    sql(f"SELECT setval(pg_get_serial_sequence('{t}','id'), (SELECT COALESCE(MAX(id),0)+1 FROM {t}), false)")

NEG = sql("INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, activo) VALUES (%s, '3001112233', 'barberia', TRUE) RETURNING id", (NOMBRE,), uno=True)['id']
sql("""INSERT INTO configuracion_horarios (negocio_id, dia_semana, activo, hora_inicio, hora_fin)
       SELECT %s, d, TRUE, '09:00', '18:00' FROM generate_series(1, 7) d""", (NEG,))
SERV = sql("INSERT INTO servicios (negocio_id, nombre, duracion, precio, activo) VALUES (%s, 'Corte', 60, 25000, TRUE) RETURNING id", (NEG,), uno=True)['id']
ANA = sql("INSERT INTO profesionales (negocio_id, nombre, activo) VALUES (%s, 'Ana Uno', TRUE) RETURNING id", (NEG,), uno=True)['id']
BETO = sql("INSERT INTO profesionales (negocio_id, nombre, activo) VALUES (%s, 'Beto Dos', TRUE) RETURNING id", (NEG,), uno=True)['id']
FECHA = (localizacion.ahora_en(NEG).date() + dt.timedelta(days=2)).isoformat()
C1 = db.agregar_cita(NEG, ANA, '3101234567', FECHA, '10:00', SERV, 'Laura Gómez')
C2 = db.agregar_cita(NEG, BETO, '3209998877', FECHA, '11:00', SERV, 'Pedro Pérez')
check('citas de prueba creadas', C1 and C2)

def cliente(rol, pro=None):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['usuario_id'] = 99; s['usuario_rol'] = rol; s['negocio_id'] = NEG; s['usuario_nombre'] = 'Prueba'
        if pro:
            s['profesional_id'] = pro
    return c

anon = A.app.test_client()
check('la agenda pide iniciar sesión', anon.get('/agenda').status_code == 302)
check('la API de la agenda pide iniciar sesión', anon.get('/api/agenda/dia').status_code == 401)

ana = cliente('profesional', ANA)
dueno = cliente('propietario')
check('la agenda del barbero carga', ana.get('/agenda').status_code == 200)
r = dueno.get('/agenda')
check('la agenda del dueño carga', r.status_code == 200 and b'window.AGENDA' in r.data)

d = ana.get(f'/api/agenda/dia?fecha={FECHA}').get_json()
check('el barbero solo ve sus citas', [c['cliente'] for c in d['citas']] == ['Laura Gómez'], [c['cliente'] for c in d['citas']])
check('el resumen suma lo esperado', d['resumen']['citas'] == 1 and '25.000' in d['resumen']['esperado_txt'])
huecos = d['huecos'][str(ANA)] if str(ANA) in d['huecos'] else d['huecos'].get(ANA)
check('huecos libres alrededor de la cita', huecos and huecos[0]['desde'] == '09:00' and huecos[0]['hasta'] == '10:00'
      and huecos[1]['desde'] == '11:00', huecos)
check('la cita trae el recordatorio por WhatsApp', d['citas'][0].get('recordatorio', '').startswith('https://wa.me/573101234567?text='))
dd = dueno.get(f'/api/agenda/dia?fecha={FECHA}').get_json()
check('el dueño ve a todo el equipo', len(dd['citas']) == 2 and len(dd['equipo']) == 2)
sem = ana.get('/api/agenda/semana').get_json()
check('la tira de días marca las citas', any(x['fecha'] == FECHA and x['citas'] == 1 for x in sem['dias']))

# permisos entre barberos
r = ana.post(f'/api/agenda/citas/{C2}/estado', json={'estado': 'completado'})
check('un barbero no puede tocar la cita de otro', r.status_code == 404)
r = ana.post('/api/agenda/citas', json={'profesional_id': BETO, 'servicio_id': SERV, 'fecha': FECHA, 'hora': '15:00', 'nombre': 'Intruso'})
check('un barbero no puede agendarle a otro', r.status_code == 400)

# estados
r = ana.post(f'/api/agenda/citas/{C1}/estado', json={'estado': 'completado'})
check('marcar como atendida', r.status_code == 200 and sql('SELECT estado FROM citas WHERE id=%s', (C1,), uno=True)['estado'] == 'completado')
d = ana.get(f'/api/agenda/dia?fecha={FECHA}').get_json()
check('lo atendido cuenta como cobrado', '25.000' in d['resumen']['cobrado_txt'])
check('estado inválido se rechaza', ana.post(f'/api/agenda/citas/{C1}/estado', json={'estado': 'borrado'}).status_code == 400)
r = dueno.post(f'/api/agenda/citas/{C2}/estado', json={'estado': 'cancelado'})
check('el dueño cancela cualquier cita', r.status_code == 200 and sql('SELECT estado FROM citas WHERE id=%s', (C2,), uno=True)['estado'] == 'cancelado')
r = dueno.post(f'/api/agenda/citas/{C2}/estado', json={'estado': 'confirmado'})
check('deshacer: vuelve a pendiente', sql('SELECT estado FROM citas WHERE id=%s', (C2,), uno=True)['estado'] == 'confirmado')

# cita sin reserva
h = ana.get(f'/api/agenda/horarios?profesional_id={ANA}&servicio_id={SERV}&fecha={FECHA}').get_json()
check('horas libres para agendar', h['ok'] and '11:00' in [x['hora'] for x in h['horarios']] and '10:00' not in [x['hora'] for x in h['horarios']])
r = ana.post('/api/agenda/citas', json={'profesional_id': ANA, 'servicio_id': SERV, 'fecha': FECHA, 'hora': '12:00', 'nombre': 'kevin mejía'})
check('agendar a alguien sin teléfono', r.status_code == 200 and r.get_json()['ok'])
fila = sql('SELECT cliente_nombre, cliente_telefono FROM citas WHERE id=%s', (r.get_json()['id'],), uno=True)
check('el nombre queda capitalizado y sin teléfono', fila['cliente_nombre'] == 'Kevin Mejía' and fila['cliente_telefono'] == '')
r = ana.post('/api/agenda/citas', json={'profesional_id': ANA, 'servicio_id': SERV, 'fecha': FECHA, 'hora': '12:30', 'nombre': 'Choque'})
check('no se permite cruzar citas', r.status_code == 409)
r = dueno.post('/api/agenda/citas', json={'profesional_id': BETO, 'servicio_id': SERV, 'fecha': FECHA, 'hora': '14:00', 'nombre': 'Del Dueño', 'telefono': '3112223344'})
check('el dueño agenda a cualquier barbero', r.status_code == 200)
avisos = sql("SELECT titulo FROM notificaciones_profesional WHERE profesional_id = %s ORDER BY id DESC LIMIT 1", (BETO,), uno=True)
check('el barbero recibe el aviso de la cita que le agendó el dueño', avisos and avisos['titulo'] == 'Nueva cita')

# bloqueos
r = ana.post('/api/agenda/bloqueos', json={'profesional_id': ANA, 'fecha': FECHA, 'hora': '13:00', 'duracion': 60, 'motivo': 'Almuerzo'})
check('bloquear un rato', r.status_code == 200)
d = ana.get(f'/api/agenda/dia?fecha={FECHA}').get_json()
bloqueo = next((c for c in d['citas'] if c['estado'] == 'bloqueo'), None)
check('el bloqueo aparece en la agenda', bloqueo and bloqueo['motivo'] == 'Almuerzo' and bloqueo['fin'] == '14:00')
h = ana.get(f'/api/agenda/horarios?profesional_id={ANA}&servicio_id={SERV}&fecha={FECHA}').get_json()
check('nadie puede reservar dentro del bloqueo', '13:00' not in [x['hora'] for x in h['horarios']])
check('otro barbero no quita mi bloqueo', cliente('profesional', BETO).delete(f"/api/agenda/bloqueos/{bloqueo['id']}").status_code == 404)
check('quitar el bloqueo', ana.delete(f"/api/agenda/bloqueos/{bloqueo['id']}").status_code == 200)

# notificaciones
NS.notification_system.notify_appointment_reminder(ANA, {'id': C1, 'hora': '10:00', 'cliente_nombre': 'Laura Gómez', 'servicio_nombre': 'Corte'}, 24)
n = ana.get('/api/agenda/notificaciones').get_json()
check('la campana muestra el recordatorio', n['ok'] and n['sin_leer'] >= 1 and n['notificaciones'][0]['titulo'] == 'Mañana tienes cita', n['notificaciones'][:1])
check('texto de recordatorio limpio', n['notificaciones'][0]['mensaje'] == 'Laura Gómez · Corte · mañana a las 10:00 a. m.', n['notificaciones'][0]['mensaje'])
check('la notificación trae "hace cuánto"', n['notificaciones'][0]['cuando'] in ('Ahora',) or n['notificaciones'][0]['cuando'].startswith('Hace'))
fc = sql("SELECT fecha_creacion FROM notificaciones_profesional ORDER BY id DESC LIMIT 1", uno=True)['fecha_creacion']
check('la fecha de la notificación es la de hoy (no 2025-12-12)', str(fc) != '2025-12-12', fc)
nd = dueno.get('/api/agenda/notificaciones').get_json()
check('el dueño ve las notificaciones de su equipo', any(x['profesional'] == 'Ana Uno' for x in nd['notificaciones']))
dueno.post('/api/agenda/notificaciones/leidas', json={})
check('el dueño no marca como leídas las del barbero', ana.get('/api/agenda/notificaciones').get_json()['sin_leer'] >= 1)
ana.post('/api/agenda/notificaciones/leidas', json={})
check('el barbero marca las suyas como leídas', ana.get('/api/agenda/notificaciones').get_json()['sin_leer'] == 0)

check('manifest para instalar la agenda', anon.get('/manifest-agenda.json').get_json()['start_url'] == '/agenda')
with ana.session_transaction() as s:
    pass
r = A.app.test_client().get('/app')
check('/app sin sesión lleva al inicio', r.status_code == 302)

# limpieza
sql("DELETE FROM notificaciones_profesional WHERE profesional_id IN (%s, %s)", (ANA, BETO))
for t in ('citas', 'clientes', 'configuracion_horarios', 'servicios', 'profesionales'):
    sql(f"DELETE FROM {t} WHERE negocio_id = %s", (NEG,))
sql("DELETE FROM negocios WHERE id = %s", (NEG,))

print('RESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
sys.exit(0 if ok else 1)
