"""Disponibilidad: lógica pura + flujos contra PostgreSQL local (puerto 55432). Nunca toca producción."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
from _comun import url_bd_pg as _url_bd_pg
import os, sys, datetime as dt, importlib, types
os.environ['DATABASE_URL'] = _url_bd_pg()
os.environ['SECRET_KEY'] = 'test'
os.environ.pop('WHATSAPP_WEBHOOK_SECRET', None)
sys.path.insert(0, _SERVICIO)
import disponibilidad as D

ok = True
def check(nombre, cond, extra=''):
    global ok; ok &= bool(cond); print(('OK   ' if cond else 'FALLO'), nombre, extra)

# ---------- lógica pura ----------
dia = {'activo': True, 'hora_inicio': '09:00', 'hora_fin': '12:00', 'almuerzo_inicio': None, 'almuerzo_fin': None}
f = '2026-11-20'

check('a_minutos: time', D.a_minutos(dt.time(9, 30)) == 570)
check('a_minutos: HH:MM:SS', D.a_minutos('09:30:00') == 570)
check('a_minutos: 12h PM', D.a_minutos('2:15 PM') == 14 * 60 + 15)
check('a_minutos: 12:00 AM = 0', D.a_minutos('12:00 AM') == 0)
check('a_minutos: basura -> None', D.a_minutos('hola') is None and D.a_minutos(None) is None)

libres = D.calcular_horarios_libres(dia, [], [], 60, f)
check('sin citas: 09:00 a 11:00 (servicio 60 min, paso 15)', libres[0] == '09:00' and libres[-1] == '11:00' and len(libres) == 9, str(libres))

# cita con la hora como objeto time (lo que devuelve PostgreSQL) y como texto
for hora in (dt.time(10, 0), '10:00', '10:00:00', '10:00 AM'):
    l = D.calcular_horarios_libres(dia, [{'hora': hora, 'duracion': 30, 'estado': 'confirmado'}], [], 30, f)
    check(f'cita 10:00-10:30 ({type(hora).__name__} {hora}) quita 09:45,10:00,10:15', '09:45' not in l and '10:00' not in l and '10:15' not in l and '09:30' in l and '10:30' in l, str(l[:8]))

l = D.calcular_horarios_libres(dia, [{'hora': '10:00', 'duracion': 30, 'estado': 'cancelado'}], [], 30, f)
check('cita cancelada no ocupa', '10:00' in l)

l = D.calcular_horarios_libres(dia, [{'hora': '10:00', 'duracion': 120, 'estado': 'bloqueado'}], [], 30, f)
check('bloqueo de 2h ocupa las 2h', not [x for x in l if '10:00' <= x < '12:00'] and '09:30' in l, str(l))

l = D.calcular_horarios_libres(dia, [{'hora': '10:00', 'duracion': 0, 'estado': 'confirmado'}], [], 15, f)
check('cita con duración 0 ocupa al menos 15 min', '10:00' not in l and '10:15' in l)

alm = dict(dia, hora_fin='15:00', almuerzo_inicio='12:00', almuerzo_fin='13:00')
l = D.calcular_horarios_libres(alm, [], [], 60, f)
check('almuerzo: ningún servicio lo invade', '11:15' not in l and '12:00' not in l and '12:45' not in l and '11:00' in l and '13:00' in l, str(l))

rec = [{'activo': True, 'dias_semana_lista': [5], 'hora_inicio': '10:00', 'hora_fin': '11:00', 'fecha_inicio': None, 'fecha_fin': None},
       {'activo': True, 'dias_semana_lista': [5], 'hora_inicio': '09:00', 'hora_fin': '09:30', 'fecha_inicio': None, 'fecha_fin': None},
       {'activo': False, 'dias_semana_lista': [5], 'hora_inicio': '11:00', 'hora_fin': '12:00'}]
l = D.calcular_horarios_libres(dia, [], rec, 30, f)  # 2026-11-20 es viernes (5)
check('bloqueos recurrentes: se aplican TODOS los activos', '09:00' not in l and '10:00' not in l and '10:30' not in l and '09:30' in l and '11:00' in l, str(l))
l = D.calcular_horarios_libres(dia, [], rec, 30, '2026-11-21')  # sábado
check('bloqueo recurrente de viernes no afecta el sábado', '10:00' in l)
rec2 = [{'activo': True, 'dias_semana_lista': [5], 'hora_inicio': '10:00', 'hora_fin': '11:00', 'fecha_inicio': '2026-12-01', 'fecha_fin': None}]
check('bloqueo recurrente fuera de su rango de fechas no aplica', '10:00' in D.calcular_horarios_libres(dia, [], rec2, 30, f))

# hoy: margen de 30 minutos
tz = dt.timezone(dt.timedelta(hours=-5))
ahora = dt.datetime(2026, 11, 20, 10, 10, tzinfo=tz)
l = D.calcular_horarios_libres(dia, [], [], 30, f, ahora=ahora)
check('hoy 10:10 -> primer horario 10:45 (margen 30 min)', l and l[0] == '10:45', str(l[:3]))
l = D.calcular_horarios_libres(dia, [], [], 30, '2026-11-21', ahora=ahora)
check('mañana no se ve afectado por la hora actual', l[0] == '09:00')
check('día inactivo -> sin horarios', D.calcular_horarios_libres(dict(dia, activo=False), [], [], 30, f) == [])
check('servicio más largo que la jornada -> sin horarios', D.calcular_horarios_libres(dia, [], [], 240, f) == [])
check('duración inválida -> sin horarios', D.calcular_horarios_libres(dia, [], [], None, f) == [])

# ---------- contra PostgreSQL ----------
import database as db
import web_chat_handler as H
NEG, PRO = 1, 1
SERV = 1  # 45 min
def limpiar():
    c = db.get_db_connection(); k = c.cursor()
    k.execute("DELETE FROM citas")
    try:
        k.execute("DELETE FROM bloqueos_recurrentes")
    except Exception:
        c.rollback()
    c.commit(); c.close()
limpiar()
d = dt.date.today() + dt.timedelta(days=1)
while not (db.obtener_horarios_por_dia(NEG, d.isoformat()) or {}).get('activo'):
    d += dt.timedelta(days=1)
FECHA = d.isoformat()

# una cita real: el chat y la API dejan de ofrecer esas horas
cid = db.agregar_cita(NEG, PRO, '3001112233', FECHA, '09:00', SERV, 'Ana')
check('cita real creada', bool(cid))
chat = H.generar_horarios_disponibles_actualizado(NEG, PRO, FECHA, SERV)
check('chat: ya no ofrece 9:00 AM ni 9:30 AM (cita 9:00-9:45)', '9:00 AM' not in chat and '9:30 AM' not in chat and '9:45 AM' in chat, str(chat[:5]))
check('chat: formato de 12 horas', all(('AM' in x or 'PM' in x) for x in chat))

# bloquear encima de una cita: pide confirmación y, con sobreescribir, la cancela
r = db.bloquear_horario_profesional(NEG, PRO, FECHA, '09:30', duracion_minutos=60, motivo='Reunión')
check('bloquear sobre una cita existente pide confirmación (ya no falla con ValueError)', (not r.get('success')) and r.get('needs_override'), str(r)[:120])
r = db.bloquear_horario_profesional(NEG, PRO, FECHA, '09:30', duracion_minutos=60, motivo='Reunión', sobreescribir=True)
check('bloquear con sobreescribir cancela la cita y crea el bloqueo', r.get('success'), str(r)[:120])
chat = H.generar_horarios_disponibles_actualizado(NEG, PRO, FECHA, SERV)
check('chat: el bloqueo 9:30-10:30 oculta esas horas', not [x for x in chat if x in ('9:30 AM', '9:45 AM', '10:00 AM', '10:15 AM')] and '10:30 AM' in chat, str(chat[:6]))

# bloqueo recurrente: se materializa con su duración real
limpiar()
dow = d.isoweekday()
rr = db.crear_bloqueo_recurrente(NEG, PRO, [dow], '15:00', '17:30', motivo='Curso')
check('bloqueo recurrente creado', bool(rr), str(rr)[:100])
x = db.agregar_cita(NEG, PRO, '3001112233', FECHA, '16:00', SERV, 'Intruso')
check('agregar_cita dentro de un bloqueo recurrente es rechazada', not x, f'(cita_id={x})')
x = db.agregar_cita(NEG, PRO, '3001112233', FECHA, '14:30', SERV, 'Justo antes')
check('agregar_cita que termina justo al empezar el bloqueo (14:15-15:00) se acepta', bool(x) and x > 0, f'(cita_id={x})') if False else None
x = db.agregar_cita(NEG, PRO, '3001112233', FECHA, '14:15', SERV, 'Justo antes')
check('agregar_cita 14:15-15:00 (termina justo al empezar el bloqueo) se acepta', bool(x), f'(cita_id={x})')
x = db.agregar_cita(NEG, PRO, '3001112233', FECHA, '17:30', SERV, 'Justo después')
check('agregar_cita 17:30 (justo al terminar el bloqueo) se acepta', bool(x), f'(cita_id={x})')
chat = H.generar_horarios_disponibles_actualizado(NEG, PRO, FECHA, SERV)
check('chat: 15:00-17:30 recurrente oculto', not [x for x in chat if x in ('3:00 PM', '3:15 PM', '4:00 PM', '5:00 PM', '5:15 PM')] and '6:15 PM' in chat, str(chat[-6:]))

# API de horarios del panel (misma lógica, 'HH:MM')
importlib.invalidate_caches()
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
import app as A
cli = A.app.test_client()
r = cli.get(f'/api/horarios_disponibles?profesional_id={PRO}&fecha={FECHA}&servicio_id={SERV}')
j = r.get_json()
check('API /api/horarios_disponibles responde 200', r.status_code == 200, str(j)[:100])
hs = j.get('horarios', [])
check('API: formato HH:MM y sin el bloqueo recurrente 15:00-17:30', hs and all(len(x) == 5 for x in hs) and not [x for x in hs if '15:00' <= x < '17:30'] and '18:15' in hs, str(hs[-8:]))
check('API: paso de 15 min (igual que el chat)', '09:15' in hs)
r = cli.get(f'/api/horarios_disponibles?profesional_id={PRO}&fecha=basura&servicio_id={SERV}')
check('API: fecha inválida -> 400', r.status_code == 400)

# herramienta de IA
ia = H.ia_consultar_horarios({'profesional_nombre': 'x', 'fecha': FECHA}, NEG)
check('IA: responde sin romper', isinstance(ia, str) and len(ia) > 0, ia[:80].replace('\n', ' | '))
profs = db.obtener_profesionales(NEG)
check('hay profesionales en la BD de prueba', len(profs) > 0)
ia = H.ia_consultar_horarios({'profesional_nombre': profs[0]['nombre'], 'fecha': FECHA}, NEG)
check('IA: lista horarios en 12h y los ocupados no aparecen', ('AM' in ia or 'PM' in ia) and '3:00 PM' not in ia and 'servicio más corto' in ia, ia.replace('\n', ' | ')[:200])

limpiar()
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
