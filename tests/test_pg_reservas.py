"""Reserva directa desde el perfil público (/<enlace>): enlaces cortos, horarios, reservar, "primer disponible",
doble reserva, mis citas, cancelar, redirecciones antiguas y asistente sin IA. PostgreSQL local; nunca toca producción."""
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
os.environ.pop('OPENAI_API_KEY', None)
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
import publico as P
import app as A

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

def sql(q, p=(), uno=False, todos=False):
    c = db.get_db_connection(); k = c.cursor(); k.execute(q, p)
    r = k.fetchone() if uno else (k.fetchall() if todos else None)
    c.commit(); c.close(); return r

# ── datos: un negocio de barbería propio de la prueba ──
sql("DELETE FROM citas WHERE negocio_id IN (SELECT id FROM negocios WHERE nombre = 'Barbería Prueba Reservas')")
sql("DELETE FROM profesionales WHERE negocio_id IN (SELECT id FROM negocios WHERE nombre = 'Barbería Prueba Reservas')")
sql("DELETE FROM servicios WHERE negocio_id IN (SELECT id FROM negocios WHERE nombre = 'Barbería Prueba Reservas')")
sql("DELETE FROM configuracion_horarios WHERE negocio_id IN (SELECT id FROM negocios WHERE nombre = 'Barbería Prueba Reservas')")
sql("DELETE FROM clientes WHERE negocio_id IN (SELECT id FROM negocios WHERE nombre = 'Barbería Prueba Reservas')")
sql("DELETE FROM negocios WHERE nombre = 'Barbería Prueba Reservas'")
for t in ('negocios', 'servicios', 'profesionales', 'configuracion_horarios', 'citas', 'clientes'):
    sql(f"SELECT setval(pg_get_serial_sequence('{t}','id'), (SELECT COALESCE(MAX(id),0)+1 FROM {t}), false)")
NEG = sql("""INSERT INTO negocios (nombre, telefono_whatsapp, tipo_negocio, activo, direccion)
             VALUES ('Barbería Prueba Reservas', '3001112233', 'barberia', TRUE, 'Calle 1') RETURNING id""", uno=True)['id']
sql("""INSERT INTO configuracion_horarios (negocio_id, dia_semana, activo, hora_inicio, hora_fin)
       SELECT %s, d, TRUE, '09:00', '18:00' FROM generate_series(1, 7) d""", (NEG,))
SERV = sql("INSERT INTO servicios (negocio_id, nombre, duracion, precio, activo) VALUES (%s, 'Corte', 60, 25000, TRUE) RETURNING id", (NEG,), uno=True)['id']
SERV2 = sql("INSERT INTO servicios (negocio_id, nombre, duracion, precio, activo) VALUES (%s, 'Cejas', 15, 5000, TRUE) RETURNING id", (NEG,), uno=True)['id']
PRO1 = sql("INSERT INTO profesionales (negocio_id, nombre, activo) VALUES (%s, 'Ana Uno', TRUE) RETURNING id", (NEG,), uno=True)['id']
PRO2 = sql("INSERT INTO profesionales (negocio_id, nombre, activo) VALUES (%s, 'Beto Dos', TRUE) RETURNING id", (NEG,), uno=True)['id']
# Beto solo hace cejas
sql("INSERT INTO profesional_servicios (profesional_id, servicio_id) VALUES (%s, %s)", (PRO2, SERV2))

# ── enlaces cortos ──
check('slug_corto quita "Barbería"', P.slug_corto('Barbería Nacho') == 'nacho', P.slug_corto('Barbería Nacho'))
check('slug_corto no deja enlaces de 1 letra', P.slug_corto('Barber Shop M') == 'barber-shop-m', P.slug_corto('Barber Shop M'))
check('slug reservado no es válido', not P.slug_valido('admin') and not P.slug_valido('login'))
P.asegurar_slugs(forzar=True)
SLUG = P.slug_de(NEG)
check('el negocio recibe un enlace corto', SLUG and SLUG.startswith('prueba-reservas'), SLUG)

cli = A.app.test_client()
r = cli.get('/')
check('inicio responde 200', r.status_code == 200)
r = cli.get('/' + SLUG)
check('perfil del negocio responde 200', r.status_code == 200)
html = r.get_data(as_text=True)
check('el perfil muestra servicios y botón de reserva', 'Corte' in html and 'data-reservar' in html)
check('el perfil incrusta los datos para reservar', 'window.WABOT' in html)
r = cli.get('/' + SLUG.upper())
check('el enlace en mayúsculas redirige al canónico', r.status_code == 301 and r.headers['Location'].endswith('/' + SLUG))
r = cli.get('/' + SLUG + '/ana-uno')
check('perfil del profesional por su nombre', r.status_code == 200 and 'Ana Uno' in r.get_data(as_text=True))
check('perfil inexistente da 404', cli.get('/no-existe-este-negocio').status_code == 404)
check('un segmento reservado no es un perfil', cli.get('/admin').status_code != 200 or b'WABOT' not in cli.get('/admin').data)

r = cli.get(f'/cliente/{NEG}')
check('/cliente/<id> antiguo redirige al enlace corto', r.status_code == 302 and r.headers['Location'].endswith('/' + SLUG), r.headers.get('Location'))
r = cli.get(f'/negocio/{NEG}')
check('/negocio/<id> antiguo redirige al enlace corto', r.status_code == 301 and r.headers['Location'].endswith('/' + SLUG))
r = cli.get(f'/profesional/{PRO1}/publico')
check('perfil antiguo del profesional redirige', r.status_code == 301 and r.headers['Location'].endswith(f'/{SLUG}/ana-uno'))

# ── horarios ──
dias = cli.get(f'/api/reserva/{NEG}/dias').get_json()['dias']
check('se ofrecen 21 días', len(dias) == 21)
FECHA = dias[2]['fecha']    # pasado mañana: siempre dentro del horario completo
h = cli.get(f'/api/reserva/{NEG}/horarios?servicio_id={SERV}&fecha={FECHA}').get_json()
horas = [x['hora'] for x in h['horarios']]
check('hay horarios para el corte', '09:00' in horas and '17:00' in horas and '17:15' not in horas, horas[-3:])
check('el corte solo lo ofrece Ana (Beto solo hace cejas)', all(x['pros'] == [PRO1] for x in h['horarios']))
h2 = cli.get(f'/api/reserva/{NEG}/horarios?servicio_id={SERV2}&fecha={FECHA}').get_json()
check('las cejas las ofrecen ambos', sorted(h2['horarios'][0]['pros']) == sorted([PRO1, PRO2]))

# ── reservar ──
def reservar(**extra):
    datos = {'servicio_id': SERV2, 'profesional_id': None, 'fecha': FECHA, 'hora': '10:00', 'nombre': 'laura gómez', 'telefono': '310 123 4567'}
    datos.update(extra)
    return cli.post(f'/api/reserva/{NEG}', json=datos)

r = reservar(telefono='123')
check('teléfono inválido se rechaza', r.status_code == 400 and r.get_json()['campo'] == 'telefono')
r = reservar(nombre='')
check('nombre vacío se rechaza', r.status_code == 400 and r.get_json()['campo'] == 'nombre')
r = reservar(hora='03:00')
check('hora fuera de horario se rechaza', r.status_code == 409)

r = reservar()
j = r.get_json()
check('reserva con "primer disponible" funciona', r.status_code == 200 and j['ok'], j)
check('el nombre se guarda con mayúsculas', j['cliente']['nombre'] == 'Laura Gómez')
check('el teléfono se normaliza', j['cliente']['telefono'] == '3101234567')
TOKEN = j['token']
primero = j['cita']['profesional']
r = reservar(telefono='3209998877', nombre='Otro Cliente')
j2 = r.get_json()
check('el mismo horario se asigna al otro profesional libre', j2['ok'] and j2['cita']['profesional'] != primero, (primero, j2.get('cita', {}).get('profesional')))
r = reservar(telefono='3201112222', nombre='Tercero')
check('con ambos ocupados el horario se rechaza (409)', r.status_code == 409 and r.get_json().get('ocupado'))
cli_ = sql("SELECT nombre FROM clientes WHERE negocio_id=%s AND telefono='3101234567'", (NEG,), uno=True)
check('el cliente queda registrado', cli_ and cli_['nombre'] == 'Laura Gómez')
r = reservar(servicio_id=SERV, profesional_id=PRO2, hora='11:00', telefono='3101234567')
check('no se puede reservar un servicio con quien no lo hace', r.status_code == 409)

# ── mis citas y cancelar ──
otro = A.app.test_client()
check('mis citas sin identificarse = 401', otro.get(f'/api/reserva/{NEG}/mis-citas').status_code == 401)
r = otro.get(f'/api/reserva/{NEG}/mis-citas', headers={'X-Cliente-Token': TOKEN}).get_json()
check('mis citas con el token del dispositivo', r['ok'] and len(r['proximas']) == 1 and r['proximas'][0]['puede_cancelar'])
check('token de otro negocio no sirve', otro.get(f'/api/reserva/1/mis-citas', headers={'X-Cliente-Token': TOKEN}).status_code == 401)
check('token alterado no sirve', otro.get(f'/api/reserva/{NEG}/mis-citas', headers={'X-Cliente-Token': TOKEN + 'x'}).status_code == 401)
cita_ajena = j2['cita']['id']
r = otro.post(f'/api/reserva/{NEG}/citas/{cita_ajena}/cancelar', headers={'X-Cliente-Token': TOKEN}, json={})
check('no se puede cancelar la cita de otra persona', r.status_code == 404)
r = otro.post(f'/api/reserva/{NEG}/citas/{j["cita"]["id"]}/cancelar', headers={'X-Cliente-Token': TOKEN}, json={})
check('cancelar la propia cita', r.status_code == 200 and r.get_json()['ok'])
estado = sql('SELECT estado FROM citas WHERE id=%s', (j['cita']['id'],), uno=True)['estado']
check('la cita queda cancelada', estado == 'cancelado')
h3 = cli.get(f'/api/reserva/{NEG}/horarios?servicio_id={SERV2}&fecha={FECHA}').get_json()
libre = next((x for x in h3['horarios'] if x['hora'] == '10:00'), None)
check('el horario cancelado vuelve a estar libre', libre is not None)

# ── día lleno sugiere el siguiente ──
sql("UPDATE configuracion_horarios SET activo = FALSE WHERE negocio_id = %s AND dia_semana = %s", (NEG, __import__('datetime').date.fromisoformat(FECHA).isoweekday()))
h4 = cli.get(f'/api/reserva/{NEG}/horarios?servicio_id={SERV}&fecha={FECHA}').get_json()
check('un día sin horarios sugiere el siguiente disponible', not h4['horarios'] and h4.get('siguiente', {}).get('fecha', '') > FECHA, h4.get('siguiente'))
sql("UPDATE configuracion_horarios SET activo = TRUE WHERE negocio_id = %s", (NEG,))

# ── asistente sin IA ──
r = cli.post(f'/api/reserva/{NEG}/preguntar', json={'mensajes': [{'role': 'user', 'content': '¿cuánto cuesta?'}]}).get_json()
check('asistente: precios', 'Corte' in r['respuesta'] and '25.000' in r['respuesta'], r['respuesta'][:80])
r = cli.post(f'/api/reserva/{NEG}/preguntar', json={'mensajes': [{'role': 'user', 'content': 'qué horario tienen'}]}).get_json()
check('asistente: horario', 'Lunes' in r['respuesta'])
r = cli.post(f'/api/reserva/{NEG}/preguntar', json={'mensajes': [{'role': 'user', 'content': 'quiero reservar un corte'}]}).get_json()
check('asistente: ofrece reservar el servicio', r.get('reserva', {}).get('servicio_id') == SERV, r)

# ── panel: enlace y QR ──
with cli.session_transaction() as s:
    s['usuario_id'] = 1; s['usuario_rol'] = 'propietario'; s['negocio_id'] = NEG; s['csrf_token'] = 'tok'
r = cli.get('/negocio/enlace/qr.png')
check('QR del enlace', r.status_code == 200 and r.data[:4] == b'\x89PNG')
r = cli.post('/negocio/enlace', data={'csrf_token': 'tok', 'slug': 'Mi Barbería Nueva'})
check('cambiar enlace', P.slug_de(NEG) == 'mi-barberia-nueva', P.slug_de(NEG))
cli.post('/negocio/enlace', data={'csrf_token': 'tok', 'slug': 'login'})
check('no se acepta un enlace reservado', P.slug_de(NEG) == 'mi-barberia-nueva')
check('el enlace viejo ya no responde', cli.get('/' + SLUG).status_code == 404)
anon = A.app.test_client()
check('el QR exige sesión del negocio', anon.get('/negocio/enlace/qr.png').status_code == 403)

# ── JSON incrustado seguro ──
check('json_seguro escapa </script>', '</script>' not in str(P.json_seguro({'x': '</script><b>'})))

# limpieza
sql("DELETE FROM citas WHERE negocio_id=%s", (NEG,))
sql("DELETE FROM clientes WHERE negocio_id=%s", (NEG,))
sql("DELETE FROM profesional_servicios WHERE profesional_id IN (%s, %s)", (PRO1, PRO2))
sql("DELETE FROM profesionales WHERE negocio_id=%s", (NEG,))
sql("DELETE FROM servicios WHERE negocio_id=%s", (NEG,))
sql("DELETE FROM configuracion_horarios WHERE negocio_id=%s", (NEG,))
sql("DELETE FROM negocios WHERE id=%s", (NEG,))

print('RESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
sys.exit(0 if ok else 1)
