"""Conexión directa con la API de Meta: firma, verificación, extracción, envíos y flujo completo (API de Meta simulada)."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys, json, hmac, hashlib, time, importlib, types
os.environ.pop('DATABASE_URL', None)
os.environ['SECRET_KEY'] = 'test'
os.environ.pop('META_WHATSAPP_TOKEN', None); os.environ.pop('META_APP_SECRET', None); os.environ.pop('META_VERIFY_TOKEN', None)
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
import whatsapp_meta as W
import app as A

ok = True
def check(n, c, extra=''):
    global ok; ok &= bool(c); print(('OK   ' if c else 'FALLO'), n, extra)

SECRETO = 'secreto-app'
def firmar(cuerpo, secreto=SECRETO):
    return 'sha256=' + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()

def payload(mensajes, meta=None):
    return {'object': 'whatsapp_business_account', 'entry': [{'id': 'WABA', 'changes': [{'field': 'messages', 'value': {
        'messaging_product': 'whatsapp', 'metadata': meta or {'display_phone_number': '57 301 765 0099', 'phone_number_id': 'PNID1'},
        'contacts': [{'profile': {'name': 'Ana'}, 'wa_id': '573001234567'}], 'messages': mensajes}}]}]}

texto = lambda t, i='wamid.A1': {'from': '573001234567', 'id': i, 'timestamp': '1', 'type': 'text', 'text': {'body': t}}
boton = lambda i, i_msg='wamid.B1': {'from': '573001234567', 'id': i_msg, 'type': 'interactive', 'interactive': {'type': 'button_reply', 'button_reply': {'id': i, 'title': 'Agendar cita'}}}
lista = lambda i, i_msg='wamid.L1': {'from': '573001234567', 'id': i_msg, 'type': 'interactive', 'interactive': {'type': 'list_reply', 'list_reply': {'id': i, 'title': '10:15 AM'}}}
audio = {'from': '573001234567', 'id': 'wamid.AU', 'type': 'audio', 'audio': {'id': 'x'}}

# --- firma
cuerpo = b'{"a":1}'
check('firma válida', W.firma_valida(cuerpo, firmar(cuerpo), SECRETO))
check('firma con otro secreto -> inválida', not W.firma_valida(cuerpo, firmar(cuerpo, 'otro'), SECRETO))
check('cuerpo alterado -> inválida', not W.firma_valida(b'{"a":2}', firmar(cuerpo), SECRETO))
check('sin cabecera / sin secreto / formato raro -> inválida', not W.firma_valida(cuerpo, '', SECRETO) and not W.firma_valida(cuerpo, firmar(cuerpo), '') and not W.firma_valida(cuerpo, 'md5=abc', SECRETO))

# --- extracción
ms = W.extraer_mensajes(payload([texto('Hola'), boton('1'), lista('3'), audio]))
check('extrae 4 mensajes', len(ms) == 4)
check('texto', ms[0]['message'] == 'Hola' and ms[0]['to'] == '57 301 765 0099' and ms[0]['phone_number_id'] == 'PNID1' and ms[0]['from'] == '573001234567' and ms[0]['message_id'] == 'wamid.A1')
check('botón -> usa el id (el flujo numerado espera "1")', ms[1]['message'] == '1')
check('lista -> usa el id', ms[2]['message'] == '3')
check('audio -> no soportado', ms[3]['soportado'] is False)
estado = {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': 'P'}, 'statuses': [{'status': 'read'}]}}]}]}
check('notificación de estado (leído) se ignora', W.extraer_mensajes(estado) == [] and W.extraer_mensajes({}) == [] and W.extraer_mensajes(None) == [])

# --- construcción de envíos
e = W.construir_envios({'message': 'Hola Ana'}, '573001234567')
check('texto simple', len(e) == 1 and e[0]['type'] == 'text' and e[0]['text']['body'] == 'Hola Ana' and e[0]['to'] == '573001234567' and e[0]['messaging_product'] == 'whatsapp')
e = W.construir_envios({'message': '¿Qué deseas?', 'buttons': [{'id': '1', 'title': 'Agendar cita'}, {'id': '2', 'title': 'Ver mis citas'}]}, '57300')
check('2 opciones -> botones de respuesta', len(e) == 1 and e[0]['interactive']['type'] == 'button' and [b['reply']['id'] for b in e[0]['interactive']['action']['buttons']] == ['1', '2'])
e = W.construir_envios({'message': 'Horarios', 'buttons': [{'id': str(i), 'title': f'{i}:00 AM con un título larguísimo de prueba'} for i in range(1, 13)]}, '57300')
filas = e[0]['interactive']['action']['sections'][0]['rows']
check('12 opciones -> lista de máximo 10 filas con título ≤ 24', e[0]['interactive']['type'] == 'list' and len(filas) == 10 and all(len(f['title']) <= 24 for f in filas))
largo = 'x' * 1500
e = W.construir_envios({'message': largo, 'buttons': [{'id': '1', 'title': 'Sí'}]}, '57300')
check('texto largo + opciones -> texto normal y luego opciones con cuerpo corto', len(e) == 2 and e[0]['type'] == 'text' and e[1]['interactive']['body']['text'] == 'Elige una opción:')
check('texto > 4000 se recorta', len(W.construir_envios({'message': 'y' * 9000}, '1')[0]['text']['body']) == 4000)
b3 = W.construir_envios({'message': 'm', 'buttons': [{'id': '1', 'title': 'T' * 40}]}, '1')[0]['interactive']['action']['buttons'][0]['reply']['title']
check('título de botón ≤ 20', len(b3) == 20)

# --- flujo completo con la API de Meta simulada
enviados = []
def falso_enviar(pnid, cuerpo, token=None):
    enviados.append((pnid, cuerpo)); return True, ''
llamadas = []
def procesar(entrada):
    llamadas.append(entrada)
    if entrada['to'] == '9999':
        return {'error': 'Número no registrado'}, 404
    if entrada['message'] == 'boom':
        return {'error': 'Error interno'}, 500
    return {'success': True, 'message': f"eco:{entrada['message']}", 'buttons': [{'id': '1', 'title': 'Uno'}, {'id': '2', 'title': 'Dos'}]}, 200
vistos = set()
def reclamar(clave):
    if clave in vistos: return False
    vistos.add(clave); return True

r = W.manejar_notificacion(payload([texto('Hola')]), procesar, reclamar, falso_enviar)
check('manejar: envía la respuesta al cliente por el phone_number_id correcto', r == [('wamid.A1', 'enviado')] and enviados[-1][0] == 'PNID1' and enviados[-1][1]['to'] == '573001234567' and enviados[-1][1]['interactive']['body']['text'] == 'eco:Hola')
check('manejar: se llamó a procesar con from/to/message/message_id', llamadas[-1] == {'from': '573001234567', 'to': '57 301 765 0099', 'message': 'Hola', 'message_id': 'wamid.A1'})
n = len(enviados)
r = W.manejar_notificacion(payload([texto('Hola')]), procesar, reclamar, falso_enviar)
check('reintento de Meta (mismo wamid) no se procesa ni se responde dos veces', r == [('wamid.A1', 'repetido')] and len(enviados) == n)
r = W.manejar_notificacion(payload([boton('2', 'wamid.B2')]), procesar, reclamar, falso_enviar)
check('botón pulsado llega como "2"', llamadas[-1]['message'] == '2')
r = W.manejar_notificacion(payload([audio]), procesar, reclamar, falso_enviar)
check('audio: respuesta amable sin pasar por el chat', r == [('wamid.AU', 'enviado')] and 'solo puedo leer mensajes de texto' in enviados[-1][1]['text']['body'])
n = len(enviados)
r = W.manejar_notificacion(payload([texto('x', 'wamid.X')], meta={'display_phone_number': '9999', 'phone_number_id': 'P9'}), procesar, reclamar, falso_enviar)
check('número que no es de ningún negocio: no se responde', r == [('wamid.X', 'sin_negocio')] and len(enviados) == n)
r = W.manejar_notificacion(payload([texto('boom', 'wamid.E')]), procesar, reclamar, falso_enviar)
check('error interno: se avisa al cliente con un mensaje genérico', enviados[-1][1]['text']['body'].startswith('Tuve un problema'))
def enviar_falla(*a, **k): return False, 'HTTP 401'
r = W.manejar_notificacion(payload([texto('Hola', 'wamid.F')]), procesar, reclamar, enviar_falla)
check('si Meta rechaza el envío se registra y no se rompe', r == [('wamid.F', 'error_envio')])
r = W.manejar_notificacion(payload([texto('uno', 'wamid.M1'), texto('dos', 'wamid.M2')]), procesar, reclamar, falso_enviar)
check('varios mensajes en una notificación', [x[1] for x in r] == ['enviado', 'enviado'])
def procesar_revienta(e): raise RuntimeError('x')
r = W.manejar_notificacion(payload([texto('Hola', 'wamid.R')]), procesar_revienta, reclamar, falso_enviar)
check('una excepción en procesar no tumba el hilo', r == [('wamid.R', 'error')])

# --- rutas Flask
cli = A.app.test_client()
check('sin variables de entorno las rutas de Meta no existen (404)', cli.get('/api/whatsapp/meta/webhook?hub.mode=subscribe').status_code == 404 and cli.post('/api/whatsapp/meta/webhook', data=b'{}').status_code == 404)
os.environ.update({'META_WHATSAPP_TOKEN': 'tok', 'META_APP_SECRET': SECRETO, 'META_VERIFY_TOKEN': 'verifica123'})
r = cli.get('/api/whatsapp/meta/webhook?hub.mode=subscribe&hub.verify_token=verifica123&hub.challenge=987654')
check('verificación de Meta: devuelve el challenge', r.status_code == 200 and r.get_data(as_text=True) == '987654')
check('verificación con token incorrecto -> 403', cli.get('/api/whatsapp/meta/webhook?hub.mode=subscribe&hub.verify_token=mal&hub.challenge=1').status_code == 403)
cuerpo = json.dumps(payload([texto('Hola', 'wamid.Z1')])).encode()
check('POST sin firma -> 403', cli.post('/api/whatsapp/meta/webhook', data=cuerpo, content_type='application/json').status_code == 403)
check('POST con firma falsa -> 403', cli.post('/api/whatsapp/meta/webhook', data=cuerpo, content_type='application/json', headers={'X-Hub-Signature-256': firmar(cuerpo, 'otro')}).status_code == 403)

# POST firmado: responde 200 de inmediato y procesa en segundo plano (se sustituyen procesar y envío)
recibidos = []
W.enviar = lambda pnid, cuerpo_, token=None: (recibidos.append((pnid, cuerpo_)) or (True, ''))
A.obtener_negocio_por_numero_whatsapp = lambda numero: 7
import web_chat_handler as H
H.procesar_mensaje_chat = lambda **kw: {'message': f"bot:{kw['user_message']}", 'options': [{'value': '1', 'text': 'Agendar'}]}
t0 = time.time()
r = cli.post('/api/whatsapp/meta/webhook', data=cuerpo, content_type='application/json', headers={'X-Hub-Signature-256': firmar(cuerpo)})
check('POST firmado -> 200 inmediato', r.status_code == 200 and time.time() - t0 < 2)
for _ in range(50):
    if recibidos: break
    time.sleep(0.1)
check('integración real: el mensaje pasó por procesar_whatsapp_entrante y se respondió por Meta', recibidos and recibidos[0][0] == 'PNID1' and recibidos[0][1]['to'] == '573001234567' and 'bot:Hola' in json.dumps(recibidos[0][1]), str(recibidos[:1])[:150])
cuerpo2 = json.dumps({'entry': []}).encode()
check('POST firmado sin mensajes -> 200', cli.post('/api/whatsapp/meta/webhook', data=cuerpo2, content_type='application/json', headers={'X-Hub-Signature-256': firmar(cuerpo2)}).status_code == 200)

print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
