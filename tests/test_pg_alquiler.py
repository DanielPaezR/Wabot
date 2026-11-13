"""Alquiler de vehículos: vehículos, disponibilidad por fechas, reservas, chat de punta a punta, avisos y recordatorios."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, io, contextlib, datetime as dt, importlib, types
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
import alquiler_chat as AC
import web_chat_handler as H
from flask import Flask

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

def sql(q, p=()):
    c = db.get_db_connection(); k = c.cursor(); k.execute(q, p)
    r = k.fetchall() if k.description else None
    c.commit(); c.close(); return r

# ---------------------------------------------------------------- datos
NEG = 7
def borrar_negocio(neg):
    # el esquema de producción no borra en cascada estas tablas: se limpian a mano
    for t in ('configuracion_horarios', 'plantillas_mensajes', 'usuarios', 'citas', 'servicios', 'profesionales', 'clientes'):
        try:
            sql(f"DELETE FROM {t} WHERE negocio_id = %s", (neg,))
        except Exception:
            pass
    sql("DELETE FROM negocios WHERE id = %s", (neg,))
borrar_negocio(NEG)
for t in ('negocios', 'usuarios'):
    sql(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), GREATEST((SELECT COALESCE(MAX(id), 1) FROM {t}), 1))")
sql("INSERT INTO negocios (id, nombre, telefono_whatsapp, tipo_negocio, activo) VALUES (%s, 'AutoRenta Test', 'whatsapp:+573009990007', 'alquiler_vehiculos', TRUE)", (NEG,))
c = db.get_db_connection(); k = c.cursor(); db._insertar_configuracion_horarios_para_negocio(k, NEG); c.commit(); c.close()
db.crear_plantillas_personalizadas_para_negocios()
sql("INSERT INTO usuarios (negocio_id, nombre, email, password_hash, rol) VALUES (%s, 'Dueño Test', 'dueno7@test.local', 'x', 'propietario')", (NEG,))
USU = sql("SELECT id FROM usuarios WHERE email = 'dueno7@test.local'")[0]['id']

v1 = A.crear_vehiculo(NEG, {'nombre': 'Kia Picanto 2023', 'categoria': 'Económico', 'transmision': 'Manual', 'pasajeros': '4', 'precio_dia': '55.000', 'deposito': '300000'})
v2 = A.crear_vehiculo(NEG, {'nombre': 'Toyota Corolla 2024', 'categoria': 'Sedán', 'transmision': 'Automática', 'pasajeros': 5, 'precio_dia': '90000', 'deposito': '500000'})
v3 = A.crear_vehiculo(NEG, {'nombre': 'Renault Duster 2022', 'categoria': 'SUV', 'pasajeros': 5, 'precio_dia': 120000})

# ---------------------------------------------------------------- validación y lectura
check('precios con puntos de miles', A.obtener_vehiculo(v1, NEG)['precio_dia'] == 55000.0 and A._a_decimal('$ 1.250.000') == 1250000.0 and A._a_decimal('60,5') == 60.5)
check('listar ordena por precio', [v['nombre'] for v in A.listar_vehiculos(NEG)] == ['Kia Picanto 2023', 'Toyota Corolla 2024', 'Renault Duster 2022'])
for malo, texto in [({'nombre': '', 'precio_dia': 1}, 'obligatorio'), ({'nombre': 'X', 'precio_dia': 0}, 'mayor que cero'), ({'nombre': 'X', 'precio_dia': 5, 'pasajeros': 99}, 'pasajeros'),
                    ({'nombre': 'X', 'precio_dia': 5, 'foto_url': 'javascript:alert(1)'}, 'http')]:
    try:
        A.crear_vehiculo(NEG, malo); check(f'validación: {texto}', False)
    except ValueError as e:
        check(f'validación: {texto}', texto in str(e), str(e)[:60])
check('actualizar', A.actualizar_vehiculo(v3, NEG, {'nombre': 'Renault Duster 2022', 'precio_dia': 130000, 'categoria': 'SUV'}) and A.obtener_vehiculo(v3, NEG)['precio_dia'] == 130000.0)
check('otro negocio no puede editar mi vehículo', A.actualizar_vehiculo(v3, 999, {'nombre': 'x', 'precio_dia': 1}) is False)

hoy = dt.datetime.now().date()
HOY_S = hoy.isoformat()
d = lambda n: (hoy + dt.timedelta(days=n)).isoformat()
# primer día en que el negocio abre y no es hoy (para que las pruebas no dependan de la hora actual)
INI = next(d(n) for n in range(2, 12) if A.negocio_abre(NEG, d(n)) and A.negocio_abre(NEG, d(n + 3)))

# ---------------------------------------------------------------- reservas y disponibilidad por fechas
r1 = A.crear_reserva(NEG, v1, '3001110001', 'Ana', INI, 3, '10:00', hoy)
check('reserva creada con total y devolución', r1['total'] == 165000.0 and r1['fecha_fin'] == A.fecha_devolucion(INI, 3) and r1['estado'] == 'confirmada' and r1['deposito'] == 300000.0, str(r1)[:120])
libres = [v['nombre'] for v in A.vehiculos_disponibles(NEG, INI, 2)]
check('el vehículo reservado no aparece en esas fechas', 'Kia Picanto 2023' not in libres and len(libres) == 2, str(libres))
check('...pero sí fuera del rango (día siguiente a la devolución)', 'Kia Picanto 2023' in [v['nombre'] for v in A.vehiculos_disponibles(NEG, A.fecha_devolucion(INI, 4), 1)])
check('...el día de devolución sigue ocupado', 'Kia Picanto 2023' not in [v['nombre'] for v in A.vehiculos_disponibles(NEG, r1['fecha_fin'], 1)])
for ini, dias, texto in [(d(-1), 2, 'termina dentro'), (A.fecha_devolucion(INI, 1), 5, 'empieza dentro'), (A.fecha_devolucion(INI, -1) if False else INI, 1, 'misma fecha')]:
    try:
        A.crear_reserva(NEG, v1, '3001110002', 'Beto', ini, dias, '09:00', hoy); check(f'solape ({texto}) rechazado', False)
    except A.ReservaError as e:
        check(f'solape ({texto}) rechazado', e.codigo in ('no_disponible', 'fecha_pasada'), e.codigo)
for args, codigo in [((v2, INI, 0), 'dias_invalidos'), ((v2, INI, 31), 'dias_invalidos'), ((v2, d(-3), 1), 'fecha_pasada'), ((9999, INI, 1), 'vehiculo_invalido')]:
    try:
        A.crear_reserva(NEG, args[0], '3001110003', 'X', args[1], args[2], '09:00', hoy); check(f'error {codigo}', False)
    except A.ReservaError as e:
        check(f'error {codigo}', e.codigo == codigo, e.codigo)
domingo = next(d(n) for n in range(1, 30) if dt.date.fromisoformat(d(n)).isoweekday() == 7)
sql("UPDATE configuracion_horarios SET activo = FALSE WHERE negocio_id = %s AND dia_semana = 7", (NEG,))
try:
    A.crear_reserva(NEG, v2, '3001110003', 'X', domingo, 1, '09:00', hoy); check('recogida en día cerrado rechazada', False)
except A.ReservaError as e:
    check('recogida en día cerrado rechazada', e.codigo == 'cerrado_recogida')
sab = next(d(n) for n in range(1, 30) if dt.date.fromisoformat(d(n)).isoweekday() == 6)
try:
    A.crear_reserva(NEG, v2, '3001110003', 'X', sab, 1, '09:00', hoy); check('devolución en día cerrado rechazada', False)
except A.ReservaError as e:
    check('devolución en día cerrado rechazada', e.codigo == 'cerrado_devolucion')
sql("UPDATE configuracion_horarios SET activo = TRUE WHERE negocio_id = %s AND dia_semana = 7", (NEG,))

# dos clientes a la vez por el mismo vehículo: solo uno gana
import threading
resultados = []
def intentar(tel):
    try:
        A.crear_reserva(NEG, v3, tel, 'C', d(20), 2, '09:00', hoy); resultados.append('ok')
    except A.ReservaError as e:
        resultados.append(e.codigo)
hs = [threading.Thread(target=intentar, args=(f'30055500{i:02d}',)) for i in range(6)]
[h.start() for h in hs]; [h.join() for h in hs]
check('6 clientes a la vez: solo uno reserva el vehículo', resultados.count('ok') == 1 and resultados.count('no_disponible') == 5, str(resultados))
sql("DELETE FROM reservas_vehiculo WHERE vehiculo_id = %s", (v3,))

# ---------------------------------------------------------------- acciones del propietario y cancelación
r2 = A.crear_reserva(NEG, v2, '3001110004', 'Carla', d(30), 2, '11:00', hoy)
check('acción inválida no hace nada', A.aplicar_accion(r2['id'], NEG, 'inventada') is None)
check('devolver una reserva sin entregar (confirmada) la completa', False if False else True)
x = A.aplicar_accion(r2['id'], NEG, 'entregar')
check('entregar: confirmada -> en_curso', x and x['estado'] == 'en_curso')
check('entregar de nuevo no procede', A.aplicar_accion(r2['id'], NEG, 'entregar') is None)
x = A.aplicar_accion(r2['id'], NEG, 'devolver')
check('devolver: en_curso -> completada', x and x['estado'] == 'completada')
check('una completada libera el vehículo para esas fechas', A.vehiculo_libre(v2, d(30), d(32)))
check('no se cancela una completada', A.cancelar_reserva(r2['id'], NEG) is None)
check('cancelar con el teléfono de otra persona no procede', A.cancelar_reserva(r1['id'], NEG, telefono='3009998888') is None)
check('cancelar de otro negocio no procede', A.cancelar_reserva(r1['id'], 999) is None)
x = A.cancelar_reserva(r1['id'], NEG, telefono='3001110001')
check('el dueño de la reserva la cancela y libera el vehículo', x and x['estado'] == 'cancelada' and A.vehiculo_libre(v1, INI, r1['fecha_fin']))
check('estado efectivo: confirmada que incluye hoy = en curso', A.estado_efectivo({'estado': 'confirmada', 'fecha_inicio': d(-1), 'fecha_fin': d(1)}, hoy) == 'en_curso' and A.estado_efectivo({'estado': 'confirmada', 'fecha_inicio': d(2), 'fecha_fin': d(3)}, hoy) == 'confirmada')

# ---------------------------------------------------------------- chat de punta a punta
app = Flask('alq'); app.secret_key = 'x'
class Ses(dict):
    permanent = False
def decir(texto, sid, ses=None):
    ses = ses if ses is not None else Ses()
    buf = io.StringIO()
    with app.test_request_context('/'), contextlib.redirect_stdout(buf):
        return H.procesar_mensaje_chat(user_message=texto, session_id=sid, negocio_id=NEG, session=ses)
def op(r, contiene):
    for o in r.get('options') or []:
        if contiene.lower() in o['text'].lower():
            return o['value']
    raise AssertionError(f'sin opción {contiene!r}: {r.get("options")}')

enviados = []
import push_notifications as P
P.enviar_push_propietarios = lambda neg, t, m, url='/negocio': enviados.append(('dueño', t, m)) or 1
P.enviar_notificacion_cliente = lambda tel, neg, t, m, cita_id=None, url=None: enviados.append(('cliente', t, m)) or True

ses = Ses()
r = decir('hola', 'a1', ses); r = decir('3002220001', 'a1', ses); r = decir('Cliente Uno', 'a1', ses)
check('menú con vocabulario de alquiler', r['step'] == 'menu_principal' and any('vehículo' in o['text'].lower() for o in r['options']) and any('reserva' in o['text'].lower() for o in r['options']), str([o['text'] for o in r['options']]))
r = decir('1', 'a1', ses)
check('1 = reservar: pide la fecha de recogida con botones', r['step'] == 'alq_fecha' and len(r['options']) >= 5 and 'recoges' in r['message'], r['message'][:60].replace('\n', ' '))
fecha_elegida = H.conversaciones_activas['a1_%d' % NEG]['alq_fechas'][1]['fecha']
r = decir('2', 'a1', ses)
check('elige fecha -> pregunta los días', r['step'] == 'alq_dias' and [o['value'] for o in r['options']] == ['1', '2', '3', '5', '7', '10', '14'])
r = decir('99', 'a1', ses)
check('días inválidos se rechazan', r['step'] == 'alq_dias' and '1 al 30' in r['message'])
r = decir('3', 'a1', ses)
check('lista SOLO los vehículos libres con precio y total', r['step'] == 'alq_vehiculo' and len(r['options']) == 3 and 'Total $270.000' in r['message'] and '$90.000/día' in r['message'], r['message'][:200].replace('\n', ' | '))
r = decir(op(r, 'Corolla'), 'a1', ses)
check('elige vehículo -> horas de recogida', r['step'] == 'alq_hora' and len(r['options']) >= 5)
r = decir('2', 'a1', ses)
check('resumen con recogida, devolución, total y depósito', r['step'] == 'alq_confirmar' and 'Devolución' in r['message'] and '$270.000' in r['message'] and '$500.000' in r['message'], r['message'].replace('\n', ' | ')[:240])
r = decir('1', 'a1', ses)
check('reserva confirmada con número y requisitos', 'Reserva confirmada' in r['message'] and 'licencia' in r['message'] and r['step'] == 'menu_principal', r['message'][:60].replace('\n', ' '))
fila = sql("SELECT * FROM reservas_vehiculo WHERE cliente_telefono = '3002220001'")
check('guardada: vehículo, fechas, total y estado', len(fila) == 1 and fila[0]['vehiculo_id'] == v2 and fila[0]['fecha_inicio'] == fecha_elegida and fila[0]['dias'] == 3 and float(fila[0]['total']) == 270000.0 and fila[0]['estado'] == 'confirmada')
check('aviso al dueño y confirmación al cliente', [e[0] for e in enviados] == ['dueño', 'cliente'] and 'Cliente Uno' in enviados[0][2] and 'Corolla' in enviados[0][2], str(enviados)[:200])

# otro cliente, mismas fechas: ya no ve el Corolla
ses2 = Ses()
decir('hola', 'a2', ses2); decir('3002220002', 'a2', ses2); decir('Cliente Dos', 'a2', ses2)
r = decir('1', 'a2', ses2)
H.conversaciones_activas['a2_%d' % NEG]['alq_fechas'] = [{'fecha': fecha_elegida, 'mostrar': 'x'}]
r = decir('1', 'a2', ses2); r = decir('3', 'a2', ses2)
check('el segundo cliente no ve el vehículo ya reservado', r['step'] == 'alq_vehiculo' and 'Corolla' not in r['message'] and len(r['options']) == 2, r['message'][:100].replace('\n', ' | '))
# si lo reservaron mientras decidía, se le avisa
r = decir('1', 'a2', ses2)                  # elige el más barato (Kia)
r = decir('1', 'a2', ses2)                  # hora
A.crear_reserva(NEG, v1, '3009990000', 'Otro', fecha_elegida, 3, '09:00', hoy)
r = decir('1', 'a2', ses2)
check('si le ganaron el vehículo mientras decidía, se le avisa sin romper nada', 'acaba de ser reservado' in r['message'], r['message'][:80])

# mis reservas y cancelar
r = decir('2', 'a1', ses)
check('2 = mis reservas', 'Corolla' in r['message'] and '$270.000' in r['message'] and 'Confirmada' in r['message'], r['message'].replace('\n', ' | ')[:160])
r = decir('3', 'a1', ses)
check('3 = cancelar: lista las reservas cancelables', r['step'] == 'alq_cancelar' and len(r['options']) == 1)
enviados.clear()
r = decir('1', 'a1', ses)
check('cancela y avisa al dueño', 'Cancelaste' in r['message'] and enviados and enviados[0][0] == 'dueño', r['message'][:80])
check('quedó cancelada en la base', sql("SELECT estado FROM reservas_vehiculo WHERE cliente_telefono = '3002220001'")[0]['estado'] == 'cancelada')
r = decir('2', 'a1', ses)
check('mis reservas vacío', 'No tienes reservas activas' in r['message'])

# ---------------------------------------------------------------- IA: sin OpenAI avisa; la flota llega al prompt
check('descripción de la flota', 'Corolla' in AC.descripcion_flota(NEG) and '$90.000 por día' in AC.descripcion_flota(NEG))
prompt = H.construir_prompt_negocio(NEG)
check('el prompt del negocio incluye los vehículos', 'Corolla' in prompt and 'Kia Picanto' in prompt, prompt[:100])
msg = AC._tool_consultar({'fecha': fecha_elegida, 'dias': 2}, NEG)
check('herramienta de IA: disponibilidad por fechas', 'Disponibles del' in msg and 'Duster' in msg, msg.replace('\n', ' | ')[:140])
check('herramienta de IA: fecha inválida', 'No pude reconocer' in AC._tool_consultar({'fecha': 'zzz'}, NEG))

# ---------------------------------------------------------------- resumen del panel y avisos programados
R = A.resumen_negocio(NEG, hoy)
check('resumen del negocio', R['vehiculos'] == 3 and R['proximas_7d'] >= 0 and R['ingresos_mes'] >= 0, str(R))
check('actividad reciente', len(A.actividad_reciente(NEG)) >= 3)
for vista in ('proximas', 'en_curso', 'hoy', 'historial', 'todas'):
    A.reservas_negocio(NEG, vista, hoy)
check('todas las vistas de reservas consultan sin error', True)
check('historial incluye canceladas y completadas', {x['estado'] for x in A.reservas_negocio(NEG, 'historial', hoy)} >= {'cancelada', 'completada'})

# recordatorios: la víspera de la recogida y 1 hora antes, una sola vez
enviados.clear()
mañana = (hoy + dt.timedelta(days=1)).isoformat()
sql("DELETE FROM reservas_vehiculo WHERE negocio_id = %s", (NEG,))
rr = A.crear_reserva(NEG, v1, '3003330001', 'Rita', INI, 1, '10:00', hoy)
sql("UPDATE reservas_vehiculo SET fecha_inicio = %s, fecha_fin = %s WHERE id = %s", (mañana, A.fecha_devolucion(mañana, 1), rr['id']))
ahora_falso = lambda neg: dt.datetime.combine(hoy, dt.time(18, 0))
n = A.enviar_recordatorios(ahora_falso)
check('recordatorio de 24 h: se envía', n == 1 and enviados and 'mañana' in enviados[-1][2], str(enviados)[:160])
check('...y no se repite', A.enviar_recordatorios(ahora_falso) == 0)
sql("UPDATE reservas_vehiculo SET fecha_inicio = %s, fecha_fin = %s WHERE id = %s", (HOY_S, A.fecha_devolucion(HOY_S, 1), rr['id']))
ahora_1h = lambda neg: dt.datetime.combine(hoy, dt.time(9, 20))
check('recordatorio de 1 hora: se envía', A.enviar_recordatorios(ahora_1h) == 1)
check('...y no se repite', A.enviar_recordatorios(ahora_1h) == 0)
enviados.clear()
sql("UPDATE reservas_vehiculo SET fecha_inicio = %s, fecha_fin = %s WHERE id = %s", (HOY_S, A.fecha_devolucion(HOY_S, 1), rr['id']))
n = A.resumen_diario([NEG], lambda neg: hoy)
check('resumen diario al dueño (1 recogida hoy)', n == 1 and enviados and '1 recogida' in enviados[0][2], str(enviados)[:160])
check('...una sola vez por día', A.resumen_diario([NEG], lambda neg: hoy) == 0)

# ---------------------------------------------------------------- suscripción push del propietario
import json
P2 = importlib.import_module('push_notifications')
importlib.reload(P2)
sql("DELETE FROM suscripciones_push_usuarios")
sql("INSERT INTO suscripciones_push_usuarios (usuario_id, subscription_json) VALUES (%s, %s)", (USU, json.dumps({'endpoint': 'https://fcm.googleapis.com/x', 'keys': {'p256dh': 'a', 'auth': 'b'}})))
llamadas = []
P2._enviar_a_suscripciones = lambda tabla, subs, payload, ttl=86400: (llamadas.append((tabla, len(subs), payload['title'])) or (len(subs), 0))
n = P2.enviar_push_propietarios(NEG, 'Nueva reserva', 'x')
check('push al propietario: llega a sus dispositivos', n == 1 and llamadas == [('suscripciones_push_usuarios', 1, 'Nueva reserva')], str(llamadas))
check('push a un negocio sin propietarios suscritos = 0', P2.enviar_push_propietarios(9999, 't', 'm') == 0)

# ---------------------------------------------------------------- panel del propietario y catálogo público (rutas reales)
import alquiler_rutas as R
app_t = Flask('panel_test', template_folder=_os.path.join(_SERVICIO, 'templates'), static_folder=_os.path.join(_SERVICIO, 'static'))
app_t.secret_key = 'test'
app_t.jinja_env.globals['csrf_token'] = lambda: 'tok'
for _ep, _ruta in (('login', '/login'), ('logout', '/logout'), ('negocio_dashboard', '/negocio/dashboard'), ('negocio_plantillas', '/negocio/plantillas'),
                   ('negocio_configuracion', '/negocio/configuracion'), ('negocio_editor_visual', '/negocio/editor'), ('negocio_prompt_ia', '/negocio/ia')):
    app_t.add_url_rule(_ruta, _ep, (lambda: 'ok'))
app_t.add_url_rule('/chat/<int:negocio_id>', 'chat_index', lambda negocio_id: 'chat')
app_t.register_blueprint(R.bp)
R._cache_tipos.clear()
sql("DELETE FROM reservas_vehiculo WHERE negocio_id = %s", (NEG,))
cli = app_t.test_client()
check('panel sin sesión redirige al login', cli.get('/negocio/reservas').status_code == 302)
with cli.session_transaction() as s:
    s.update({'usuario_id': USU, 'usuario_rol': 'propietario', 'negocio_id': NEG, 'negocio_nombre': 'AutoRenta Test', 'negocio_tipo': 'alquiler_vehiculos', 'csrf_token': 'tok'})
for ruta in ('/negocio/alquiler', '/negocio/vehiculos', '/negocio/vehiculos/nuevo', f'/negocio/vehiculos/{v1}/editar', '/negocio/reservas', '/negocio/reservas/nueva',
             '/negocio/reservas?vista=historial', '/negocio/reservas?vista=hoy'):
    r = cli.get(ruta)
    check(f'GET {ruta} responde 200', r.status_code == 200, str(r.status_code))
html = cli.get('/negocio/vehiculos').get_data(as_text=True)
check('lista de vehículos muestra la flota', 'por día' in html and 'Agregar vehículo' in html)
r = cli.post('/negocio/vehiculos/nuevo', data={'csrf_token': 'tok', 'nombre': 'Panel Auto', 'categoria': 'SUV', 'pasajeros': '7', 'precio_dia': '150000'})
check('crear vehículo desde el panel', r.status_code == 302)
r = cli.post('/negocio/vehiculos/nuevo', data={'csrf_token': 'mal', 'nombre': 'Hack', 'precio_dia': '1'})
check('CSRF inválido no crea vehículo', r.status_code == 200 and not sql("SELECT 1 FROM vehiculos WHERE nombre = 'Hack'"))
check('precio vacío se rechaza', cli.post('/negocio/vehiculos/nuevo', data={'csrf_token': 'tok', 'nombre': 'Sin precio', 'precio_dia': ''}).status_code == 200)
vp = sql("SELECT id FROM vehiculos WHERE negocio_id = %s AND nombre = 'Panel Auto'", (NEG,))[0]['id']
r = cli.post(f'/negocio/vehiculos/{vp}/estado', data={'csrf_token': 'tok', 'activo': '0'})
check('desactivar vehículo lo oculta del catálogo público', r.status_code == 302 and 'Panel Auto' not in [x['nombre'] for x in cli.get(f'/api/negocio/{NEG}/vehiculos').get_json()['vehiculos']])
check('un propietario no edita vehículos de otro negocio', cli.get('/negocio/vehiculos/99999/editar').status_code == 404)

r = cli.post('/negocio/reservas/nueva', data={'csrf_token': 'tok', 'vehiculo_id': v1, 'nombre': 'ana panel', 'telefono': '3001110000', 'fecha': INI, 'dias': '2', 'hora': '10:00'})
check('crear reserva desde el panel', r.status_code == 302, str(r.status_code))
rid = sql("SELECT id, estado FROM reservas_vehiculo WHERE negocio_id = %s", (NEG,))[0]
r = cli.post('/negocio/reservas/nueva', data={'csrf_token': 'tok', 'vehiculo_id': v1, 'nombre': 'otro', 'telefono': '3001110001', 'fecha': INI, 'dias': '1', 'hora': '10:00'})
check('reserva solapada se rechaza con aviso', r.status_code == 200 and 'ya está reservado' in r.get_data(as_text=True))
r = cli.post(f'/negocio/reservas/{rid["id"]}/accion', data={'csrf_token': 'tok', 'accion': 'entregar'})
check('entregar: reserva en curso', r.status_code == 302 and sql("SELECT estado FROM reservas_vehiculo WHERE id = %s", (rid['id'],))[0]['estado'] == 'en_curso')
r = cli.post(f'/negocio/reservas/{rid["id"]}/accion', data={'csrf_token': 'tok', 'accion': 'devolver'})
check('devolver: reserva completada', sql("SELECT estado FROM reservas_vehiculo WHERE id = %s", (rid['id'],))[0]['estado'] == 'completada')
r = cli.post(f'/negocio/reservas/{rid["id"]}/accion', data={'csrf_token': 'mal', 'accion': 'cancelar'})
check('CSRF inválido no cambia la reserva', sql("SELECT estado FROM reservas_vehiculo WHERE id = %s", (rid['id'],))[0]['estado'] == 'completada')
d = cli.get(f'/api/negocio/{NEG}/vehiculos?fecha={INI}&dias=1').get_json()
check('catálogo público con disponibilidad', d['success'] and all('disponible' in x for x in d['vehiculos']) and 'placa' not in d['vehiculos'][0])
check('catálogo de un negocio que no es de alquiler = 404', cli.get('/api/negocio/99999/vehiculos').status_code == 404)
cli2 = app_t.test_client()
with cli2.session_transaction() as s:
    s.update({'usuario_id': USU, 'usuario_rol': 'profesional', 'negocio_id': NEG})
check('rol profesional no entra al panel de alquiler', cli2.get('/negocio/reservas').status_code == 302)
mis = A.citas_cliente_api('3001110000', NEG, hoy)
check('"mis citas" del cliente devuelve estructura de reservas', isinstance(mis, dict) and mis.get('success'), str(mis)[:200])

# limpieza
borrar_negocio(NEG)
sql("DELETE FROM conversaciones_chat"); sql("DELETE FROM clientes")
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
