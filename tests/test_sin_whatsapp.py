import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, sys, importlib, types
os.environ.pop('DATABASE_URL', None); os.environ['SECRET_KEY']='t'; os.environ.pop('WHATSAPP_WEBHOOK_SECRET', None); os.environ.pop('WHATSAPP_ACTIVO', None)
sys.path.insert(0, _SERVICIO)
for nombre in ['flask_login','cloudinary','cloudinary.uploader','openai']:
    try: importlib.import_module(nombre)
    except ImportError:
        m=types.ModuleType(nombre)
        if nombre=='flask_login':
            class _LM:
                def __init__(self,*a,**k): pass
                def __getattr__(self,n): return lambda *a,**k:(lambda f:f)
            m.LoginManager=_LM
            for n in ['login_user','logout_user','login_required','current_user']: setattr(m,n,(lambda f=None,*a,**k:f))
        if nombre=='cloudinary': m.config=lambda **k:None
        sys.modules[nombre]=m
if 'cloudinary.uploader' in sys.modules and not hasattr(sys.modules['cloudinary'],'uploader'): sys.modules['cloudinary'].uploader=sys.modules['cloudinary.uploader']
import localizacion as L; L._consultar_bd=lambda n: None
import app as A
ok=True
def check(n,c): 
    global ok; ok&=bool(c); print('OK  ' if c else 'FALLO', n)
c=A.app.test_client()
check('webhook de n8n sin clave configurada -> apagado (401)', c.post('/api/whatsapp/webhook', json={'from':'1','to':'2','message':'x'}).status_code==401)
check('negocio-por-numero apagado', c.get('/api/whatsapp/negocio-por-numero?numero=1').status_code==401)
check('sesion apagado', c.get('/api/whatsapp/sesion/x').status_code==401)
check('rutas de Meta inexistentes sin variables', c.get('/api/whatsapp/meta/webhook').status_code==404)
with A.app.test_request_context('/'):
    from flask import render_template_string
    t="{% if whatsapp_activo %}SI{% else %}NO{% endif %}"
    check('flag whatsapp_activo desactivado por defecto', render_template_string(t)=='NO')
    os.environ['WHATSAPP_ACTIVO']='1'
    check('flag activado con WHATSAPP_ACTIVO=1', render_template_string(t)=='SI')
print('RESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
