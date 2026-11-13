"""Notificaciones push de punta a punta: pywebpush real (servicio push simulado), PostgreSQL local (puerto 55432)."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, json, base64, datetime as dt, importlib, types, threading
os.environ['DATABASE_URL'] = _url_bd_pg()
os.environ['SECRET_KEY'] = 'test'
os.environ.pop('VAPID_SUBJECT', None)
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

# claves VAPID reales de prueba
from py_vapid import Vapid
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
v = Vapid(); v.generate_keys()
priv = base64.urlsafe_b64encode(v.private_key.private_numbers().private_value.to_bytes(32, 'big')).decode().rstrip('=')
pub = base64.urlsafe_b64encode(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
os.environ['VAPID_PRIVATE_KEY'] = priv
os.environ['VAPID_PUBLIC_KEY'] = pub

import localizacion as L
import database as db
import push_notifications as P
import web_chat_handler as H
import notification_system as NS
import scheduler as SCH
import app as A

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

# --- servicio push simulado: captura cada POST de pywebpush
import requests as _rq
def Resp(code, text=''):
    r = _rq.Response(); r.status_code = code; r._content = text.encode(); r.reason = {201: 'Created', 410: 'Gone', 500: 'Server Error'}.get(code, 'X'); return r
capturas = []
comportamiento = {}     # endpoint -> código
import requests
def falso_post(url, data=None, headers=None, timeout=None, **kw):
    capturas.append({'url': url, 'headers': {k.lower(): v for k, v in dict(headers or {}).items()}, 'bytes': len(data or b'')})
    codigo = comportamiento.get(url, 201)
    return Resp(codigo, 'gone' if codigo in (404, 410) else '')
requests.post = falso_post
import pywebpush
pywebpush.requests.post = falso_post

def suscripcion_real(endpoint):
    k = ec.generate_private_key(ec.SECP256R1())
    p256 = base64.urlsafe_b64encode(k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
    auth = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip('=')
    return {'endpoint': endpoint, 'keys': {'p256dh': p256, 'auth': auth}}

def jwt_claims(auth_header):
    token = auth_header.split('t=')[1].split(',')[0]
    cuerpo = token.split('.')[1]; cuerpo += '=' * (-len(cuerpo) % 4)
    return json.loads(base64.urlsafe_b64decode(cuerpo))

def limpiar():
    c = db.get_db_connection(); k = c.cursor()
    for t in ('suscripciones_push', 'suscripciones_push_clientes', 'notificaciones_profesional', 'citas', 'conversaciones_chat'):
        try: k.execute(f'DELETE FROM {t}')
        except Exception: c.rollback()
    c.commit(); c.close()
limpiar()

# ---------- asunto VAPID
check('subject: vacío -> URL https de la app (Apple lo exige)', P._vapid_subject().startswith('https://'))
os.environ['VAPID_SUBJECT'] = 'soporte@wabot.com'
check('subject: email sin mailto -> se completa', P._vapid_subject() == 'mailto:soporte@wabot.com')
os.environ['VAPID_SUBJECT'] = 'mailto:a@b.co'
check('subject: mailto se respeta', P._vapid_subject() == 'mailto:a@b.co')
os.environ.pop('VAPID_SUBJECT')

# ---------- varios dispositivos de servicios distintos
EP = {'fcm': 'https://fcm.googleapis.com/fcm/send/AAA', 'moz': 'https://updates.push.services.mozilla.com/wpush/v2/BBB', 'apple': 'https://web.push.apple.com/CCC'}
c = db.get_db_connection(); k = c.cursor()
for e in EP.values():
    k.execute("INSERT INTO suscripciones_push (profesional_id, subscription_json, dispositivo_info, activa) VALUES (1, %s, 'test', TRUE)", (json.dumps(suscripcion_real(e)),))
c.commit(); c.close()
capturas.clear()
r = P.enviar_push_profesional(1, 'Nueva cita agendada', 'Ana - 2026-11-20 10:00', cita_id=77)
check('envía a los 3 dispositivos (antes solo al primero)', r == {'enviados': 3, 'fallidos': 0, 'suscripciones': 3}, str(r))
auds = sorted(jwt_claims(x['headers']['authorization'])['aud'] for x in capturas)
check('cada envío lleva el destino (aud) de SU servicio push', auds == sorted(['https://fcm.googleapis.com', 'https://updates.push.services.mozilla.com', 'https://web.push.apple.com']), str(auds))
check('claims con asunto válido', all(jwt_claims(x['headers']['authorization'])['sub'].startswith(('https://', 'mailto:')) for x in capturas))
check('cuerpo cifrado (aes128gcm) y TTL', all(x['bytes'] > 100 and x['headers'].get('content-encoding') == 'aes128gcm' and x['headers'].get('ttl') for x in capturas), str(capturas[0]['headers'])[:120])
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT titulo, mensaje, cita_id FROM notificaciones_profesional WHERE profesional_id=1"); filas = k.fetchall(); c.close()
check('queda UNA entrada en la lista interna', len(filas) == 1 and filas[0]['cita_id'] == 77, str([dict(f) for f in filas]))

# ---------- dispositivo caducado y error temporal
comportamiento[EP['moz']] = 410
comportamiento[EP['apple']] = 500
capturas.clear()
r = P.enviar_push_profesional(1, 'Aviso', 'x', guardar=False)
check('410 no frena a los demás; 500 cuenta como fallo', r['enviados'] == 1 and r['fallidos'] == 2, str(r))
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT subscription_json, activa FROM suscripciones_push ORDER BY id"); s = k.fetchall(); c.close()
estado = {json.loads(x['subscription_json'])['endpoint']: x['activa'] for x in s}
check('el dispositivo caducado (410) se desactiva; el del error 500 se conserva', estado[EP['moz']] is False and estado[EP['apple']] is True and estado[EP['fcm']] is True, str(estado))
comportamiento.clear()
capturas.clear()
r = P.enviar_push_profesional(1, 'Aviso', 'x', guardar=False)
check('la siguiente vez ya no se reintenta el caducado', r['suscripciones'] == 2 and len(capturas) == 2)
r = P.enviar_push_profesional(999, 'Aviso', 'x', guardar=False)
check('profesional sin dispositivos -> 0 sin error', r == {'enviados': 0, 'fallidos': 0, 'suscripciones': 0})
v0 = os.environ.pop('VAPID_PRIVATE_KEY'); capturas.clear()
r = P.enviar_push_profesional(1, 'Aviso', 'x', guardar=False)
check('sin clave VAPID: no envía y no revienta', r['enviados'] == 0 and not capturas)
os.environ['VAPID_PRIVATE_KEY'] = v0

# ---------- cliente
c = db.get_db_connection(); k = c.cursor()
k.execute("INSERT INTO suscripciones_push_clientes (negocio_id, cliente_telefono, subscription_json, activa) VALUES (1, '3001112233', %s, TRUE)", (json.dumps(suscripcion_real(EP['fcm'] + 'cli')),))
c.commit(); c.close()
capturas.clear()
check('cliente: push recibido', P.enviar_notificacion_cliente('3001112233', 1, 'Tu cita es mañana', 'a las 10', cita_id=5, url='/cliente/1?cita=5') is True and len(capturas) == 1)
check('cliente sin suscripción -> False', P.enviar_notificacion_cliente('3009998888', 1, 't', 'm') is False)

# ---------- seguridad de las rutas
cli = A.app.test_client()
sub = suscripcion_real('https://fcm.googleapis.com/fcm/send/ZZZ')
for ruta, metodo in [('/push/api/push/send', 'post'), ('/push/api/push/test-simple', 'get'), ('/push/api/push/test-cliente', 'post'), ('/api/debug/recreate-push-table', 'get'), ('/api/debug/recreate-push-table', 'post')]:
    r = getattr(cli, metodo)(ruta, json={})
    check(f'ruta peligrosa eliminada: {metodo.upper()} {ruta} -> 404', r.status_code in (404, 405), str(r.status_code))
r = cli.post('/push/api/push/subscribe', json={'subscription': sub, 'profesional_id': 2})
check('suscribir sin sesión (aunque mande profesional_id) -> 401', r.status_code == 401)
with cli.session_transaction() as s:
    s['profesional_id'] = 1; s['usuario_rol'] = 'profesional'
r = cli.post('/push/api/push/subscribe', json={'subscription': sub, 'profesional_id': 2})
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT profesional_id FROM suscripciones_push WHERE subscription_json LIKE '%ZZZ%'"); filas = k.fetchall(); c.close()
check('con sesión: se guarda para SU profesional (1), no el del cuerpo (2)', r.status_code == 200 and [f['profesional_id'] for f in filas] == [1], str(filas))
r = cli.post('/push/api/push/subscribe', json={'subscription': {'foo': 1}})
check('suscripción malformada -> 400', r.status_code == 400)
cli2 = A.app.test_client()
r = cli2.post('/api/push/subscribe-cliente', json={'subscription': sub, 'telefono': '3007770000', 'negocio_id': 1})
check('cliente sin identificarse en el chat -> 401 (no basta con mandar un teléfono)', r.status_code == 401)
with cli2.session_transaction() as s:
    s['cliente_telefono'] = '3005550000'
r = cli2.post('/api/push/subscribe-cliente', json={'subscription': sub, 'telefono': '3007770000', 'negocio_id': 1})
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT cliente_telefono FROM suscripciones_push_clientes WHERE subscription_json LIKE '%ZZZ%'"); filas = k.fetchall(); c.close()
check('cliente con sesión: se guarda con el teléfono de la SESIÓN', r.status_code == 200 and [f['cliente_telefono'] for f in filas] == ['3005550000'], str(filas))
j = cli.get('/api/push/public-key').get_json()
check('public-key entrega la clave del servidor', j['success'] and j['publicKey'] == pub)
r = cli.get('/service-worker.js')
check('service worker sin caché y con alcance raíz', r.status_code == 200 and r.headers.get('Cache-Control') == 'no-cache' and r.headers.get('Service-Worker-Allowed') == '/')
r = cli.get('/admin/reset-db'); check('/admin/reset-db sin superadmin no ejecuta nada', 'reseteada' not in r.get_data(as_text=True))

# ---------- cancelación: solo el dueño de la cita y el profesional se entera
limpiar()
c = db.get_db_connection(); k = c.cursor()
k.execute("INSERT INTO suscripciones_push (profesional_id, subscription_json, dispositivo_info, activa) VALUES (1, %s, 't', TRUE)", (json.dumps(suscripcion_real(EP['fcm'])),))
c.commit(); c.close()
d = dt.date.today() + dt.timedelta(days=2)
cita = db.agregar_cita(1, 1, '3001230000', d.isoformat(), '10:00', 1, 'Ana Pérez')
check('cita creada', bool(cita))
capturas.clear()
msg = H.procesar_cancelacion_directa('sesion-x', str(cita), 1, telefono_verificado='3009999999')
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT estado FROM citas WHERE id=%s", (cita,)); est = k.fetchone()['estado']; c.close()
check('otra persona NO puede cancelar la cita (aunque conozca el ID)', est == 'confirmado' and 'No encontré' in msg, msg[:70])
msg = H.procesar_cancelacion_directa('sesion-y', str(cita), 1)
check('sin teléfono verificado no se cancela nada', 'identificarte' in msg)
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT estado FROM citas WHERE id=%s", (cita,)); est = k.fetchone()['estado']; c.close()
check('...y la cita sigue confirmada', est == 'confirmado')
msg = H.procesar_cancelacion_directa('sesion-x', str(cita), 1, telefono_verificado='3001230000')
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT estado FROM citas WHERE id=%s", (cita,)); est = k.fetchone()['estado']
k.execute("SELECT titulo, mensaje FROM notificaciones_profesional WHERE profesional_id=1"); nots = k.fetchall(); c.close()
check('el dueño sí cancela', est == 'cancelado' and 'cancelada exitosamente' in msg)
check('el profesional recibe el aviso (lista interna + push)', len(nots) == 1 and 'Ana Pérez' in nots[0]['mensaje'] and len(capturas) == 1, str([dict(n) for n in nots]))
msg = H.procesar_cancelacion_directa('sesion-x', str(cita), 1, telefono_verificado='3001230000')
check('cancelar de nuevo: no dice "cancelada" otra vez', 'No encontré' in msg)

# ---------- recordatorio y resumen diario llegan como push al profesional
limpiar()
c = db.get_db_connection(); k = c.cursor()
k.execute("INSERT INTO suscripciones_push (profesional_id, subscription_json, dispositivo_info, activa) VALUES (1, %s, 't', TRUE)", (json.dumps(suscripcion_real(EP['fcm'])),))
c.commit(); c.close()
capturas.clear()
nid = NS.notification_system.notify_appointment_reminder(1, {'id': 9, 'hora': '10:00', 'cliente_nombre': 'Ana', 'servicio_nombre': 'Corte'}, hours_before=1)
check('recordatorio al profesional: guardado y enviado como push', bool(nid) and len(capturas) == 1)
capturas.clear()
hoy = dt.datetime.now(L.tz_reloj).date()
db.agregar_cita(1, 1, '3001230000', hoy.isoformat(), '23:00', 1, 'Ana Pérez')
SCH.appointment_scheduler.enviar_resumen_diario_profesionales(negocio_ids=[1], ahora=dt.datetime.now(L.tz_reloj))
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT titulo FROM notificaciones_profesional WHERE titulo LIKE '%Resumen%'"); r_ = k.fetchall(); c.close()
check('resumen diario: guardado y enviado como push', len(r_) >= 1 and len(capturas) >= 1, f'({len(r_)} guardados, {len(capturas)} push)')

limpiar()
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
