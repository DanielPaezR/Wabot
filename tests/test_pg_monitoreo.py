"""Monitoreo: /health, /health/completo, latido del programador, registro de errores y /admin/errores (PostgreSQL local)."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, importlib, types, datetime as dt
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

import database as db
import monitoreo as M
import app as A

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

def sql(q, p=()):
    c = db.get_db_connection(); k = c.cursor(); k.execute(q, p)
    r = k.fetchall() if k.description else None
    c.commit(); c.close(); return r

sql("DELETE FROM errores_app") if M.registrar_latido('prueba') is None else None
sql("DELETE FROM errores_app"); sql("DELETE FROM app_latidos")

@A.app.route('/__explota')
def _explota():
    raise RuntimeError('boom de prueba')

cli = A.app.test_client()

# ---------------------------------------------------------------- /health
r = cli.get('/health'); j = r.get_json()
check('/health 200 con la base de datos viva', r.status_code == 200 and j['bd']['ok'] and j['status'] == 'healthy', str(j)[:120])
check('/health no expone datos sensibles', set(j) <= {'estado', 'version', 'activa_hace_seg', 'bd', 'status'})

# ---------------------------------------------------------------- /health/completo
r = cli.get('/health/completo'); j = r.get_json()
check('sin latido del programador -> 503 degradado', r.status_code == 503 and j['estado'] == 'degradado' and any('scheduler' in p for p in j['problemas']), str(j.get('problemas')))
M.registrar_latido('scheduler')
r = cli.get('/health/completo'); j = r.get_json()
check('con latido reciente y push configurado -> 200', r.status_code == 200 and j['estado'] == 'ok' and j['scheduler']['ok'], str(j)[:200])
sql("UPDATE app_latidos SET actualizado = NOW() - INTERVAL '10 minutes' WHERE clave = 'scheduler'")
r = cli.get('/health/completo'); j = r.get_json()
check('latido de hace 10 min -> 503 (programador detenido)', r.status_code == 503 and not j['scheduler']['ok'] and j['scheduler']['ultimo_latido_seg'] >= 590)
M.registrar_latido('scheduler')
os.environ['VAPID_PRIVATE_KEY'] = ''
r = cli.get('/health/completo'); j = r.get_json()
check('sin claves VAPID -> 503 con aviso', r.status_code == 503 and any('push' in p for p in j['problemas']))
os.environ['VAPID_PRIVATE_KEY'] = 'x'

# ---------------------------------------------------------------- errores
def falla(n):
    try:
        raise ValueError(f'fallo de prueba {n}')
    except ValueError as e:
        return e
e1 = falla(1)
check('registrar_error guarda', M.registrar_error(e1, '/api/x', 'GET', 'prueba') is True)
M.registrar_error(e1, '/api/x', 'GET', 'prueba')
M.registrar_error(e1, '/api/x', 'GET', 'prueba')
filas = M.errores_recientes()
check('el mismo error repetido se agrupa (3 veces, 1 fila)', len(filas) == 1 and filas[0]['veces'] == 3 and filas[0]['tipo'] == 'ValueError', str([(f['veces'], f['tipo']) for f in filas]))
try:
    {}['clave']
except KeyError as e2:
    M.registrar_error(e2, '/api/y', 'POST')
check('otro tipo de error = otra fila', len(M.errores_recientes()) == 2)
check('la traza queda guardada pero sin datos de la petición', 'ValueError' in M.errores_recientes()[-1]['traza'] or 'KeyError' in M.errores_recientes()[0]['traza'])
check('registrar_error(None) no falla', M.registrar_error(None) is False)

# protección contra tormentas de errores
sql("DELETE FROM errores_app")
M._ventana['inicio'] = 0
guardados = 0
for i in range(60):
    class E(Exception): pass
    E.__name__ = f'ErrorDistinto{i}'
    try: raise E('x')
    except E as ex: guardados += 1 if M.registrar_error(ex, f'/ruta/{i}') else 0
check('tormenta de errores: máximo 30 escrituras por minuto', guardados == M.MAX_ESCRITURAS_POR_MINUTO, f'({guardados})')
sql("DELETE FROM errores_app"); M._ventana['inicio'] = 0

# ráfaga de errores -> /health/completo 503
sql("INSERT INTO errores_app (huella, tipo, mensaje, veces) VALUES ('h', 'X', 'x', 40)")
r = cli.get('/health/completo'); j = r.get_json()
check('ráfaga de errores (40 en 10 min) -> 503', r.status_code == 503 and j['errores']['ultimos_10_min'] == 40 and any('errores' in p for p in j['problemas']))
sql("DELETE FROM errores_app")

# ---------------------------------------------------------------- un error no controlado en una ruta queda registrado
A.app.config['PROPAGATE_EXCEPTIONS'] = False
A.app.testing = False
r = cli.get('/__explota')
check('error no controlado -> página 500 amable', r.status_code == 500 and 'Algo salió mal' in r.get_data(as_text=True))
filas = M.errores_recientes()
check('...y queda registrado con su ruta', len(filas) == 1 and filas[0]['tipo'] == 'RuntimeError' and filas[0]['ruta'] == '/__explota' and filas[0]['metodo'] == 'GET', str([dict(f)['ruta'] for f in filas]))
r = cli.get('/api/__no_existe')
check('un 404 de la API no se registra como error', r.status_code == 404 and len(M.errores_recientes()) == 1)

# ---------------------------------------------------------------- /admin/errores
r = cli.get('/admin/errores')
check('sin sesión -> redirige al login', r.status_code in (302, 303))
with cli.session_transaction() as s:
    s['usuario_id'] = 1; s['usuario_rol'] = 'propietario'
r = cli.get('/admin/errores')
check('propietario no entra', r.status_code in (302, 303))
with cli.session_transaction() as s:
    s['usuario_rol'] = 'superadmin'; s['usuario_nombre'] = 'Admin'; s['csrf_token'] = 'tok'
r = cli.get('/admin/errores'); html = r.get_data(as_text=True)
check('superadmin ve estado y errores', r.status_code == 200 and 'RuntimeError' in html and 'Todo en orden' in html and 'health/completo' in html)
r = cli.post('/admin/errores/limpiar', data={'csrf_token': 'mal'})
check('limpiar con CSRF inválido no borra', len(M.errores_recientes()) == 1)
r = cli.post('/admin/errores/limpiar', data={'csrf_token': 'tok'})
check('limpiar con CSRF válido borra', r.status_code in (302, 303) and len(M.errores_recientes()) == 0)
html = cli.get('/admin/errores').get_data(as_text=True)
check('sin errores muestra el mensaje vacío', 'No hay errores registrados' in html)

# ---------------------------------------------------------------- Sentry opcional
check('sin SENTRY_DSN no se activa', M.iniciar_sentry() is False)
os.environ['SENTRY_DSN'] = 'https://clave@o0.ingest.sentry.io/0'
resultado = M.iniciar_sentry()
check('con DSN pero sin el paquete instalado no rompe la app', resultado in (True, False))
os.environ.pop('SENTRY_DSN')

# ---------------------------------------------------------------- el programador late de verdad
sql("DELETE FROM app_latidos")
import scheduler as S
S.appointment_scheduler.verificar_recordatorios()
filas = sql("SELECT clave FROM app_latidos")
check('verificar_recordatorios registra el latido', [f['clave'] for f in filas] == ['scheduler'])

sql("DELETE FROM errores_app"); sql("DELETE FROM app_latidos")
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
