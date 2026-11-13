"""Renta de vehículos por días: flujo del chat, disponibilidad de varios días, IA y 'mis citas' (PostgreSQL local)."""
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
import web_chat_handler as H
import renta as R
import disponibilidad as D
from flask import Flask

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

# ---------------------------------------------------------------- lógica pura
check('plan por días: renta_autos + 1440 min', R.es_renta_por_dias('renta_autos', 1440) and R.es_renta_por_dias('renta_autos', 4320))
check('planes por horas y otros negocios no son por días', not R.es_renta_por_dias('renta_autos', 480) and not R.es_renta_por_dias('barberia', 1440) and not R.es_renta_por_dias(None, None))
check('devolución cruza fin de mes y de año', R.fecha_devolucion('2026-12-30', 3) == '2027-01-02' and R.fecha_devolucion('2026-02-27', 2) == '2026-03-01')
check('días de renta', R.dias_de_renta('2026-11-14', '2026-11-17') == 3)
check('precio total', R.precio_total(100000, 3) == 300000.0 and R.precio_total(None, 3) == 0.0)
check('etiqueta del día', R.etiqueta_dia('2026-11-14') == 'Sáb 14/11')

# ---------------------------------------------------------------- datos
c = db.get_db_connection(); k = c.cursor()
for t in ('citas', 'conversaciones_chat', 'clientes'):
    k.execute(f'DELETE FROM {t}')
k.execute("DELETE FROM servicios WHERE negocio_id = 2"); k.execute("DELETE FROM profesionales WHERE negocio_id = 2")
k.execute("DELETE FROM configuracion_horarios WHERE negocio_id = 2"); k.execute("DELETE FROM plantillas_mensajes WHERE negocio_id = 2")
k.execute("DELETE FROM negocios WHERE id = 2")
for tabla in ('negocios', 'profesionales', 'servicios', 'citas', 'configuracion_horarios', 'plantillas_mensajes'):
    k.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), GREATEST((SELECT COALESCE(MAX(id), 1) FROM {tabla}), 1))")
k.execute("INSERT INTO negocios (id, nombre, telefono_whatsapp, tipo_negocio, activo, emoji) VALUES (2, 'AutoRenta Test', 'whatsapp:+573009990002', 'renta_autos', TRUE, 'car')")
db._insertar_configuracion_horarios_para_negocio(k, 2)
k.execute("INSERT INTO profesionales (negocio_id, nombre, especialidad, activo) VALUES (2, 'Auto A', 'Sedan', TRUE), (2, 'Auto B', 'SUV', TRUE) RETURNING id")
ids = [r['id'] for r in k.fetchall()]
PA, PB = ids
k.execute("INSERT INTO servicios (negocio_id, nombre, duracion, precio, activo) VALUES (2, 'Renta por dia', 1440, 100000, TRUE), (2, 'Renta 4 horas', 240, 40000, TRUE) RETURNING id")
SD, SH = [r['id'] for r in k.fetchall()]
c.commit(); c.close()
db.crear_plantillas_personalizadas_para_negocios()

app = Flask('renta'); app.secret_key = 'x'
class Ses(dict):
    permanent = False
def decir(texto, sid, ses):
    buf = io.StringIO()
    with app.test_request_context('/'), contextlib.redirect_stdout(buf):
        return H.procesar_mensaje_chat(user_message=texto, session_id=sid, negocio_id=2, session=ses)
def opcion(r, contiene):
    for o in r.get('options') or []:
        if contiene.lower() in o['text'].lower():
            return o['value']
    raise AssertionError(f'sin opción {contiene!r} en {r.get("options")}')
def hasta_servicios(sid, ses, tel, nombre, vehiculo):
    r = decir('hola', sid, ses)
    r = decir(tel, sid, ses)
    if r['step'] == 'solicitando_nombre':
        r = decir(nombre, sid, ses)
    r = decir('1', sid, ses)       # agendar
    assert r['step'] == 'seleccionando_profesional', r
    r = decir(opcion(r, vehiculo), sid, ses)
    assert r['step'] == 'seleccionando_servicio', r
    return r

# ---------------------------------------------------------------- reserva de 3 días por el menú
ses1 = Ses()
r = hasta_servicios('c1', ses1, '3001110000', 'Cliente Uno', 'Auto A')
r = decir(opcion(r, 'por dia'), 'c1', ses1)
check('plan por día: pregunta cuántos días', r['step'] == 'seleccionando_dias' and 'cuántos días' in r['message'], r['message'][:60].replace('\n', ' '))
check('ofrece botones de días', [o['value'] for o in r['options']] == ['1', '2', '3', '5', '7', '10', '14'])
r2 = decir('45', 'c1', ses1)
check('días fuera de rango se rechazan', r2['step'] == 'seleccionando_dias' and '1 al 30' in r2['message'])
r = decir('3', 'c1', ses1)
check('muestra fechas de recogida con la devolución', r['step'] == 'seleccionando_fecha' and 'devuelves' in r['options'][0]['text'], str(r['options'][:2]))
check('muestra el total (3 x 100.000)', '$300,000' in r['message'], r['message'][:90].replace('\n', ' '))
fecha_elegida = H.conversaciones_activas['c1_2']['fechas_disponibles'][0]['fecha']
r = decir('1', 'c1', ses1)
check('pide la hora de recogida', r['step'] == 'agendando_hora' and 'recoges' in r['message'] and len(r['options']) > 1, r['message'][:80].replace('\n', ' '))
r = decir('1', 'c1', ses1)
check('resumen con recogida, devolución y total', r['step'] == 'confirmando_cita' and 'Devolución' in r['message'] and '$300,000' in r['message'] and '3 día' in r['message'], r['message'][:200].replace('\n', ' '))
r = decir('1', 'c1', ses1)
check('reserva confirmada', 'Reserva confirmada' in r['message'] and '$300,000' in r['message'], r['message'][:60].replace('\n', ' '))
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT id, fecha, fecha_fin, hora, estado, profesional_id FROM citas WHERE negocio_id = 2"); filas = k.fetchall(); c.close()
D0 = fecha_elegida; DN = R.fecha_devolucion(D0, 3)
check('guardada con fecha_fin = recogida + 3 días', len(filas) == 1 and filas[0]['fecha'] == D0 and filas[0]['fecha_fin'] == DN and filas[0]['profesional_id'] == PA, str([dict(f) for f in filas]))
CITA1 = filas[0]['id']

# ---------------------------------------------------------------- el vehículo queda ocupado todos esos días
d0 = dt.date.fromisoformat(D0)
dia = lambda n: (d0 + dt.timedelta(days=n)).isoformat()
check('libre justo antes de la recogida', db.profesional_libre_en_rango(PA, dia(-3), dia(-1)))
check('ocupado el primer día, un día intermedio y el de devolución',
      not db.profesional_libre_en_rango(PA, D0, D0) and not db.profesional_libre_en_rango(PA, dia(1), dia(1)) and not db.profesional_libre_en_rango(PA, DN, DN))
check('libre el día siguiente a la devolución', db.profesional_libre_en_rango(PA, dia(4), dia(6)))
check('el otro vehículo no se ve afectado', db.profesional_libre_en_rango(PB, D0, DN))
check('horarios por horas: ninguno dentro de la renta', D.horarios_libres(2, PA, dia(1), duracion=240) == [] and D.horarios_libres(2, PA, DN, duracion=240) == [])
check('horarios por horas: sí el día antes', len(D.horarios_libres(2, PA, dia(-1), duracion=240)) > 0 or dia(-1) < dt.date.today().isoformat())
x = db.agregar_cita(2, PA, '3005550001', dia(1), '10:00', SH, 'Intruso')
check('agregar_cita por horas dentro de la renta se rechaza', not x)
x = db.agregar_cita(2, PA, '3005550001', DN, '10:00', SH, 'Intruso')
check('...también el día de la devolución', not x)
x = db.agregar_cita(2, PA, '3005550001', dia(-2), dia(0) and '10:00', SD, 'Solapada', fecha_fin=dia(1))
check('otra renta que se solapa (termina dentro) se rechaza', not x)
x = db.agregar_cita(2, PA, '3005550001', dia(2), '10:00', SD, 'Solapada', fecha_fin=dia(5))
check('otra renta que empieza dentro se rechaza', not x)
x = db.agregar_cita(2, PA, '3005550001', dia(-1), '10:00', SD, 'Envuelve', fecha_fin=dia(6))
check('otra renta que envuelve a la existente se rechaza', not x)
x = db.agregar_cita(2, PA, '3005550001', dia(4), '10:00', SD, 'Después', fecha_fin=dia(6))
check('renta que empieza el día después de la devolución sí se acepta', bool(x))
if x:
    c = db.get_db_connection(); k = c.cursor(); k.execute("UPDATE citas SET estado='cancelado' WHERE id=%s", (x,)); c.commit(); c.close()

# ---------------------------------------------------------------- otro cliente, mismo vehículo: no se le ofrecen fechas ocupadas
ses2 = Ses()
r = hasta_servicios('c2', ses2, '3002220000', 'Cliente Dos', 'Auto A')
r = decir(opcion(r, 'por dia'), 'c2', ses2)
r = decir('2', 'c2', ses2)
ofrecidas = [f['fecha'] for f in H.conversaciones_activas['c2_2']['fechas_disponibles']]
solapa = [f for f in ofrecidas if dt.date.fromisoformat(f) <= dt.date.fromisoformat(DN) and dt.date.fromisoformat(f) + dt.timedelta(days=2) >= d0]
check('no se ofrecen fechas cuya renta (2 días) se solape con la existente', ofrecidas and not solapa, f'ofrecidas={ofrecidas} solapan={solapa}')
# y el otro vehículo sí está libre en esas fechas
ses3 = Ses()
r = hasta_servicios('c3', ses3, '3003330000', 'Cliente Tres', 'Auto B')
r = decir(opcion(r, 'por dia'), 'c3', ses3)
r = decir('3', 'c3', ses3)
ofrecidas_b = [f['fecha'] for f in H.conversaciones_activas['c3_2']['fechas_disponibles']]
check('el otro vehículo sí ofrece la fecha de la renta existente', D0 in ofrecidas_b or d0 < dt.date.today(), str(ofrecidas_b[:3]))

# ---------------------------------------------------------------- planes por horas siguen como siempre
ses4 = Ses()
r = hasta_servicios('c4', ses4, '3004440000', 'Cliente Cuatro', 'Auto B')
r = decir(opcion(r, '4 horas'), 'c4', ses4)
check('plan por horas: va directo a elegir fecha (sin preguntar días)', r['step'] == 'seleccionando_fecha' and 'dias_renta' not in H.conversaciones_activas['c4_2'], r['step'])

# ---------------------------------------------------------------- días cerrados: no se puede devolver
c = db.get_db_connection(); k = c.cursor(); k.execute("UPDATE configuracion_horarios SET activo = FALSE WHERE negocio_id = 2 AND dia_semana = 7"); c.commit(); c.close()
cands = R.candidatas_recogida(2, PB, 1, dt.date.today(), dt.datetime.now(), maximo=40)
malas = [x for x in cands if dt.date.fromisoformat(x['fecha']).isoweekday() in (6, 7)]   # sábado (devolvería domingo) y domingo
check('no se ofrece recoger el domingo ni el sábado de una renta de 1 día (devolución en domingo cerrado)', cands and not malas, str([x['mostrar'] for x in malas]))
c = db.get_db_connection(); k = c.cursor(); k.execute("UPDATE configuracion_horarios SET activo = TRUE WHERE negocio_id = 2 AND dia_semana = 7"); c.commit(); c.close()

# ---------------------------------------------------------------- cancelar libera el vehículo
msg = H.procesar_cancelacion_directa('c1', str(CITA1), 2, telefono_verificado='3001110000')
check('cancelar la renta', 'cancelada exitosamente' in msg)
check('el vehículo queda libre otra vez', db.profesional_libre_en_rango(PA, D0, DN))

# ---------------------------------------------------------------- IA
args = {'profesional_nombre': 'Auto A', 'servicio_nombre': 'Renta por dia', 'fecha': dia(10), 'hora': '10:00'}
ses_ia = Ses()
decir('hola', 'ia1', ses_ia); decir('3006660000', 'ia1', ses_ia); decir('Cliente IA', 'ia1', ses_ia)
with app.test_request_context('/'), contextlib.redirect_stdout(io.StringIO()):
    m = H.ia_confirmar_agendamiento(dict(args), 2, '3006660000', 'Cliente IA')
check('IA: sin días pregunta cuántos días', 'cuántos días' in m, m[:50])
with app.test_request_context('/'), contextlib.redirect_stdout(io.StringIO()):
    m = H.ia_confirmar_agendamiento(dict(args, dias=4), 2, '3006660000', 'Cliente IA')
check('IA: resumen de la reserva con total', 'RESUMEN DE TU RESERVA' in m and '$400,000' in m and 'Devolución' in m, m.replace('\n', ' | ')[:160])
with app.test_request_context('/'), contextlib.redirect_stdout(io.StringIO()):
    m = H.ia_agendar_cita(dict(args), 2, '3006660000', 'Cliente IA')
check('IA: agendar sin días pregunta', 'cuántos días' in m)
with app.test_request_context('/'), contextlib.redirect_stdout(io.StringIO()):
    m = H.ia_agendar_cita(dict(args, dias=4), 2, '3006660000', 'Cliente IA')
c = db.get_db_connection(); k = c.cursor(); k.execute("SELECT fecha, fecha_fin FROM citas WHERE cliente_telefono='3006660000' AND estado='confirmado'"); f = k.fetchall(); c.close()
check('IA: agenda la renta con fecha_fin', 'Reserva' in m or 'reserva' in m, m.replace('\n', ' | ')[:120])
check('IA: guardada con 4 días', len(f) == 1 and f[0]['fecha_fin'] == R.fecha_devolucion(dia(10), 4), str([dict(x) for x in f]))
with app.test_request_context('/'), contextlib.redirect_stdout(io.StringIO()):
    m = H.ia_agendar_cita(dict(args, fecha=dia(12), dias=2), 2, '3006660000', 'Cliente IA')
check('IA: fechas que chocan con otra renta se rechazan', 'no está disponible' in m, m[:80])

# ---------------------------------------------------------------- "mis citas": devolución, total y "En curso"
c = db.get_db_connection(); k = c.cursor(); k.execute("DELETE FROM citas WHERE negocio_id = 2"); c.commit(); c.close()
hoy = dt.date.today()
en_curso = db.agregar_cita(2, PB, '3007770000', (hoy - dt.timedelta(days=1)).isoformat(), '08:00', SD, 'Cliente Curso', fecha_fin=(hoy + dt.timedelta(days=2)).isoformat())
futura = db.agregar_cita(2, PA, '3007770000', (hoy + dt.timedelta(days=10)).isoformat(), '09:00', SD, 'Cliente Curso', fecha_fin=(hoy + dt.timedelta(days=12)).isoformat())
check('rentas de prueba creadas', bool(en_curso) and bool(futura))
sys.modules.setdefault('flask_login', sys.modules['flask_login'])
os.environ['DATABASE_URL'] = _url_bd_pg()
import app as A
cli = A.app.test_client()
with cli.session_transaction() as s:
    s['cliente_telefono'] = '3007770000'
j = cli.get('/api/cliente/mis-citas?negocio_id=2').get_json()
por = {x['id']: x for x in j['citas']}
check('mis citas: renta en curso', por[en_curso]['estado_texto'] == 'En curso' and por[en_curso]['es_proxima'], str(por[en_curso]))
check('mis citas: devolución y total (3 días x 100.000)', por[en_curso]['fecha_fin'] and por[en_curso]['precio'] == 300000.0, f"{por[en_curso]['fecha_fin']} {por[en_curso]['precio']}")
check('mis citas: renta futura próxima de 2 días = 200.000', por[futura]['es_proxima'] and por[futura]['precio'] == 200000.0 and por[futura]['estado_texto'] == 'Confirmada')

# limpieza
c = db.get_db_connection(); k = c.cursor()
for t in ('citas', 'conversaciones_chat', 'clientes'):
    k.execute(f'DELETE FROM {t}')
k.execute("DELETE FROM servicios WHERE negocio_id = 2"); k.execute("DELETE FROM profesionales WHERE negocio_id = 2")
k.execute("DELETE FROM configuracion_horarios WHERE negocio_id = 2"); k.execute("DELETE FROM plantillas_mensajes WHERE negocio_id = 2")
k.execute("DELETE FROM negocios WHERE id = 2")
c.commit(); c.close()
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
