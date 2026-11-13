import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import json, os, re, subprocess
from flask import Flask, render_template
RAIZ = _SERVICIO
app = Flask('t', template_folder=os.path.join(RAIZ, 'templates')); app.secret_key = 'x'
app.url_build_error_handlers.append(lambda e, ep, v: '#')
app.template_filter('tojson')(lambda v: json.dumps(v))
@app.context_processor
def c(): return {'csrf_token': lambda: 'tok', 'current_user': None}
ok = True
def check(n, c):
    global ok; ok &= bool(c); print(('OK  ' if c else 'FALLO'), n)
with app.test_request_context('/'):
    for actual in ('', 'Hola {nombre_negocio}'):
        html = render_template('negocio/prompt_ia.html', negocio={'nombre': 'N'}, prompt_actual=actual,
            variables=[{'variable': '{direccion}', 'etiqueta': 'Dirección', 'valor': 'Calle 1 "x"'}, {'variable': '{telefono}', 'etiqueta': 'Tel', 'valor': '+297'}],
            prompt_renderizado='Negocio: N. Tel +297', max_caracteres=6000)
        check(f'editor (prompt={actual!r}): botones insertan variables, no valores', 'data-variable="{direccion}"' in html and 'data-valor' not in html)
        check('editor: no aparece la palabra None', '>None<' not in html and 'None</textarea>' not in html)
        check('editor: muestra la vista previa', 'Negocio: N. Tel +297' in html)
        check('editor: el valor actual va en el tooltip escapado', 'title="Ahora vale: Calle 1 &#34;x&#34;"' in html)
        js = re.findall(r'<script>(.*?)</script>', html, re.S)[0]
        open(os.path.join(__import__('tempfile').gettempdir(), '_p.js'), 'w', encoding='utf-8').write(js)
        check('editor: JS válido', subprocess.run(['node', '--check', os.path.join(__import__('tempfile').gettempdir(), '_p.js')], capture_output=True).returncode == 0)
print('\nRESULTADO:', 'TODO OK' if ok else 'HAY FALLOS')
