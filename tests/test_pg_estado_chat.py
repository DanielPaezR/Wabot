"""Estado de conversación persistido + ProxyFix, contra PostgreSQL local (puerto 55432)."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, io, contextlib, datetime as dt, decimal, importlib, types
os.environ['DATABASE_URL'] = _url_bd_pg()
os.environ['SECRET_KEY'] = 'test'
os.environ.pop('WHATSAPP_WEBHOOK_SECRET', None)
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

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

import estado_conversacion as E
import database as db
import web_chat_handler as H

# --- codec
tz = dt.timezone(dt.timedelta(hours=-5))
est = {'estado': 'x', 'timestamp': dt.datetime(2026, 11, 13, 10, 5, tzinfo=tz), 'f': dt.date(2026, 11, 14), 'h': dt.time(9, 30),
       'p': decimal.Decimal('15000.50'), 'lista': [1, 2, {'a': 'b'}], 'tupla': (1, 2), 'texto': 'ñandú ✅', 'n': None, 'b': True}
rt = E.decodificar(E.codificar(est))
check('codec: ida y vuelta conserva datetime con zona, date, time, Decimal', rt['timestamp'] == est['timestamp'] and rt['f'] == est['f'] and rt['h'] == est['h'] and rt['p'] == est['p'] and rt['texto'] == est['texto'] and rt['tupla'] == [1, 2])
check('codec: la fecha con zona horaria sigue siendo comparable con otra con zona', (dt.datetime.now(tz) - rt['timestamp']).total_seconds() != 0)

# --- base de datos
k = 'chat:prueba_1'
E.borrar(k)
check('cargar: no existe -> (None, True)', E.cargar(k) == (None, True))
check('guardar', E.guardar(k, est))
got, disp = E.cargar(k)
check('cargar: lo guardado', disp and got['p'] == est['p'] and got['timestamp'] == est['timestamp'])
conn = db.get_db_connection(); cur = conn.cursor()
cur.execute("UPDATE conversaciones_chat SET actualizado = NOW() - INTERVAL '45 minutes' WHERE clave=%s", (k,)); conn.commit(); conn.close()
check('TTL: a los 45 min ya no se carga (TTL 30)', E.cargar(k, ttl_minutos=30) == (None, True))
check('TTL: sí se carga con TTL 24h', E.cargar(k, ttl_minutos=1440)[0] is not None)
check('guardar de nuevo reemplaza (upsert)', E.guardar(k, {'estado': 'y'}) and E.cargar(k)[0] == {'estado': 'y'})
E.borrar(k)
check('borrar', E.cargar(k) == (None, True))
check('tipo no serializable no rompe: guardar devuelve False', E.guardar(k, {'x': object()}) is False)

# --- el chat sobrevive a un "reinicio" (se vacía la memoria del proceso)
c = db.get_db_connection(); kk = c.cursor(); kk.execute("DELETE FROM citas"); kk.execute("DELETE FROM conversaciones_chat"); c.commit(); c.close()
from flask import Flask
app = Flask('e2e'); app.secret_key = 'x'
class Ses(dict):
    permanent = False
SID = 'web_persist_1'
def decir(texto, ses):
    buf = io.StringIO()
    with app.test_request_context('/'), contextlib.redirect_stdout(buf):
        r = H.procesar_mensaje_chat(user_message=texto, session_id=SID, negocio_id=1, session=ses)
    return r
ses = Ses()
decir('hola', ses); decir('3001234567', ses); decir('Juan Pérez', ses)
r = decir('1', ses)   # menú -> elegir profesional
check('antes del reinicio: eligiendo profesional', r['step'] == 'seleccionando_profesional', r['step'])
H.conversaciones_activas.clear()          # <- simula un redeploy / otro proceso
ses2 = Ses()                               # y una sesión de Flask nueva (sin nada en memoria)
r = decir('1', ses2)
check('tras el reinicio la conversación continúa en el siguiente paso (servicio)', r['step'] == 'seleccionando_servicio', r['step'])
r = decir('1', ses2); check('...y luego fecha', r['step'] == 'seleccionando_fecha', r['step'])
H.conversaciones_activas.clear()
r = decir('1', ses2); check('segundo reinicio: sigue (horarios)', r['step'] == 'agendando_hora', r['step'])
H.conversaciones_activas.clear()
r = decir('1', ses2); check('tercer reinicio: llega a confirmar', r['step'] == 'confirmando_cita', r['step'])
H.conversaciones_activas.clear()
r = decir('1', ses2); check('cuarto reinicio: la cita se confirma', 'Confirmada' in r['message'] or 'Confirmada'.lower() in r['message'].lower(), r['message'][:60].replace('\n', ' '))
c = db.get_db_connection(); kk = c.cursor(); kk.execute("SELECT count(*) AS n FROM citas WHERE estado='confirmado'"); n = kk.fetchone()['n']; c.close()
check('la cita quedó en la BD', n == 1, f'({n})')
c = db.get_db_connection(); kk = c.cursor(); kk.execute("SELECT count(*) AS n FROM conversaciones_chat WHERE clave LIKE 'chat:%'"); n = kk.fetchone()['n']; c.close()
check('al terminar la conversación se borra su estado', n == 0, f'(quedan {n})')

# dos clientes a la vez no se mezclan
def decir_id(texto, sid, ses):
    buf = io.StringIO()
    with app.test_request_context('/'), contextlib.redirect_stdout(buf):
        return H.procesar_mensaje_chat(user_message=texto, session_id=sid, negocio_id=1, session=ses)
a, b = Ses(), Ses()
decir_id('hola', 'A', a); decir_id('hola', 'B', b)
decir_id('3001111111', 'A', a); decir_id('3002222222', 'B', b)
decir_id('Ana', 'A', a); decir_id('Beto', 'B', b)
decir_id('1', 'A', a)
H.conversaciones_activas.clear()
rb = decir_id('2', 'B', b)   # B: "Ver mis citas" desde el menú, mientras A ya está eligiendo profesional
ra = decir_id('1', 'A', a)
check('dos conversaciones simultáneas no se mezclan', rb['step'] != 'seleccionando_servicio' and ra['step'] == 'seleccionando_servicio', f"B={rb['step']} A={ra['step']}")

# --- ProxyFix
import app as A
A.app.add_url_rule('/__ip', 'ip_prueba', lambda: __import__('flask').request.remote_addr)
cli = A.app.test_client()
check('sin proxy: IP del socket', cli.get('/__ip', environ_overrides={'REMOTE_ADDR': '10.1.1.1'}).get_data(as_text=True) == '10.1.1.1')
r = cli.get('/__ip', headers={'X-Forwarded-For': '203.0.113.5'}, environ_overrides={'REMOTE_ADDR': '10.1.1.1'}).get_data(as_text=True)
check('con X-Forwarded-For (Railway): IP real del visitante', r == '203.0.113.5', r)
r = cli.get('/__ip', headers={'X-Forwarded-For': '6.6.6.6, 203.0.113.9'}, environ_overrides={'REMOTE_ADDR': '10.1.1.1'}).get_data(as_text=True)
check('IP falsificada por el cliente no se acepta (se toma la que añadió el proxy)', r == '203.0.113.9', r)
A.rate_limit_cache.clear()
res = [A.check_rate_limit('203.0.113.5', max_requests=3) for _ in range(5)]
check('rate limit por IP: 3 permitidos y luego bloqueado', res == [True, True, True, False, False])
check('rate limit: otra IP no se ve afectada', A.check_rate_limit('198.51.100.7', max_requests=3))

c = db.get_db_connection(); kk = c.cursor(); kk.execute("DELETE FROM citas"); kk.execute("DELETE FROM conversaciones_chat"); c.commit(); c.close()
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
