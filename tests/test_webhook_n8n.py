import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys, types, importlib
os.environ.pop('DATABASE_URL', None)
os.environ['SECRET_KEY'] = 'test'
os.environ['WHATSAPP_WEBHOOK_SECRET'] = 'clave-n8n'
sys.path.insert(0, _SERVICIO)

# módulos de terceros que pueden no estar instalados localmente
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
def check(n, c):
    global ok; ok &= bool(c); print(('OK  ' if c else 'FALLO'), n)

llamadas = []
A.obtener_negocio_por_numero_whatsapp = lambda numero: 10
import web_chat_handler as H
H.procesar_mensaje_chat = lambda **kw: (llamadas.append(kw['user_message']) or {'message': f"eco:{kw['user_message']}", 'options': [{'value': str(i), 'text': f'Opcion {i}'} for i in range(1, 6)]})
c = A.app.test_client()
body = {'from': '+573000000001', 'to': '+573017650099', 'message': 'hola', 'message_id': 'wamid.1'}
H_ = {'X-Webhook-Secret': 'clave-n8n'}

check('sin header -> 401', c.post('/api/whatsapp/webhook', json=body).status_code == 401)
check('header incorrecto -> 401', c.post('/api/whatsapp/webhook', json=body, headers={'X-Webhook-Secret': 'mala'}).status_code == 401)
check('negocio-por-numero sin header -> 401', c.get('/api/whatsapp/negocio-por-numero?numero=1').status_code == 401)
check('sesion sin header -> 401', c.get('/api/whatsapp/sesion/x').status_code == 401)
r = c.post('/api/whatsapp/webhook', json=body, headers=H_)
check('con header -> 200', r.status_code == 200)
d = r.get_json()
check('5 opciones -> tipo_interactivo lista', d.get('tipo_interactivo') == 'lista' and len(d['buttons']) == 5)
r2 = c.post('/api/whatsapp/webhook', json=body, headers=H_)
check('mismo message_id: respuesta repetida y NO se reprocesa', r2.get_json() == d and llamadas == ['hola'])
body2 = dict(body, message_id='wamid.2', message='quiero agendar')
c.post('/api/whatsapp/webhook', json=body2, headers=H_)
check('otro message_id sí se procesa', llamadas == ['hola', 'quiero agendar'])
check('cuerpo no JSON -> 400 (no 500)', c.post('/api/whatsapp/webhook', data='hola', headers=H_).status_code == 400)
check('JSON incompleto -> 400', c.post('/api/whatsapp/webhook', json={'from': '1'}, headers=H_).status_code == 400)
H.procesar_mensaje_chat = lambda **kw: {'message': 'x', 'options': [{'value': '1', 'text': 'A'}, {'value': '2', 'text': 'B'}]}
d3 = c.post('/api/whatsapp/webhook', json=dict(body, message_id='wamid.3'), headers=H_).get_json()
check('2 opciones -> tipo_interactivo botones', d3.get('tipo_interactivo') == 'botones')
ses = A.app.config['whatsapp_sessions']; k = next(iter(ses)); ses[k]['_ultimo_uso'] = 0
A._wa_limpiar_estado()
check('sesiones de >24h se descartan', k not in A.app.config['whatsapp_sessions'])
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
