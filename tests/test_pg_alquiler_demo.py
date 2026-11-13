"""Demo de alquiler de vehículos: se crea completa, es repetible y su dueño puede entrar."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIO = _os.path.normpath(_os.path.join(_AQUI, '..', 'services', 'wabot_chat'))
from _comun import url_bd_pg as _url_bd_pg
import os, sys, importlib, types
os.environ['DATABASE_URL'] = _url_bd_pg()
os.environ['SECRET_KEY'] = 'test'
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
import alquiler as A
import alquiler_solicitud as AS
import alquiler_demo as D

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

def sql(q, p=()):
    c = db.get_db_connection(); k = c.cursor(); k.execute(q, p)
    r = k.fetchall() if k.description else None
    c.commit(); c.close(); return r

def borrar():
    for fila in sql("SELECT id FROM negocios WHERE nombre = %s", (D.NOMBRE,)) or []:
        neg = fila['id']
        for t in ('configuracion_horarios', 'plantillas_mensajes', 'usuarios', 'citas', 'servicios', 'profesionales', 'clientes', 'configuracion'):
            try:
                sql(f"DELETE FROM {t} WHERE negocio_id = %s", (neg,))
            except Exception:
                pass
        sql("DELETE FROM negocios WHERE id = %s", (neg,))
borrar()

r1 = D.crear_demo()
neg = r1['negocio_id']
check('la demo se crea', r1['nuevo'] and neg)
check('es del tipo alquiler_vehiculos', dict(db.obtener_negocio_por_id(neg))['tipo_negocio'] == 'alquiler_vehiculos')
check('no crea servicios ni profesionales de peluquería', not sql("SELECT 1 FROM servicios WHERE negocio_id = %s", (neg,)) and not sql("SELECT 1 FROM profesionales WHERE negocio_id = %s", (neg,)))
check('flota de 7 vehículos activos', len(A.listar_vehiculos(neg)) == 7)
check('el dueño entra con la clave generada', db.verificar_usuario(D.EMAIL, r1['clave']))
check('no queda el usuario por defecto con clave conocida', not sql("SELECT 1 FROM usuarios WHERE negocio_id = %s AND email LIKE 'propietario%%@negocio.com'", (neg,)))
estados = sorted(x['estado'] for x in sql("SELECT estado FROM reservas_vehiculo WHERE negocio_id = %s", (neg,)))
check('reservas de ejemplo en todos los estados', estados == ['cancelada', 'completada', 'confirmada', 'en_curso', 'pendiente', 'pendiente'], str(estados))
check('formulario base con indicaciones de abono', len(AS.campos(neg)) == 8 and 'abono' in AS.instrucciones(neg))
check('una solicitud pendiente tiene los documentos completos y otra no', sorted(x['docs_completos'] for x in sql("SELECT docs_completos FROM reservas_vehiculo WHERE negocio_id = %s AND estado = 'pendiente'", (neg,))) == [False, True])
check('la imagen de ejemplo existe', _os.path.exists(_os.path.join(_SERVICIO, 'static', 'img', 'documento-ejemplo.svg')))

r2 = D.crear_demo()
check('repetirla no duplica el negocio ni los datos', r2['negocio_id'] == neg and not r2['nuevo'] and len(A.listar_vehiculos(neg)) == 7
      and sql("SELECT COUNT(*) AS n FROM reservas_vehiculo WHERE negocio_id = %s", (neg,))[0]['n'] == 6 and sql("SELECT COUNT(*) AS n FROM negocios WHERE nombre = %s", (D.NOMBRE,))[0]['n'] == 1)
check('...y genera una clave nueva que reemplaza la anterior', r2['clave'] != r1['clave'] and db.verificar_usuario(D.EMAIL, r2['clave']) and not db.verificar_usuario(D.EMAIL, r1['clave']))
check('hay vehículos libres para reservar en los próximos días', len(A.vehiculos_disponibles(neg, __import__('datetime').date.today().isoformat() if False else (__import__('datetime').date.today() + __import__('datetime').timedelta(days=30)).isoformat(), 2)) >= 5)

borrar()
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
