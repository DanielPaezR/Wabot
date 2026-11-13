import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys, datetime as dt, importlib, types
os.environ.pop('DATABASE_URL', None); os.environ['SECRET_KEY'] = 'test'
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
import localizacion as L
L._consultar_bd = lambda nid: None
import app as A

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

ahora = dt.datetime.now(A.tz_negocio).replace(tzinfo=None)
def fila(i, delta_min, estado):
    t = ahora + dt.timedelta(minutes=delta_min)
    return {'id': i, 'fecha': t.date(), 'hora': t.time().replace(second=0, microsecond=0), 'estado': estado, 'servicio_nombre': 'Corte', 'precio': 25000,
            'profesional_nombre': 'Pedro', 'profesional_id': 1, 'negocio_nombre': 'Barbería', 'ya_calificada': False}
FILAS = [fila(1, 60 * 24 * 3, 'confirmado'),      # en 3 días
         fila(2, 120, 'confirmado'),               # en 2 horas
         fila(3, -90, 'confirmado'),               # hace 1h30, nunca se marcó completada
         fila(4, -60 * 24 * 5, 'completado'),
         fila(5, -60 * 24 * 9, 'cancelado'),
         fila(6, 60 * 24 * 2, 'cancelado')]        # futura pero cancelada
class Cur:
    def execute(self, *a, **k): pass
    def fetchall(self): return FILAS
class Con:
    def cursor(self, **k): return Cur()
    def close(self): pass
A.get_db_connection = lambda: Con()

c = A.app.test_client()
r = c.get('/api/cliente/mis-citas?negocio_id=1')
check('sin identificarse -> 401', r.status_code == 401)
with c.session_transaction() as s:
    s['cliente_telefono'] = '3001234567'
j = c.get('/api/cliente/mis-citas?negocio_id=1').get_json()
por_id = {x['id']: x for x in j['citas']}
check('200 y 6 citas', j['success'] and j['total'] == 6)
check('cita en 3 días y en 2 horas: es_proxima', por_id[1]['es_proxima'] and por_id[2]['es_proxima'])
check('confirmada de hace 90 min: NO es próxima y se muestra "Pasada"', not por_id[3]['es_proxima'] and por_id[3]['estado_texto'] == 'Pasada')
check('completada y cancelada no son próximas', not por_id[4]['es_proxima'] and not por_id[5]['es_proxima'] and por_id[4]['estado_texto'] == 'Completada')
check('cancelada futura NO es próxima', not por_id[6]['es_proxima'] and por_id[6]['estado_texto'] == 'Cancelada')
check('formato de fecha dd/mm/aaaa y hora HH:MM', len(por_id[1]['fecha']) == 10 and por_id[1]['fecha'][2] == '/' and len(por_id[1]['hora']) == 5)
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
