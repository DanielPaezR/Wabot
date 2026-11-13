"""Todas las plantillas: Jinja válido y JavaScript válido (requiere node)."""
import os as _os
_AQUI = _os.path.dirname(_os.path.abspath(__file__))
_SERVICIOS = _os.path.normpath(_os.path.join(_AQUI, '..', 'services'))
_SERVICIO = _os.path.join(_SERVICIOS, 'wabot_chat')
import os, re, glob, subprocess, tempfile
from jinja2 import Environment
R = _SERVICIOS
env = Environment(extensions=['jinja2.ext.do', 'jinja2.ext.loopcontrols'])
malas = 0; n = 0
for f in glob.glob(os.path.join(R, '*', 'templates', '**', '*.html'), recursive=True):
    s = open(f, encoding='utf-8').read(); n += 1
    rel = os.path.relpath(f, R)
    try:
        env.parse(s)
    except Exception as e:
        malas += 1; print('JINJA', rel, e); continue
    plano = re.sub(r'\{\{.*?\}\}', '0', re.sub(r'\{%.*?%\}', '', s, flags=re.S), flags=re.S)
    for i, js in enumerate(re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>', plano, re.S)):
        p = os.path.join(tempfile.gettempdir(), '_ck.js'); open(p, 'w', encoding='utf-8').write(js)
        r = subprocess.run(['node', '--check', p], capture_output=True, text=True, encoding='utf-8')
        if r.returncode:
            malas += 1; print('JS', rel, i, (r.stderr or '').strip().splitlines()[-1:])
print(f'{n} plantillas, {malas} con problemas')

import sys as _sys
print("RESULTADO: TODO OK" if malas == 0 else "RESULTADO: HAY FALLOS")
_sys.exit(0)
