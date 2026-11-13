import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import json, os, re, subprocess, sys
RAIZ = _SERVICIOS
sys.path.insert(0, _os.path.join(RAIZ, 'wabot_chat'))
from jinja2 import Environment
ok = True
def check(n, c):
    global ok; ok &= bool(c); print(('OK  ' if c else 'FALLO'), n)

# 1) sintaxis Jinja y JS de todas las plantillas tocadas
env = Environment()
for f in ['wabot_chat/templates/login.html', 'wabot_chat/templates/cliente/index.html',
          'wabot_directorio/templates/directorio/negocio.html', 'wabot_directorio/templates/directorio/profesional.html',
          'wabot_directorio/templates/directorio/mapa.html', 'wabot_chat/templates/negocio/prompt_ia.html']:
    html = open(os.path.join(RAIZ, f), encoding='utf-8').read()
    try:
        env.parse(html); okj = True
    except Exception as e:
        okj = False; print(e)
    check(f'Jinja válido: {f}', okj)
    rendered = re.sub(r'\{\{.*?\}\}', '0', re.sub(r'\{%.*?%\}', '', html, flags=re.S), flags=re.S)
    for i, js in enumerate(re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>', rendered, re.S)):
        p = os.path.join(__import__('tempfile').gettempdir(), f'_d_{i}.js'); open(p, 'w', encoding='utf-8').write(js)
        r = subprocess.run(['node', '--check', p], capture_output=True, text=True); os.remove(p)
        if r.returncode: print(r.stderr[:300])
        check(f'  JS #{i} sin errores: {f.split("/")[-1]}', r.returncode == 0)

# 2) color de acento: solo hex de 6 dígitos, texto legible
os.environ.pop('DATABASE_URL', None)
import importlib.util
src = open(_os.path.join(RAIZ, 'wabot_directorio', 'app.py'), encoding='utf-8').read()
bloque = src[src.index("ACENTO_DEFECTO"):src.index("_cors_origins")]
ns = {'json': json, 're': re, 'SimpleNamespace': __import__('types').SimpleNamespace}
exec(bloque, ns)
f = ns['acento_del_negocio']; N = ns['SimpleNamespace']
check('acento por defecto dorado', f(N(configuracion={}))[0] == '#d4a857')
check('acento válido desde JSON (str)', f(N(configuracion='{"color_acento": "#1E90FF"}'))[0] == '#1E90FF')
check('acento válido desde dict', f(N(configuracion={'color_acento': '#ffffff'}))[1] == '#17110a')
check('acento oscuro -> texto blanco', f(N(configuracion={'color_acento': '#0a2a66'}))[1] == '#ffffff')
for malo in ['red', '#12', '#12345g', 'javascript:alert(1)', '#fff;}body{x:y', None, 123]:
    check(f'acento inválido ignorado: {malo!r}', f(N(configuracion={'color_acento': malo}))[0] == '#d4a857')
check('configuracion inválida no rompe', f(N(configuracion='no-json'))[0] == '#d4a857')
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
